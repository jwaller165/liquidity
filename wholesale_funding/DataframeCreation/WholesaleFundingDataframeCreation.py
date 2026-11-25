# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # How this notebook works
# MAGIC
# MAGIC Each code cell is labeled `Step N`. Read the map top to bottom.
# MAGIC
# MAGIC ```
# MAGIC  INPUTS                          STEP                                  WHAT HAPPENS
# MAGIC  ------                          ----                                  ------------
# MAGIC
# MAGIC  Workbook, Historical tab ---->  3  Read and clean the tab             headers, dates, $ and % text,
# MAGIC                                                                        Yes/No flags, blank tranche = 1
# MAGIC                                     |
# MAGIC  id_lookup (in Step 2) ------->  4  Calculate columns                                                                       sec_id, whlsefndg_id and cost center
# MAGIC                                                                        from the lookup, counterparty type, legal entity,
# MAGIC                                                                        GL split, maturity bucket, TPS second
# MAGIC                                                                        leg, keep month-end rows only
# MAGIC                                     |
# MAGIC  JH, FIS, SNV TPG tables ----->  5  Pull brokered source balances      one stacked view of source accounts
# MAGIC                                     |                                  (balance, system, entity_id)
# MAGIC                                     v
# MAGIC                                  6  Allocate to brokered tranches      a. no account? take tranche 2's
# MAGIC                                                                           (else tranche 1's)
# MAGIC                                                                        b. match the account to a source row;
# MAGIC                                                                           if none, match the CUSIP
# MAGIC                                                                        c. fill the tranches in order up to
# MAGIC                                                                           max_balance; BRK_NMD is filled last
# MAGIC                                                                        d. no cost center? take the source
# MAGIC                                                                           row's entity_id
# MAGIC                                                                        e. keep the source account type
# MAGIC                                                                           (src_ac_tp_code, src_ac_tp_desc)
# MAGIC                                     |
# MAGIC                                     v
# MAGIC                                  7  Complete cost centers and GLs      Fed Funds rule, then lookup, then
# MAGIC                                                                        source entity_id, then bank default.
# MAGIC                                                                        GL from the source account type.
# MAGIC                                                                        Fill legal entity and level6_id.
# MAGIC                                     |
# MAGIC                                     v
# MAGIC                                  8  Final columns, in order
# MAGIC                                  9  Validate                          hard stops (unmapped rows, pools that do
# MAGIC                                                                        not tie) and warnings
# MAGIC                                 10  Write                              table or temp view (your choice)
# MAGIC                                 11  Run report (optional)              Excel: Run Info, Column Guide, Final Table, GL Recon,
# MAGIC                                                                        GL Recon by Bank, GL Recon by Entity, Maturity Buckets
# MAGIC ```
# MAGIC
# MAGIC ## Where each column comes from
# MAGIC
# MAGIC Every column has a 1 to 3 line description of how it is derived. It is written as a column comment when the output is a table (see `COLUMN_COMMENTS` in Step 8) and is listed on the Column Guide tab of the run report.
# MAGIC
# MAGIC `current_balance` follows one rule: brokered rows with a source match take their allocated balance (the source balance filled into the tranches up to each `max_balance`, the Brokered NMD tranche last). Every other row keeps the workbook balance. `allocation_flag` says which rows used the allocation.
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC # Wholesale Funding: Month-End Build
# MAGIC
# MAGIC Builds the month-end wholesale funding table from the source tab of the Wholesale Funding Dashboard workbook, allocates source-system balances to brokered deposit tranches, and can write a run report workbook.
# MAGIC
# MAGIC ## Run options
# MAGIC
# MAGIC | Widget | What it does |
# MAGIC |---|---|
# MAGIC | Report File Name / Custom File Name | Name of the Excel report. Pick a preset, or pick `custom` and type a name. The report date is added, for example `wholesale_funding_month_end_20260930.xlsx`. |
# MAGIC | Output Type | `table` writes a Unity Catalog table. `temp view` creates a session-only view for testing. |
# MAGIC | Write Mode | `overwrite` replaces the table. `append` removes the loaded as-of dates from the table first, then appends, so a rerun does not duplicate rows. |
# MAGIC | Environment | `dev` writes to `finance.dev`, `prod` writes to `finance.reporting`. Only applies to tables. |
# MAGIC | Table / View Name | Name of the output table or view. |
# MAGIC | Source Folder / Source Tab | Workspace folder holding the workbook and the tab to read (default `Historical`). |
# MAGIC | Create Run Report | `yes` writes an Excel workbook and prints the tables below. |
# MAGIC | Report Date | Month-end for the report. Blank uses the latest as-of date in the run. |
# MAGIC | Final Table Tab | `report date only` or `all dates`. |
# MAGIC | Report Folder | Workspace folder for the report workbook. |
# MAGIC
# MAGIC GL Recon leaves out TM1 GL 2328128 and the pairs in `RECON_EXCLUDED_PAIRS` (GL 2321008 at entity 165.9998001), on both the wholesale funding and TM1 sides. The Run Info tab lists them.
# MAGIC
# MAGIC ## Run report tabs
# MAGIC
# MAGIC 1. Run Info: run parameters, row counts and validation warnings.
# MAGIC 2. Column Guide: how each column is derived.
# MAGIC 3. Final Table: the final table.
# MAGIC 4. GL Recon: wholesale funding balance against the TM1 trial balance by GL account, with the TM1 entities that carry each balance.
# MAGIC 5. GL Recon by Bank: the same comparison by GL account and legacy bank. TM1 takes the bank from Projects ("No Project" shows as `(no project)`). Each recon tab also shows the GL table's recon group.
# MAGIC 6. GL Recon by Entity: the same comparison by GL account and entity (cost center).
# MAGIC 7. Maturity Buckets: balance by maturity bucket, then by instrument and product.
# MAGIC
# MAGIC ## Assumptions
# MAGIC
# MAGIC - A month-end snapshot is a row whose `as_of_date` equals the last business day of its month.
# MAGIC - Brokered tranche allocation: a tranche with its own account keeps it. A tranche 2 or higher with no account takes tranche 2's account. If tranche 2 has no account either, the null tranches use tranche 1's account (`TRANCHE_1_FALLBACK`). Each account's source balance fills its tranches in order, each up to its `max_balance`. The Brokered NMD (BRK_NMD) tranche is filled last and takes any remainder. The account is matched to the source systems first; if nothing matches, the row's CUSIP is matched to the source account number.
# MAGIC - A null tranche is treated as tranche 1.
# MAGIC - `sec_id` is the Empyrean SecID from the id lookup (Step 2), joined on `contract_id`; contracts not in the lookup have none. `whlsefndg_id` equals `sec_id` for borrowings. For brokered deposits it is built as `BrokNMD-`, `BrokTerm-` or `BrokCD-` + `contract_id` + `-` + tranche.
# MAGIC - `cost_center_id` comes from the id lookup; if the lookup has none, from the `entity_id` of the matched source account (JH, FIS, SNV TPG); if there is still none, from the legacy bank default (`BANK_DEFAULT`, listed as a warning). `cost_center_source` records which. A row with no cost center or legal entity stops the run.
# MAGIC - `legal_entity_id` comes from the cost center prefix (165 Bank, D7B HoldCo, P81 and FCT TPS). Brokered deposits are `Bank`. The internal TPS second leg is `HoldCo`.
# MAGIC - Balances are whole dollars even though the workbook headers say $MM. Percent text such as `3.87%` is converted to `0.0387`.
# MAGIC - Flags are stored as `TRUE` / `FALSE` strings.
# MAGIC - Rows with a blank instrument type take it from the other rows of the same contract and as-of date.
# MAGIC
# MAGIC ## Column renames from the previous version
# MAGIC
# MAGIC `Sec_ID` to `whlsefndg_id` (`sec_id` is back as its own column: the Empyrean SecID from the id lookup, which can differ from `whlsefndg_id`), `currency_type` to `issue_currency`, `entity` to `legacy_bank`, `End_of_Month` to `end_of_month`, `Quarter_Year` to `quarter_year`, `target_millions` / `max_millions` to `target_balance` / `max_balance`, `contract_balance` to `contract_total_balance`, `broker_fee_cd_only` to `broker_fee_rate`, `annualized_exp_coupon` / `annualized_exp_all_in` to `annualized_coupon_expense` / `annualized_all_in_expense`, `contractual_maturity` / `auto_roll_at_notice` to `contractual_maturity_flag` / `auto_roll_flag`, `gl_bs_acct` / `gl_bs_fee_acct` to `gl_account_number` / `gl_fee_account_number`, `income_gl` split into `income_gl_account_number` / `income_fee_gl_account_number`, `_ingested_at` / `_source_file` to `ingested_at` / `source_file`.
# MAGIC
# MAGIC The first run after this change must use `overwrite`, because the table schema changed.

# COMMAND ----------

# DBTITLE 1,Imports, run options and constants
# Step 1: Imports, run options and constants
%pip install openpyxl --quiet 

import openpyxl 
import os
import re
from datetime import datetime

import pandas as pd
from pyspark.sql import Window
from pyspark.sql import functions as f
from pyspark.sql.types import StringType, StructField, StructType

# ----------------------------------------------------------------------------
# Run options
# ----------------------------------------------------------------------------
dbutils.widgets.dropdown(
    "report_file_name",
    "wholesale_funding_run_report",
    ["wholesale_funding_run_report", "wholesale_funding_month_end", "wholesale_funding_recon_pack", "custom"],
    "1. Report File Name",
)
dbutils.widgets.text("custom_file_name", "", "2. Custom File Name (used when Report File Name = custom)")
dbutils.widgets.dropdown("view_type", "temp view", ["table", "temp view"], "3. Output Type")
dbutils.widgets.dropdown("write_mode", "overwrite", ["overwrite", "append"], "4. Write Mode")
dbutils.widgets.dropdown("environment", "dev", ["prod", "dev"], "5. Environment")
dbutils.widgets.text("view_name", "wholesalefunding", "6. Table / View Name")
dbutils.widgets.text(
    "source_folder",
    "/Workspace/Users/joshuawaller@synovus.com/liquidity/wholesale_funding/FlatFlies",
    "7. Source Folder (Workspace Path)",
)
dbutils.widgets.text("source_sheet", "Historical", "8. Source Tab")
dbutils.widgets.dropdown("run_report", "no", ["no", "yes"], "9. Create Run Report")
dbutils.widgets.text("report_date", "", "10. Report Date (YYYY-MM-DD, blank = latest)")
dbutils.widgets.dropdown("report_table_scope", "report date only", ["report date only", "all dates"], "11. Final Table Tab")
dbutils.widgets.text(
    "report_folder",
    "/Workspace/Users/joshuawaller@synovus.com/liquidity/wholesale_funding/Outputs/run_reports",
    "12. Report Folder (Workspace Path)",
)

view_type = dbutils.widgets.get("view_type")
write_mode = dbutils.widgets.get("write_mode")
environment = dbutils.widgets.get("environment")
view_name = dbutils.widgets.get("view_name").strip().lower()
source_sheet = dbutils.widgets.get("source_sheet").strip()
run_report = dbutils.widgets.get("run_report") == "yes"
report_table_scope = dbutils.widgets.get("report_table_scope")

# Report file name: a preset from the dropdown, or the custom name. The report date is added: <name>_<YYYYMMDD>.xlsx
report_file_name = dbutils.widgets.get("report_file_name")
if report_file_name == "custom":
    custom_name = re.sub(r"\.xlsx$", "", dbutils.widgets.get("custom_file_name").strip(), flags=re.I)
    report_file_name = re.sub(r"[^A-Za-z0-9_-]+", "_", custom_name).strip("_")
    if not report_file_name:
        raise ValueError("Report File Name is custom, so Custom File Name cannot be blank.")


def workspace_path(path):
    """Drop any 'file:' prefix and trailing slash, and make sure the path starts with /Workspace."""
    path = re.sub(r"^file:", "", path.strip()).rstrip("/")
    return path if path.startswith("/Workspace") else "/Workspace" + (path if path.startswith("/") else "/" + path)


source_folder = workspace_path(dbutils.widgets.get("source_folder"))
report_folder = workspace_path(dbutils.widgets.get("report_folder"))

report_date_text = dbutils.widgets.get("report_date").strip()
try:
    report_date_input = datetime.strptime(report_date_text, "%Y-%m-%d").date() if report_date_text else None
except ValueError:
    raise ValueError(f"Report Date must be YYYY-MM-DD or blank, got '{report_date_text}'.")

if not re.fullmatch(r"[a-z_][a-z0-9_]*", view_name):
    raise ValueError(f"Invalid name: '{view_name}'. Use letters, numbers and underscores only.")

# Tables go to Unity Catalog (prod -> finance.reporting, dev -> finance.dev). Temp views use the bare name.
target_schema = {"prod": "finance.reporting", "dev": "finance.dev"}[environment]
target_name = f"{target_schema}.{view_name}" if view_type == "table" else view_name

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
SOURCE_FILE = "Wholesale Funding Dashboard.xlsx"
file_location = f"file:{source_folder}/{SOURCE_FILE}"

DIM_DATES_TABLE = "finance.default.dim_dates"
TPG_POSITION_TABLE = "silver_dev.tpg_reports_pnfp.position_report"   # dev schema: repoint before relying on this in prod
TM1_TABLE = "silver_prod.p021.tm1_financetrialbalancepbi"
GL_ACCOUNT_TABLE = "silver_prod.reference_data.d_gl_account"

RECON_TOLERANCE = 100.00   # dollars; variances at or below this show as MATCH
FILL_LAST_PRODUCT_TYPE = "Brokered NMD"   # instrument_type_code BRK_NMD: the tranche filled last, it takes any remainder
EXCLUDED_PRIMARY_TYPES = ["Repo"]   # primary instrument types left out of the build (repos are no longer carried)
RECON_EXCLUDED_PAIRS = [("2321008", "165.9998001")]   # (GL account, entity) pairs left out of the GL recon on both sides
REPORT_EXCLUDE_INTERNAL = True   # GL Recon and Maturity Buckets use external rows only (internal_flag = FALSE), so the
                                  # internal TPS second leg is not counted twice. The Final Table tab always has every row.

# Maturity buckets: (label, first day, last day) counted from as_of_date. None = open ended.
MATURITY_BUCKETS = [
    ("Past Maturity", None, -1),
    ("0-30 days", 0, 30),
    ("31-90 days", 31, 90),
    ("91-180 days", 91, 180),
    ("181-365 days", 181, 365),
    ("1-2 years", 366, 730),
    ("2-3 years", 731, 1095),
    ("3-5 years", 1096, 1825),
    ("Over 5 years", 1826, None),
]
NO_MATURITY_LABEL = "No Maturity Date"
BUCKET_ORDER = [b[0] for b in MATURITY_BUCKETS] + [NO_MATURITY_LABEL]

print(f"Output:      {view_type} -> {target_name} ({environment}, {write_mode})")
print(f"Source:      {file_location}  [tab: {source_sheet}]")
print(f"Run report:  {'yes -> ' + report_folder + '/' + report_file_name + '_<report date>.xlsx' if run_report else 'no'}")

# COMMAND ----------

# DBTITLE 1,Reference data: sec_id and cost_center_id for borrowings
# Step 2: Reference data: sec_id (Empyrean SecID) and cost_center_id for borrowings
id_lookup_data = [
    ("SNV-ARC-1", "SNV_bor_464000000000_1", "165.9998001"),
    ("SNV-ARC-2", "SNV_bor_464000000000_2", "165.9998001"),
    ("SNV-ARC-3", "SNV_bor_464000000000_3", "165.9998001"),
    ("SNV-ARC-4", "SNV_bor_464000000000_4", "165.9998001"),
    ("SNV-ARC-5", "SNV_bor_464000000000_5", "165.9998001"),
    ("SNV-DRC-1", "SNV_bor_402000000000", "165.9998001"),
    ("PNFP-ADV-1", "BOR_69_1", "165.9998001"),
    ("PNFP-ADV-2", "BOR_495_2", "165.9998001"),
    ("PNFP-ADV-3", "BOR_496_3", "165.9998001"),
    ("PNFP-ADV-4", "BOR_498_4", "165.9998001"),
    ("PNFP-ADV-5", "BOR_499_5", "165.9998001"),
    ("PNFP-ADV-6", "BOR_505_6", "165.9998001"),
    ("PNFP-ADV-7", "BOR_507_7", "165.9998001"),
    ("PNFP-ADV-8", "BOR_509_8", "165.9998001"),
    ("PNFP-ADV-9", "BOR_513_9", "165.9998001"),
    ("SNV-HC-1", "SNV_bor_55555SBD5", "D7B.0008887"),
    ("SNV-BANK-1", "SNV_bor_55555SBD8", "165.9998001"),
    ("SNV-TPS-1", "SNV_bor_55555TPS3", "FCT.8888"),
    ("SNV-HC-2", "SNV_bor_55555SBD9", "D7B.0008887"),
    ("SNV-BANK-2", "SNV_bor_55555SBD10", "165.9998001"),
    ("PNFP-TPS-1", "BOR_TPS 1_15", "P81.0004700"),
    ("PNFP-TPS-2", "BOR_TPS 2_16", "P81.0004700"),
    ("PNFP-TPS-3", "BOR_TPS 3_17", "P81.0004700"),
    ("PNFP-TPS-4", "BOR_TPS 4_18", "P81.0004700"),
    ("PNFP-TPS-5", "BOR_BNC Cap Trust I_19", "P81.0004700"),
    ("PNFP-TPS-6", "BOR_BNC Cap Trust II_20", "P81.0004700"),
    ("PNFP-TPS-7", "BOR_BNC Cap Trust III_21", "P81.0004700"),
    ("PNFP-TPS-8", "BOR_BNC Cap Trust IV_22", "P81.0004700"),
    ("PNFP-TPS-9", "BOR_Southcoast Capital Trust III_26", "D7B.0008087"),
    ("PNFP-TPS-10", "BOR_Valley Cap Trust I_23", "P81.0004700"),
    ("PNFP-TPS-11", "BOR_Valley Cap Trust II_24", "P81.0004700"),
    ("PNFP-TPS-12", "BOR_Valley Cap Trust III_25", "P81.0004700"),
    ("PNFP-HC-1", "BOR_SUB DEBT NOTE_14", "P81.0004700"),
    ("SNV-HC-3", "SNV_bor_55555SBD11", "D7B.0008887"),
    ("SNV-FFP-1", "SNV-FFP-1", "165.9998001"),
    ("PNFP-FFP-1", "PNFP-FFP-2", "165.9998001"),
    ("PNFP-FFP-2", "PNFP-FFP-2", "165.9998001"),
    ("PNFP-FFP-3", "PNFP-FFP-3", "165.9998001"),
]

id_lookup_schema = StructType([
    StructField("contract_id", StringType(), True),
    StructField("sec_id", StringType(), True),   # Empyrean SecID; also the whlsefndg_id for borrowings
    StructField("cost_center_id", StringType(), True),
])
id_lookup_df = spark.createDataFrame(id_lookup_data, id_lookup_schema)

# The lookup is joined on contract_id, so it must be unique or rows would multiply.
duplicate_lookup_ids = id_lookup_df.groupBy("contract_id").count().filter("count > 1").count()
if duplicate_lookup_ids:
    raise ValueError("id_lookup has duplicate contract_id values.")

# COMMAND ----------

# DBTITLE 1,Read and clean the source tab
# Step 3: Read and clean the source tab
COLUMN_MAPPING = {
    "As Of Date": "as_of_date",
    "Entity": "legacy_bank",
    "Contract ID": "contract_id",
    "Tranche": "tranche",
    "Primary Instrument Type": "primary_instrument_type",
    "Sub-Instrument Type": "sub_instrument_type",
    "Product Type": "product_type",
    "Counterparty Name (if applicable)": "counterparty_name",
    "Account #": "account_number",
    "CUSIP": "cusip",
    "Issuance Date": "issuance_date",
    "Maturity Date": "maturity_date",
    "Months Remaining": "months_remaining",
    "Notice Date": "notice_date",
    "First Call Date": "first_call_date",
    "Contractual Maturity": "contractual_maturity_flag",
    "Auto-roll @ Notice": "auto_roll_flag",
    "Rate Type": "rate_type",
    "Benchmark": "benchmark",
    "Base Rate": "base_rate",
    "Spread": "spread",
    "Coupon Rate": "coupon_rate",
    "Annualized Exp Coupon": "annualized_coupon_expense",
    "Broker Fee (CD only)": "broker_fee_rate",
    "All in Rate": "all_in_rate",
    "Annualized Exp All-In": "annualized_all_in_expense",
    "Accrual Convention": "accrual_convention",
    "Int. Pay Frequency": "interest_payment_frequency",
    "Monthly Expense (est.)": "monthly_expense_est",
    "Annualized Expense (est.)": "annualized_expense_est",
    "Est. Yield": "estimated_yield",
    "Target ($MM)": "target_balance",          # header says $MM, values are whole dollars
    "Max ($MM)": "max_balance",
    "Principal Balance ($MM)": "current_balance",
    "Contract Balance ($MM)": "contract_total_balance",
    "Balance GL": "balance_gl_raw",
    "Income GL": "income_gl_raw",
    "Balance Data Source:": "balance_data_source",
}

DATE_COLUMNS = ["as_of_date", "issuance_date", "maturity_date", "notice_date", "first_call_date"]
RATE_COLUMNS = ["base_rate", "spread", "coupon_rate", "broker_fee_rate", "all_in_rate", "estimated_yield"]
AMOUNT_COLUMNS = [
    "target_balance", "max_balance", "monthly_expense_est", "annualized_expense_est",
    "annualized_coupon_expense", "annualized_all_in_expense",
]
WHOLE_DOLLAR_COLUMNS = ["current_balance", "contract_total_balance"]
FLAG_COLUMNS = ["contractual_maturity_flag", "auto_roll_flag"]
NUMERIC_COLUMNS = RATE_COLUMNS + AMOUNT_COLUMNS + WHOLE_DOLLAR_COLUMNS + ["months_remaining", "tranche"]
PLACEHOLDERS = ("n.a.", "na", "n/a", "none", "-", "--")


def clean_header(header):
    """Remove HTML breaks and standardize spacing in a source header."""
    header = re.sub(r"<br\s*/?>", "", header, flags=re.IGNORECASE)
    return " ".join(header.split()).strip()


def to_double(col, percent_aware=False, dash_is_zero=False):
    """Text to double. Strips $ , % and parentheses ('(1,000)' is negative).
    percent_aware: '3.87%' becomes 0.0387. dash_is_zero: an accounting dash '-' becomes 0."""
    c = f"trim(`{col}`)"
    num = f"try_cast(regexp_replace(regexp_replace({c}, '[$%,]', ''), '[()]', '') as double)"
    expr = f"case when {c} like '(%)' then -1 * {num} else {num} end"
    if dash_is_zero:
        expr = f"case when {c} = '-' then 0.0 else {expr} end"
    if percent_aware:
        expr = f"case when instr({c}, '%') > 0 then ({expr}) / 100 else {expr} end"
    return f.expr(expr)


def to_date(col):
    """Text to date. Handles M/d/yy, M/d/yyyy, yyyy-MM-dd and Excel serial numbers."""
    c = f"trim(`{col}`)"
    expr = (
        f"case "
        f"when {c} rlike '^[0-9]{{1,2}}/[0-9]{{1,2}}/[0-9]{{4}}$' then try_to_date({c}, 'M/d/yyyy') "
        f"when {c} rlike '^[0-9]{{1,2}}/[0-9]{{1,2}}/[0-9]{{2}}$' then try_to_date({c}, 'M/d/yy') "
        f"when {c} rlike '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' then try_to_date(substr({c}, 1, 10), 'yyyy-MM-dd') "
        f"when {c} rlike '^[0-9]+([.][0-9]+)?$' then date_add('1899-12-30', cast(try_cast({c} as double) as int)) "
        f"end"
    )
    return f.expr(expr)


def yes_no_flag(col):
    """Yes/No text to 'TRUE' / 'FALSE'. Anything else (n.a., blank) becomes null."""
    v = f.lower(f.trim(f.col(col)))
    return (
        f.when(v.isin("yes", "y", "true"), f.lit("TRUE"))
        .when(v.isin("no", "n", "false"), f.lit("FALSE"))
    )


# ---- Read the tab ----
raw = (
    spark.read.format("excel")
    .option("header", "false")
    .option("inferSchema", "false")
    .option("dataAddress", source_sheet)
    .load(file_location)
)

# The excel reader does not honor the header option on this compute, so take headers from the first row.
first_row = raw.first()
headers = [clean_header(str(first_row[i])) for i in range(len(raw.columns))]
if len(headers) != len(set(headers)):
    raise ValueError("Duplicate column names found after header cleanup.")
raw = raw.toDF(*headers).filter(f.col(headers[0]) != clean_header(str(first_row[0])))

missing = [c for c in COLUMN_MAPPING if c not in headers]
if missing:
    raise ValueError(
        "Missing expected columns in the source tab:\n"
        + "\n".join(f"  - {c}" for c in missing)
        + "\n\nAvailable columns:\n"
        + "\n".join(f"  - {c}" for c in sorted(headers))
    )
ignored = [c for c in headers if c not in COLUMN_MAPPING]
if ignored:
    print("Source columns not used: " + ", ".join(ignored))

df = raw.select(*[f.col(f"`{src}`").alias(tgt) for src, tgt in COLUMN_MAPPING.items()])
source_row_count = df.count()

# ---- Trim text; blank and placeholder values (n.a., -, none) become null ----
amount_like = set(AMOUNT_COLUMNS + WHOLE_DOLLAR_COLUMNS)   # a lone '-' means zero in these, handled below
for c in df.columns:
    trimmed = f.trim(f.col(c))
    keep_dash = c in amount_like
    is_blank = (trimmed == "") | (f.lower(trimmed).isin(*[p for p in PLACEHOLDERS if not (keep_dash and p == "-")]))
    df = df.withColumn(c, f.when(is_blank, f.lit(None)).otherwise(trimmed))

# ---- Cast ----
for c in DATE_COLUMNS:
    df = df.withColumn(c, to_date(c))
for c in RATE_COLUMNS:
    df = df.withColumn(c, to_double(c, percent_aware=True))
for c in AMOUNT_COLUMNS:
    df = df.withColumn(c, to_double(c, dash_is_zero=True))
for c in WHOLE_DOLLAR_COLUMNS:   # whole dollars as BIGINT (avoids scientific notation)
    df = df.withColumn(c, f.round(to_double(c, dash_is_zero=True)).cast("bigint"))
df = df.withColumn("months_remaining", to_double("months_remaining"))
df = df.withColumn("tranche", f.coalesce(f.expr("cast(try_cast(tranche as double) as int)"), f.lit(1)))   # null tranche = 1
for c in FLAG_COLUMNS:
    df = df.withColumn(c, yes_no_flag(c))

print(f"Source rows read: {source_row_count:,}")

# COMMAND ----------

# DBTITLE 1,Calculated columns and month-end snapshots
# Step 4: Calculated columns and month-end snapshots

# Instrument types are contract-level: fill blanks from the other rows of the same contract and date.
w_contract = Window.partitionBy("contract_id", "as_of_date")
for c in ("primary_instrument_type", "sub_instrument_type"):
    df = df.withColumn(c, f.coalesce(f.col(c), f.first(c, ignorenulls=True).over(w_contract)))
df = df.filter(~f.coalesce(f.col("primary_instrument_type").isin(EXCLUDED_PRIMARY_TYPES), f.lit(False)))

# sec_id (Empyrean SecID) and cost_center_id for borrowings come from the lookup
df = df.join(id_lookup_df, on="contract_id", how="left")
df = df.withColumn("cost_center_source", f.when(f.col("cost_center_id").isNotNull(), f.lit("LOOKUP")))

# Calendar attributes; keep only month-end snapshots (as_of_date = last business day of its month)
dim_dates_df = spark.table(DIM_DATES_TABLE).select(
    f.col("Date").alias("dim_date"),
    f.col("Last_Business_Day_Of_Month").alias("last_business_day_of_month"),
    f.col("Quarter_Year").alias("quarter_year"),
    f.col("End_of_Month").alias("end_of_month"),
)
df = (
    df.join(dim_dates_df, df["as_of_date"] == dim_dates_df["dim_date"], "left")
      .drop("dim_date")
      .filter(f.col("as_of_date") == f.col("last_business_day_of_month"))
      .drop("last_business_day_of_month")
)

# Maturity bucket
days = f.col("days_to_maturity")
bucket = f.when(days.isNull(), f.lit(NO_MATURITY_LABEL))
for label, lo, hi in MATURITY_BUCKETS:
    cond = f.lit(True)
    if lo is not None:
        cond = cond & (days >= lo)
    if hi is not None:
        cond = cond & (days <= hi)
    bucket = bucket.when(cond, f.lit(label))
df = df.withColumn("days_to_maturity", f.datediff(f.col("maturity_date"), f.col("as_of_date")))
df = df.withColumn("maturity_bucket", bucket)

is_brokered = f.col("primary_instrument_type") == "Brokered Deposit"
is_cd = (f.col("sub_instrument_type") == "Brokered CD") | f.col("product_type").contains("Brokered CD")
broker_prefix = (
    f.when(f.col("product_type") == "Brokered Term NMD", f.lit("BrokTerm"))
    .when(f.col("product_type") == "Brokered NMD", f.lit("BrokNMD"))
    .when(is_cd, f.lit("BrokCD"))
)
broker_whlsefndg_id = f.concat_ws("-", broker_prefix, f.col("contract_id"), f.col("tranche").cast("string"))

df = df.withColumns({
    "deposit_flag": f.when(is_brokered, f.lit("TRUE")).otherwise(f.lit("FALSE")),
    "whlsefndg_id": f.coalesce(f.when(is_brokered & broker_prefix.isNotNull(), broker_whlsefndg_id), f.col("sec_id")),
    "counterparty_type": (
        f.when(
            f.col("product_type").isin(
                "Adjustable Rate Credit", "Daily Rate Credit",
                "Fixed Rate Advance", "Floating Rate Advance", "Fed Funds Purchased",
            ),
            f.lit("Government Sponsored Entity"),
        ).when(is_brokered, f.lit("Retail"))
    ),
    "issue_currency": f.lit("USD"),
    "optionality_type": f.when(f.col("first_call_date").isNull(), f.lit(None)).otherwise(f.lit("Call")),
    "settlement_type": f.lit("Bilateral"),
    "secured_flag": f.when(f.col("primary_instrument_type") == "FHLB Advance", f.lit("TRUE")).otherwise(f.lit("FALSE")),
    "internal_flag": f.lit("FALSE"),
    "internal_transaction_flag": f.lit("FALSE"),
    "legal_entity_id": (
        f.when(f.col("cost_center_id").startswith("165"), f.lit("Bank"))
        .when(f.col("contract_id").startswith("PNFP-TPS-9"), f.lit("TPS"))
        .when(f.col("cost_center_id").startswith("D7B"), f.lit("HoldCo"))
        .when(f.col("cost_center_id").startswith("P81"), f.lit("TPS"))
        .when(f.col("cost_center_id").startswith("FCT"), f.lit("TPS"))
        .when(is_brokered, f.lit("Bank"))
    ),
    "benchmark": f.when(f.lower(f.col("rate_type")) == "fixed", f.lit(None)).otherwise(f.col("benchmark")),
    # GL fields are 'principal/fee' pairs: split into separate columns
    "gl_account_number": f.regexp_extract(f.col("balance_gl_raw"), r"^\s*([^/]+?)\s*(?:/|$)", 1),
    "gl_fee_account_number": f.regexp_extract(f.col("balance_gl_raw"), r"/\s*(.+?)\s*$", 1),
    "income_gl_account_number": f.regexp_extract(f.col("income_gl_raw"), r"^\s*([^/]+?)\s*(?:/|$)", 1),
    "income_fee_gl_account_number": f.regexp_extract(f.col("income_gl_raw"), r"/\s*(.+?)\s*$", 1),
})
for c in ("gl_account_number", "gl_fee_account_number", "income_gl_account_number", "income_fee_gl_account_number"):
    df = df.withColumn(c, f.when(f.col(c) == "", f.lit(None)).otherwise(f.col(c)))
df = df.drop("balance_gl_raw", "income_gl_raw")

# Internal (second leg) for Trust Preferred Securities: duplicate the rows, flagged internal and booked to HoldCo
tps_internal = (
    df.filter(f.col("product_type") == "Trust Preferred Securities")
      .withColumn("internal_flag", f.lit("TRUE"))
      .withColumn("internal_transaction_flag", f.lit("TRUE"))
      .withColumn("legal_entity_id", f.lit("HoldCo"))
)
df = df.unionByName(tps_internal)

df = df.withColumn("original_account_number", f.col("account_number"))

# COMMAND ----------

# DBTITLE 1,Brokered balances from the source systems (JH = PNFP stacked data, FIS = SNV deposits, SNV TPG = SNV brokered CDs)
# Step 5: Brokered balances from the source systems (JH = PNFP stacked data, FIS = SNV deposits, SNV TPG = SNV brokered CDs)
# Month-end rows only, limited to the as-of dates in this run.
bounds = df.agg(f.min("as_of_date").alias("lo"), f.max("as_of_date").alias("hi")).first()
src_lo, src_hi = bounds["lo"], bounds["hi"]
if src_lo is None:
    raise ValueError("No month-end rows were found in the source tab. Check the dates and the source tab name.")

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW pnfp_wf_deposits AS
SELECT
  ps.load_date asofdate,
  d.end_of_month AS eomdate,
  ps.account_type,
  ps.account_number,
  CONCAT(ps.account_type, ps.account_number) as accountid,
  ps.customer_name,
  ps.product_type acct_typ_cde,
  ps.product_description acct_typ_desc,
  '165.0008051' as entity_id,
  ps.balance,
  ps.date7_entered as open_date,
  ps.maturity_date7 AS maturity_date
FROM
  silver_prod.strategicfinance.pnfp_stacked_data ps
    JOIN {DIM_DATES_TABLE} d
      ON d.date = PS.LOAD_DATE
WHERE
  ps.product_type IN ('3Z', '4E', '3I', '7G', 'IM', '30', '6I', '7I', '9I', '28', '5I', '4I')
  AND ps.account_type <> 'L'
  AND (
    RIGHT(Product_Description, 1) = 'B'
    OR (ps.product_type IN ('4E', '3I', '3Z') AND account_type <> 'T')
  )
  AND d.date = d.last_business_day_of_month
  AND d.date BETWEEN '{src_lo}' AND '{src_hi}'
""")

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW snv_brokered_cds AS
SELECT
  d.last_business_day_of_month asofdate,
  d.end_of_month as eomdate,
  'C' as account_type,
  cusip as account_number,
  CONCAT('165', cusip) as accountid,
  CounterParty as customer_name,
  '092' as acct_typ_cde,
  'Brokered CD' as acct_typ_desc,

  '165.9998001' as entity_id,

  FairValue as balance,
  SettlementDate as open_date,
  StatedMaturityDate as maturity_date
FROM
  {TPG_POSITION_TABLE}
    JOIN {DIM_DATES_TABLE} d
      ON d.date = asofdate
WHERE
  asset_liability_flag = 'L'
  AND d.date = d.last_business_day_of_month
  AND d.date BETWEEN '{src_lo}' AND '{src_hi}'
""")

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW snv_wf_deposits AS
SELECT
  dm.prcs_dte as asofdate,
  d.end_of_month as eomdate,
  df.dp_cat_cde as account_type,
  df.acct_grp_nbr as account_number,
  CONCAT(df.PRCS_GRP_NBR, df.acct_grp_nbr) as accountid,
  df.ACCT_CUST_SHRT_NME customer_name,
  df.acct_typ_cde,
  df.acct_typ_desc,

  CONCAT(df.PRCS_GRP_NBR, '.', df.cst_cntr_nbr) as entity_id, 
  dm.lgr_bal_amt as balance,
  df.eff_dte as open_date, 
  CAST(NULL AS DATE) AS maturity_date
FROM
  silver_prod.dwdx1.tb_dp_dyy_c2_acct_scd_dim df
    JOIN silver_prod.dwdx1.tb_dp_sz9_dp_acct_d_fact dm
      ON dm.DW_PROD_SERV_ID = df.DW_PROD_SERV_ID
    JOIN {DIM_DATES_TABLE} d
      ON d.date = dm.PRCS_DTE
WHERE
  df.acct_typ_cde IN ('439', '440', '196', '194', '199')
  AND d.date = d.last_business_day_of_month
  AND d.date BETWEEN '{src_lo}' AND '{src_hi}'
""")

spark.sql("""
CREATE OR REPLACE TEMP VIEW brokered_src AS
SELECT 'PNFP' AS legacy_bank, 'JH' AS source, * FROM pnfp_wf_deposits
UNION ALL
SELECT 'SNV' AS legacy_bank, 'SNV TPG' AS source, * FROM snv_brokered_cds
UNION ALL
SELECT 'SNV' AS legacy_bank, 'FIS' AS source, * FROM snv_wf_deposits
""")
brokered_src = spark.table("brokered_src")

# COMMAND ----------

# DBTITLE 1,Allocate source-system balances to brokered deposit tranches
# Step 6: Allocate source-system balances to brokered deposit tranches
#   * A tranche with its own account number keeps it (account_assignment = OWN).
#   * A tranche 2+ with no account number takes the account number of tranche 2 (TRANCHE_2).
#   * Tranche 1 is never moved to another account.
#   * Fallback: if tranche 2 has no account either, the null tranches use tranche 1's account and tranche 1 joins that
#     split (TRANCHE_1_FALLBACK).
#   * The account is matched to the source systems (exact, or right 10 characters). If nothing matches, the row's CUSIP
#     is matched to the source account number instead (source_match_type = ACCOUNT or CUSIP).
#   * All tranches on one match key form a pool. The source balance fills the tranches in order, each up to its
#     max_balance (current_balance if max_balance is blank). The Brokered NMD tranche (BRK_NMD, FILL_LAST_PRODUCT_TYPE) is
#     filled last and takes whatever is left, even above its max, so each pool always adds back to the source balance.
#   * The source row's entity_id fills cost_center_id where the id lookup has none (cost_center_source = JH, FIS, SNV TPG).
#   * The source row's account type is kept as src_ac_tp_code and src_ac_tp_desc (used for the GL account in Step 7).
def allocate_brokered_balances(wf, src):
    is_brokered = f.coalesce(f.col("primary_instrument_type") == "Brokered Deposit", f.lit(False))
    brokered = wf.filter(is_brokered)
    other = wf.filter(~is_brokered)

    w_contract = Window.partitionBy("as_of_date", "contract_id")
    own = f.col("account_number")
    t2 = f.min(f.when(f.col("tranche") == 2, own)).over(w_contract)
    t1 = f.min(f.when(f.col("tranche") == 1, own)).over(w_contract)

    brokered = (
        brokered
        .withColumn("t2_account", t2)
        .withColumn("t1_account", t1)
        .withColumn(
            "account_assignment",
            f.when(own.isNotNull(), "OWN")
            .when(f.col("tranche") == 1, "NONE")
            .when(f.col("t2_account").isNotNull(), "TRANCHE_2")
            .when(f.col("t1_account").isNotNull(), "TRANCHE_1_FALLBACK")
            .otherwise("NONE"),
        )
        .withColumn(
            "allocation_account",
            f.when(f.col("account_assignment") == "OWN", own)
            .when(f.col("account_assignment") == "TRANCHE_2", f.col("t2_account"))
            .when(f.col("account_assignment") == "TRANCHE_1_FALLBACK", f.col("t1_account")),
        )
    )

    src_small = src.select(
        f.col("asofdate").alias("src_date"),
        f.col("account_number").alias("src_account"),
        f.col("source").alias("src_source"),
        f.col("entity_id").alias("src_entity"),
        f.col("acct_typ_cde").cast("string").alias("src_type_code"),
        f.col("acct_typ_desc").cast("string").alias("src_type_desc"),
        f.col("balance").cast("decimal(28,2)").alias("src_bal"),
    )

    def source_totals(keys, key_col, condition, prefix):
        """Source balance, systems and entity for each (as_of_date, key) that matches source rows by the condition."""
        return (
            keys.alias("k")
            .join(src_small.alias("s"), f.expr(condition), "inner")
            .groupBy(f.col("k.as_of_date").alias("as_of_date"), f.col(f"k.{key_col}").alias(key_col))
            .agg(
                f.sum("s.src_bal").alias(f"{prefix}_bal"),
                f.sort_array(f.collect_set("s.src_source")).alias(f"{prefix}_sources"),
                f.min("s.src_entity").alias(f"{prefix}_entity"),
                f.min(f.struct("s.src_type_code", "s.src_type_desc")).alias(f"{prefix}_type"),
            )
        )

    # 1) Match on the account number
    keys_acct = brokered.filter(f.col("allocation_account").isNotNull()).select("as_of_date", "allocation_account").distinct()
    by_account = source_totals(
        keys_acct, "allocation_account",
        "s.src_date = k.as_of_date AND "
        "(s.src_account = k.allocation_account OR right(s.src_account, 10) = k.allocation_account)",
        "acct",
    )
    brokered = brokered.join(by_account, on=["as_of_date", "allocation_account"], how="left")

    # 2) Rows the account did not match: try the CUSIP
    keys_cusip = brokered.filter(f.col("acct_bal").isNull() & f.col("cusip").isNotNull()).select("as_of_date", "cusip").distinct()
    by_cusip = source_totals(keys_cusip, "cusip", "s.src_date = k.as_of_date AND s.src_account = k.cusip", "cusip")
    brokered = brokered.join(by_cusip, on=["as_of_date", "cusip"], how="left")

    from_account = f.col("acct_bal").isNotNull()
    brokered = (
        brokered
        .withColumn("source_match_type", f.when(from_account, "ACCOUNT").when(f.col("cusip_bal").isNotNull(), "CUSIP"))
        .withColumn("source_balance", f.coalesce(f.col("acct_bal"), f.col("cusip_bal")))
        .withColumn("src_sources", f.when(from_account, f.col("acct_sources")).otherwise(f.col("cusip_sources")))
        .withColumn("src_entity", f.when(from_account, f.col("acct_entity")).otherwise(f.col("cusip_entity")))
        .withColumn("src_type", f.when(from_account, f.col("acct_type")).otherwise(f.col("cusip_type")))
        .withColumn("src_ac_tp_code", f.col("src_type.src_type_code"))
        .withColumn("src_ac_tp_desc", f.col("src_type.src_type_desc"))
        .withColumn("source_match_key", f.when(f.col("source_match_type") == "CUSIP", f.col("cusip")).otherwise(f.col("allocation_account")))
        .withColumn(
            "source_system_name",
            f.when(f.col("src_sources").isNull() | (f.size("src_sources") == 0), "Manual")
            .when(f.size("src_sources") == 1, f.col("src_sources").getItem(0))
            .otherwise("Hybrid"),
        )
        # Brokered deposits are not in the id lookup: the matched source row's entity_id is the cost center.
        .withColumn(
            "cost_center_source",
            f.when(f.col("cost_center_id").isNotNull(), f.col("cost_center_source"))
            .when(f.col("src_entity").isNotNull(), f.col("source_system_name")),
        )
        .withColumn("cost_center_id", f.coalesce(f.col("cost_center_id"), f.col("src_entity")))
    )

    # Fill the tranches in order, each up to its max_balance. The Brokered NMD tranche is last and takes the remainder.
    w_pool = Window.partitionBy("as_of_date", "contract_id", "source_match_key")
    fills_last = f.coalesce(f.trim(f.col("product_type")) == FILL_LAST_PRODUCT_TYPE, f.lit(False)).cast("int")
    w_fill = w_pool.orderBy(fills_last, "tranche", "counterparty_name", "current_balance")
    w_before = w_fill.rowsBetween(Window.unboundedPreceding, -1)
    zero = f.lit(0).cast("decimal(28,2)")
    brokered = (
        brokered
        .withColumn("pool_rows", f.count(f.lit(1)).over(w_pool))
        .withColumn("rn", f.row_number().over(w_fill))
        .withColumn("cap", f.coalesce(f.col("max_balance"), f.col("current_balance"), f.lit(0)).cast("decimal(28,2)"))
        .withColumn("cap_before", f.coalesce(f.sum("cap").over(w_before), zero))
        .withColumn("room", f.col("source_balance") - f.col("cap_before"))   # source balance left after the earlier tranches are full
        .withColumn(
            "allocated_balance",
            f.when(f.col("source_balance").isNull(), f.lit(None).cast("decimal(28,2)"))
            .when(f.col("rn") == f.col("pool_rows"), f.greatest(f.col("room"), zero))
            .otherwise(f.greatest(f.least(f.col("cap"), f.col("room")), zero))
            .cast("decimal(28,2)"),
        )
        .withColumn("allocation_variance", f.col("allocated_balance") - f.col("current_balance").cast("decimal(28,2)"))
        .withColumn(
            "allocation_status",
            f.when(f.col("allocation_account").isNull() & f.col("source_balance").isNull(), "NO_ACCOUNT")
            .when(f.col("source_balance").isNull(), "NO_SOURCE_BALANCE")
            .otherwise("ALLOCATED"),
        )
        .withColumn("account_number", f.col("allocation_account"))   # original_account_number keeps the workbook value
        .drop("t2_account", "t1_account", "allocation_account", "pool_rows", "rn", "cap", "cap_before", "room", "src_sources", "src_entity", "src_type",
              "acct_bal", "acct_sources", "acct_entity", "acct_type", "cusip_bal", "cusip_sources", "cusip_entity", "cusip_type")
    )
    return other.unionByName(brokered, allowMissingColumns=True).withColumn(
        "source_system_name", f.coalesce(f.col("source_system_name"), f.lit("Manual"))
    )


df = allocate_brokered_balances(df, brokered_src)


# COMMAND ----------

# DBTITLE 1,Complete cost centers
# Step 7: Complete cost centers and GL accounts, fill legal entities and add level6_id, so nothing reaches the final table unmapped.
# cost_center_id, in order of precedence:
#   1. Fed Funds Purchased rule: FED_FUNDS_COST_CENTER (cost_center_source = FED_FUNDS_RULE)
#   2. the id lookup (LOOKUP)
#   3. the entity_id of the matched source account (JH, FIS, SNV TPG), applied in Step 6
#   4. the legacy bank's default (BANK_DEFAULT), listed in the validation warnings so it can be added to the id lookup
# Rows still without a cost center fail validation. legal_entity_id is filled from the cost center prefix where blank.
# gl_account_number:
#   1. Fed Funds Purchased rows use FED_FUNDS_GL
#   2. rows whose whlsefndg_id is in GL_BY_WHLSEFNDG_ID take that GL
#   3. rows whose account_number is in GL_BY_ACCOUNT take that GL
#   4. brokered rows whose matched source account type is in GL_BY_SOURCE_TYPE take that GL
#   5. everything else keeps the workbook GL
# The workbook GL stays in workbook_gl_account_number.
# level6_id comes from the GL table on gl_account_number.
DEFAULT_COST_CENTER = {"PNFP": "165.0008051", "SNV": "165.9998001"}
FED_FUNDS_TYPE = "Fed Funds Purchased"
FED_FUNDS_GL = "2321008"
FED_FUNDS_COST_CENTER = "165.0008051"
GL_BY_WHLSEFNDG_ID = {"BrokNMD-SNV-NMD-2-1": "2268035", "BrokNMD-SNV-NMD-3-1": "2268035", "BrokNMD-SNV-NMD-4-1": "2268035", "BrokNMD-SNV-NMD-7-1": "2268035", "BrokNMD-SNV-NMD-6-4": "2101509", "BrokTerm-SNV-NMD-6-1": "2101509", "BOR_498_4": "2410009", "BOR_509_8": "2410009", "BOR_513_9": "2410009"}   # whlsefndg_id -> GL account
# product_type -> (instrument_type_key, instrument_type_code). The hundreds digit is the primary instrument type:
# 1xx Brokered Deposit, 2xx FHLB Advance, 3xx Long-Term Debt, 4xx Fed Funds Purchased. Add a row here for any new product type.
INSTRUMENT_TYPES = {
    "Brokered NMD": (101, "BRK_NMD"),
    "Brokered Term NMD": (102, "BRK_TERM_NMD"),
    "Non-Callable Brokered CD": (103, "BRK_CD_NONCALL"),
    "Callable Brokered CD": (104, "BRK_CD_CALL"),
    "Daily Rate Credit": (201, "FHLB_DRC"),
    "Adjustable Rate Credit": (202, "FHLB_ARC"),
    "Fixed Rate Advance": (203, "FHLB_FIXED"),
    "Floating Rate Advance": (204, "FHLB_FLOAT"),
    "HoldCo Subordinated Debt": (301, "LTD_HC_SUB"),
    "HoldCo Senior Debt": (302, "LTD_HC_SR"),
    "Bank Subordinated Debt": (303, "LTD_BK_SUB"),
    "Bank Senior Debt": (304, "LTD_BK_SR"),
    "Trust Preferred Securities": (305, "LTD_TPS"),
    "Fed Funds Purchased": (401, "FED_FUNDS"),
}
# GL plug rows (contract_id ends in GL-Plug) balance the workbook to the GL and have no real product type.
# They get a key of their own: the primary type's hundreds digit + 99.
PLUG_INSTRUMENT_TYPES = {   # primary_instrument_type -> (instrument_type_key, instrument_type_code)
    "Brokered Deposit": (199, "BRK_GL_PLUG"),
    "FHLB Advance": (299, "FHLB_GL_PLUG"),
    "Long-Term Debt": (399, "LTD_GL_PLUG"),
}
GL_BY_ACCOUNT = {"1018426260": "2268035"}   # account_number -> GL account (leading zeros ignored)
GL_BY_SOURCE_TYPE = {   # source account type code (FIS acct_typ_cde, JH product type) -> GL account
    "439": "2101509", "440": "2268035", "194": "2101517", "196": "2101525", "199": "2268076",
    "3Z": "2101509", "4E": "2268035",
}

is_fed_funds = f.coalesce(f.col("primary_instrument_type") == FED_FUNDS_TYPE, f.lit(False))
bank_default = f.coalesce(*[f.when(f.col("legacy_bank") == bank, f.lit(cc)) for bank, cc in DEFAULT_COST_CENTER.items()])
filled_cost_center = f.when(is_fed_funds, f.lit(FED_FUNDS_COST_CENTER)).otherwise(f.coalesce(f.col("cost_center_id"), bank_default))
legal_entity_from_cost_center = (
    f.when(filled_cost_center.startswith("165"), f.lit("Bank"))
    .when(filled_cost_center.startswith("D7B"), f.lit("HoldCo"))
    .when(filled_cost_center.startswith("P81"), f.lit("TPS"))
    .when(filled_cost_center.startswith("FCT"), f.lit("TPS"))
)
is_gl_plug = f.coalesce(f.lower(f.col("contract_id")).endswith("gl-plug"), f.lit(False))
instrument_key = f.when(
    is_gl_plug,
    f.create_map(*[f.lit(x) for k, (key, code) in PLUG_INSTRUMENT_TYPES.items() for x in (k, key)])[f.col("primary_instrument_type")],
).otherwise(f.create_map(*[f.lit(x) for k, (key, code) in INSTRUMENT_TYPES.items() for x in (k, key)])[f.trim(f.col("product_type"))])
instrument_code = f.when(
    is_gl_plug,
    f.create_map(*[f.lit(x) for k, (key, code) in PLUG_INSTRUMENT_TYPES.items() for x in (k, code)])[f.col("primary_instrument_type")],
).otherwise(f.create_map(*[f.lit(x) for k, (key, code) in INSTRUMENT_TYPES.items() for x in (k, code)])[f.trim(f.col("product_type"))])
gl_from_whlsefndg_id = f.create_map(*[f.lit(x) for pair in GL_BY_WHLSEFNDG_ID.items() for x in pair])[f.col("whlsefndg_id")]
gl_from_account = f.create_map(*[f.lit(x) for pair in GL_BY_ACCOUNT.items() for x in pair])[f.regexp_replace(f.trim(f.col("account_number")), "^0+", "")]
gl_from_source_type = f.create_map(*[f.lit(x) for pair in GL_BY_SOURCE_TYPE.items() for x in pair])[f.trim(f.col("src_ac_tp_code"))]

df = df.withColumns({
    "instrument_type_key": instrument_key.cast("int"),
    "instrument_type_code": instrument_code,
    "workbook_gl_account_number": f.col("gl_account_number"),
    "gl_account_number": f.when(is_fed_funds, f.lit(FED_FUNDS_GL)).otherwise(f.coalesce(gl_from_whlsefndg_id, gl_from_account, gl_from_source_type, f.col("gl_account_number"))),
    "cost_center_source": f.when(is_fed_funds, f.lit("FED_FUNDS_RULE"))
                           .when(f.col("cost_center_id").isNull() & bank_default.isNotNull(), f.lit("BANK_DEFAULT"))
                           .otherwise(f.col("cost_center_source")),
    "legal_entity_id": f.when(is_fed_funds, legal_entity_from_cost_center)
                        .otherwise(f.coalesce(f.col("legal_entity_id"), legal_entity_from_cost_center)),
    "cost_center_id": filled_cost_center,
})

gl_levels = (
    spark.table(GL_ACCOUNT_TABLE)
    .select(f.col("`Account ID`").cast("string").alias("gl_account_number"), f.col("`Level 6 ID`").cast("string").alias("level6_id"))
    .groupBy("gl_account_number").agg(f.min("level6_id").alias("level6_id"))
)
df = df.join(gl_levels, on="gl_account_number", how="left")


# COMMAND ----------

# DBTITLE 1,Final column set, in logical order. Materialized once so validation, the write and the report all see the same rows.
# Step 8: Final column set, in logical order. Materialized once so validation, the write and the report all see the same rows.
FINAL_COLUMNS = [
    # Lead columns
    "legacy_bank", "as_of_date", "whlsefndg_id", "sec_id", "contract_id", "tranche", "account_number", "cusip",
    # Instrument classification
    "instrument_type_key", "instrument_type_code", "deposit_flag", "primary_instrument_type", "sub_instrument_type", "product_type",
    # Entity
    "legal_entity_id", "cost_center_id",
    # Dates
    "end_of_month", "quarter_year", "issuance_date", "maturity_date", "days_to_maturity", "maturity_bucket",
    "months_remaining", "notice_date", "first_call_date",
    # Counterparty and account
    "counterparty_name", "counterparty_type", "original_account_number", "account_assignment",
    "source_system_name", "source_match_type", "source_match_key",
    # Contract terms
    "contractual_maturity_flag", "auto_roll_flag", "optionality_type", "settlement_type", "secured_flag", "issue_currency",
    # Rates
    "rate_type", "benchmark", "base_rate", "spread", "coupon_rate", "broker_fee_rate", "all_in_rate", "accrual_convention", "interest_payment_frequency",
    # Balances
    "current_balance", "source_balance", "allocation_flag", "contract_total_balance", "target_balance", "max_balance", "estimated_yield",
    # GL
    "gl_account_number", "level6_id",
    # Flags and metadata
    "internal_transaction_flag", "ingested_at", "source_file",
]

# How each column is derived. Written as column comments when the output is a table, and shown on the Column Guide tab of the run report.
COLUMN_COMMENTS = {
    "legacy_bank": "Legacy bank the contract belongs to (PNFP or SNV).\nFrom the workbook Entity column.",
    "as_of_date": "Month-end snapshot date (the last business day of the month).\nFrom the workbook As Of Date column; only month-end rows are kept.",
    "whlsefndg_id": "Wholesale funding id.\nBorrowings take sec_id from the id lookup (BOR_...). Brokered rows are built as BrokNMD, BrokTerm or BrokCD + contract_id + tranche.",
    "sec_id": "Empyrean SecID, used to tie rows back to Empyrean.\nFrom the id lookup (Step 2) by contract_id. Null for contracts not in the lookup, such as brokered deposits.",
    "contract_id": "Contract identifier, from the workbook Contract ID column.",
    "tranche": "Tranche number within the contract, from the workbook. A blank tranche is treated as 1.",
    "account_number": "Account the balance is matched on.\nThe workbook account; a brokered tranche with none takes tranche 2's account (tranche 1's if tranche 2 has none).",
    "cusip": "CUSIP from the workbook (n.a. and blanks are null).\nUsed to match a source row when the account number finds none.",
    "instrument_type_key": "Numeric tag for the instrument, looked up from product_type in INSTRUMENT_TYPES (Step 7).\n1xx brokered, 2xx FHLB, 3xx long-term debt, 4xx fed funds. GL plug rows are 199, 299 and 399.",
    "instrument_type_code": "Short text tag that goes with instrument_type_key (for example BRK_NMD, FHLB_FIXED).\nGL plug rows use BRK_GL_PLUG, FHLB_GL_PLUG or LTD_GL_PLUG.",
    "deposit_flag": "TRUE when primary_instrument_type is Brokered Deposit, otherwise FALSE.",
    "primary_instrument_type": "Top-level instrument: Brokered Deposit, FHLB Advance, Long-Term Debt or Fed Funds Purchased.\nFrom the workbook; a blank takes the value from the other rows of the same contract and date.",
    "sub_instrument_type": "Second-level instrument (for example Brokered NMD, FHLB Atlanta, Senior Debt).\nFrom the workbook; a blank takes the value from the other rows of the same contract and date.",
    "product_type": "Product within the instrument (for example Fixed Rate Advance, Brokered Term NMD), from the workbook Product Type column.",
    "legal_entity_id": "Legal entity that holds the contract: Bank, HoldCo or TPS.\nFrom the cost center prefix (165 Bank, D7B HoldCo, P81 and FCT TPS). Brokered rows are Bank; the internal TPS second leg is HoldCo.",
    "cost_center_id": "Cost center, which is the TM1 entity.\nOrder: Fed Funds Purchased rule (165.0008051), the id lookup, the entity_id of the matched source account, then the legacy bank default.",
    "end_of_month": "Calendar month-end for the as_of_date, from the date table. Used to match TM1.",
    "quarter_year": "Quarter label for the as_of_date (for example Q3 26), from the date table.",
    "issuance_date": "Date the contract was issued, from the workbook. Excel serial numbers and text dates are converted.",
    "maturity_date": "Contractual maturity date, from the workbook. Excel serial numbers and text dates are converted.",
    "days_to_maturity": "Days from as_of_date to maturity_date. Negative means past maturity; null when there is no maturity date.",
    "maturity_bucket": "Bucket of days_to_maturity: Past Maturity, 0-30 days, 31-90 days, 91-180 days, 181-365 days, 1-2 years, 2-3 years, 3-5 years, Over 5 years.\nNo Maturity Date when maturity_date is blank.",
    "months_remaining": "Months to maturity as calculated in the workbook.",
    "notice_date": "Notice date from the workbook (n.a. is null).",
    "first_call_date": "First call date from the workbook (n.a. is null).",
    "counterparty_name": "Counterparty as named in the workbook.",
    "counterparty_type": "Government Sponsored Entity for FHLB advances and Fed Funds Purchased, Retail for brokered deposits, otherwise null.\nSet by product_type in Step 4.",
    "original_account_number": "Account number exactly as the workbook had it, before any tranche 2 account was applied.\nNull where the workbook was blank.",
    "account_assignment": "Brokered rows only. OWN keeps the workbook account, TRANCHE_2 took tranche 2's account, TRANCHE_1_FALLBACK took tranche 1's.\nNull for other rows.",
    "source_system_name": "System that supplied the matched source balance: JH (PNFP), FIS (SNV deposits), SNV TPG (SNV brokered CDs), or Hybrid if more than one.\nManual when nothing matched or the row is not brokered.",
    "source_match_type": "How a brokered row matched a source row: ACCOUNT, or CUSIP when the account found nothing. Null when unmatched.",
    "source_match_key": "The account number or CUSIP the source match used. Tranches sharing a key share one source balance.",
    "contractual_maturity_flag": "TRUE or FALSE, from the workbook Contractual Maturity Yes or No.",
    "auto_roll_flag": "TRUE or FALSE, from the workbook Auto-roll @ Notice Yes or No. Null where the workbook is blank or n.a.",
    "optionality_type": "Call when a first_call_date exists, otherwise null.",
    "settlement_type": "Always Bilateral.",
    "secured_flag": "TRUE for FHLB Advances, otherwise FALSE.",
    "issue_currency": "Currency the instrument is issued in. Always USD.",
    "rate_type": "Fixed or Variable, from the workbook Rate Type column.",
    "benchmark": "Benchmark rate for variable contracts (for example SOFR, FFEFF), from the workbook. Null for fixed.",
    "base_rate": "Benchmark rate, from the workbook. Percent text such as 3.87% is converted to 0.0387.",
    "spread": "Spread over the benchmark, from the workbook. Percent text is converted to a decimal.",
    "coupon_rate": "Coupon rate, from the workbook. Percent text is converted to a decimal.",
    "broker_fee_rate": "Broker fee rate for brokered CDs, from the workbook Broker Fee (CD only) column. Percent text is converted to a decimal; null for other products.",
    "all_in_rate": "All-in rate including any broker fee, from the workbook. Percent text is converted to a decimal.",
    "accrual_convention": "Day count (for example Act/360, 30/360), from the workbook.",
    "interest_payment_frequency": "How often interest is paid (for example Monthly, At Maturity), from the workbook.",
    "current_balance": "Balance used for reporting, in dollars.\nBrokered rows with a source match take their allocated balance: the source balance filled into the tranches up to each max_balance, with the Brokered NMD tranche last.\nEvery other row keeps the workbook Principal Balance.",
    "source_balance": "Balance on the matched source account (JH, FIS or SNV TPG) before it is split across tranches. Null when there is no match.",
    "allocation_flag": "TRUE when current_balance came from the source allocation.\nFALSE for brokered rows with no source match (the workbook balance is kept). Null for other rows.",
    "contract_total_balance": "Total balance of the whole contract, from the workbook Contract Balance column, in dollars.",
    "target_balance": "Target balance, from the workbook Target column, in dollars.",
    "max_balance": "Maximum balance, from the workbook Max column, in dollars. The allocation fills each tranche up to this.",
    "estimated_yield": "Estimated yield from the workbook. Percent text is converted to a decimal.",
    "gl_account_number": "Balance sheet GL account.\nOrder: Fed Funds Purchased rule (2321008), GL_BY_WHLSEFNDG_ID, GL_BY_ACCOUNT, source account type for brokered rows (GL_BY_SOURCE_TYPE), then the first GL in the workbook Balance GL.",
    "level6_id": "Level 6 ID of gl_account_number, from the GL reference table.",
    "internal_transaction_flag": "TRUE on the duplicate second leg created for Trust Preferred Securities (booked to HoldCo), otherwise FALSE.\nThe run report leaves TRUE rows out of the recon and maturity schedule.",
    "ingested_at": "Timestamp of the run that wrote the row.",
    "source_file": "Path of the workbook the row came from.",
}
if set(COLUMN_COMMENTS) != set(FINAL_COLUMNS):
    raise ValueError(f"COLUMN_COMMENTS and FINAL_COLUMNS differ: {sorted(set(COLUMN_COMMENTS) ^ set(FINAL_COLUMNS))}")

df = (
    df.withColumn("ingested_at", f.current_timestamp())
      .withColumn("source_file", f.lit(file_location))
      # current_balance rule: brokered rows with a source match take the allocated balance, every other row keeps the workbook balance
      .withColumn("workbook_current_balance", f.col("current_balance"))
      .withColumn("current_balance", f.coalesce(f.col("allocated_balance"), f.col("current_balance").cast("decimal(28,2)")))
      .withColumn("allocation_flag", f.when(f.col("allocation_status") == "ALLOCATED", f.lit("TRUE"))
                                      .when(f.col("allocation_status").isin("NO_SOURCE_BALANCE", "NO_ACCOUNT"), f.lit("FALSE")))
)
if len(df.columns) != len(set(df.columns)):
    raise ValueError("Duplicate column names in the final table.")

# full_df keeps every working column for validation; final_df is the table that is written.
full_df = spark.createDataFrame(df.collect(), df.schema)
final_df = full_df.select(*FINAL_COLUMNS)
print(f"Final table: {final_df.count():,} rows, {len(final_df.columns)} columns")

# COMMAND ----------

# DBTITLE 1,Validation. Hard failures stop the run before anything is written; warnings are listed in the run report.
# Step 9: Validation. Hard failures stop the run before anything is written; warnings are listed in the run report.
hard_failures = []
validation_warnings = []

stats = full_df.agg(
    f.count(f.lit(1)).alias("rows"),
    f.sum(f.when(f.col("whlsefndg_id").isNull(), 1).otherwise(0)).alias("null_whlsefndg_id"),
    f.sum(f.when(f.col("legal_entity_id").isNull(), 1).otherwise(0)).alias("null_legal_entity"),
    f.sum(f.when(f.col("instrument_type_key").isNull(), 1).otherwise(0)).alias("null_instrument_type"),
    f.sum(f.when(f.col("primary_instrument_type").isNull(), 1).otherwise(0)).alias("null_instrument"),
    f.sum(f.when(f.col("current_balance").isNull(), 1).otherwise(0)).alias("null_balance"),
    f.sum(f.when(f.col("maturity_date").isNull(), 1).otherwise(0)).alias("null_maturity"),
    f.sum(f.when(f.col("original_account_number").rlike("^[0-9.]+[Ee][+-]?[0-9]+$"), 1).otherwise(0)).alias("sci_notation_accounts"),
    f.sum(f.when(f.col("allocation_status") == "NO_SOURCE_BALANCE", 1).otherwise(0)).alias("no_source_balance"),
    f.sum(f.when(f.col("allocation_status") == "NO_ACCOUNT", 1).otherwise(0)).alias("no_account"),
    f.sum(f.when(f.col("cost_center_id").isNull(), 1).otherwise(0)).alias("null_cost_center"),
    f.sum(f.when(f.col("cost_center_source") == "BANK_DEFAULT", 1).otherwise(0)).alias("bank_default_cost_center"),
    f.sum(f.when(f.col("level6_id").isNull(), 1).otherwise(0)).alias("no_level6"),
    f.sum(f.when(~f.col("gl_account_number").eqNullSafe(f.col("workbook_gl_account_number"))
                 & (f.col("primary_instrument_type") != FED_FUNDS_TYPE), 1).otherwise(0)).alias("gl_changed"),
    f.sum(f.when(f.col("account_assignment") == "TRANCHE_1_FALLBACK", 1).otherwise(0)).alias("tranche_1_fallback"),
    f.sum(f.when((f.col("allocation_status") == "ALLOCATED") & f.col("max_balance").isNotNull()
                 & (f.col("allocated_balance") > f.col("max_balance").cast("decimal(28,2)")), 1).otherwise(0)).alias("over_max"),
).first()

if stats["rows"] == 0:
    hard_failures.append("The final table has no rows.")

# Every row needs an instrument type key, so it can be tagged.
if stats["null_instrument_type"]:
    untagged = [f"{r[0]} / {r[1]}" for r in full_df.filter(f.col("instrument_type_key").isNull()).select("product_type", "contract_id").distinct().limit(15).collect()]
    hard_failures.append(f"{stats['null_instrument_type']:,} rows have no instrument type key (product_type / contract: {', '.join(str(u) for u in untagged)}). Add the product type to INSTRUMENT_TYPES in Step 7.")

# Nothing may be unmapped: every row needs a cost center and a legal entity.
if stats["null_cost_center"] or stats["null_legal_entity"]:
    unmapped = [r[0] for r in full_df.filter(f.col("cost_center_id").isNull() | f.col("legal_entity_id").isNull())
                .select("contract_id").distinct().limit(15).collect()]
    hard_failures.append(
        f"{stats['null_cost_center']:,} rows have no cost center and {stats['null_legal_entity']:,} have no legal entity "
        f"(contracts: {', '.join(str(u) for u in unmapped)}). Add them to the id lookup or to DEFAULT_COST_CENTER."
    )
if stats["bank_default_cost_center"]:
    defaulted = [r[0] for r in full_df.filter(f.col("cost_center_source") == "BANK_DEFAULT")
                 .select("contract_id").distinct().limit(15).collect()]
    validation_warnings.append(
        f"{stats['bank_default_cost_center']:,} rows had no cost center in the id lookup or the source systems, so the legacy bank "
        f"default was used (contracts: {', '.join(str(d) for d in defaulted)}). Add them to the id lookup to set it explicitly."
    )

unmapped_types = [r[0] for r in full_df.filter(f.col("src_ac_tp_code").isNotNull() & ~f.col("src_ac_tp_code").isin(*GL_BY_SOURCE_TYPE.keys()))
                  .select("src_ac_tp_code").distinct().limit(15).collect()]
if unmapped_types:
    validation_warnings.append(
        f"source account types with no GL mapping (the workbook GL was kept): {', '.join(str(t) for t in unmapped_types)}"
    )

# Each allocated account must add back to its source balance exactly.
pool_breaks = (
    full_df.filter(f.col("allocation_status") == "ALLOCATED")
    .groupBy("as_of_date", "contract_id", "source_match_key")
    .agg(f.max("source_balance").alias("src"), f.sum("allocated_balance").alias("alloc"))
    .filter(f.abs(f.col("src") - f.col("alloc")) > 0.005)
)
n_breaks = pool_breaks.count()
if n_breaks:
    hard_failures.append(f"{n_breaks} allocated account(s) do not add back to the source balance.")

dup_ids = (
    full_df.filter((f.col("internal_flag") == "FALSE") & f.col("whlsefndg_id").isNotNull())
    .groupBy("as_of_date", "whlsefndg_id").count().filter("count > 1").count()
)

checks = [
    ("null_whlsefndg_id", "rows have no whlsefndg_id (borrowings missing from the id lookup, such as repo or fed funds)"),
    ("null_instrument", "rows have no primary_instrument_type"),
    ("null_balance", "rows have no current_balance"),
    ("null_maturity", "rows have no maturity_date (bucketed as 'No Maturity Date')"),
    ("sci_notation_accounts", "account numbers look like scientific notation (digits may be lost in the workbook)"),
    ("no_source_balance", "brokered rows have an account but no matching source balance"),
    ("no_account", "brokered rows have no account to allocate against"),
    ("no_level6", "rows have a GL account that is not in the GL table (no level6_id)"),
    ("gl_changed", "brokered rows got a different GL from the source account type than the workbook gave"),
    ("tranche_1_fallback", "rows used the tranche 1 account because tranche 2 has none"),
    ("over_max", "brokered rows were allocated more than their max_balance (the last filled tranche takes any remainder)"),
]
for key, text in checks:
    if stats[key]:
        validation_warnings.append(f"{stats[key]:,} {text}")
if dup_ids:
    validation_warnings.append(f"{dup_ids:,} whlsefndg_id value(s) appear on more than one row (several accounts or counterparties on one tranche)")

print(f"Rows: {stats['rows']:,}   Source rows read: {source_row_count:,}")
for w in validation_warnings:
    print(f"  WARNING: {w}")
if hard_failures:
    raise ValueError("Validation failed, nothing was written:\n" + "\n".join(f"  - {h}" for h in hard_failures))
print("Validation passed.")

# COMMAND ----------

# DBTITLE 1,Write the output
# Step 10: Write the output
if view_type == "table":
    if write_mode == "append" and spark.catalog.tableExists(target_name):
        # Remove the as-of dates being loaded first so a rerun does not duplicate rows.
        loaded_dates = [r[0] for r in final_df.select("as_of_date").distinct().collect()]
        date_list = ", ".join(f"DATE'{d}'" for d in loaded_dates)
        spark.sql(f"DELETE FROM {target_name} WHERE as_of_date IN ({date_list})")
    writer = final_df.write.format("delta").mode(write_mode)
    if write_mode == "overwrite":
        writer = writer.option("overwriteSchema", "true")
    else:
        writer = writer.option("mergeSchema", "true")
    writer.saveAsTable(target_name)
else:
    if write_mode == "append":
        print("Note: append is not supported for temp views, the view will be replaced.")
    final_df.createOrReplaceTempView(target_name)

if view_type == "table":
    # Write the column derivations as comments on the table.
    try:
        spark.sql(f"COMMENT ON TABLE {target_name} IS 'Month-end wholesale funding: brokered deposits, FHLB advances, long-term debt and fed funds. See the column comments for how each column is derived.'")
        for col_name, comment in COLUMN_COMMENTS.items():
            safe = comment.replace("\\", "\\\\").replace("'", "\\'")
            spark.sql(f"ALTER TABLE {target_name} ALTER COLUMN `{col_name}` COMMENT '{safe}'")
        print(f"Column comments written for {len(COLUMN_COMMENTS)} columns.")
    except Exception as e:
        print(f"WARNING: the table was written but the column comments could not be: {e}")
else:
    print("Column comments are only written for tables. They are on the Column Guide tab of the run report.")

result_df = spark.table(target_name)
print(f"{view_type.title()} written: {target_name} ({environment}, {write_mode})")
print(f"Rows in target: {result_df.count():,}   Columns: {len(result_df.columns)}")

# COMMAND ----------

# DBTITLE 1,Run report (optional): Final Table, GL Recon with entities, Maturity Buckets, written to one Excel workbook
# Step 11: Run report (optional): Final Table, GL Recon with entities, Maturity Buckets, written to one Excel workbook
DEC = "decimal(28,2)"


def to_pandas(sdf):
    """Spark to pandas, with decimals as floats so Excel gets numbers."""
    cols = [f.col(c).cast("double").alias(c) if t.startswith("decimal") else f.col(c) for c, t in sdf.dtypes]
    return sdf.select(*cols).toPandas()


def excluded_pair(gl_col, entity_col):
    """True for the (GL account, entity) pairs in RECON_EXCLUDED_PAIRS."""
    hit = f.lit(False)
    for gl, entity in RECON_EXCLUDED_PAIRS:
        hit = hit | f.coalesce((gl_col.cast("string") == gl) & (entity_col.cast("string") == entity), f.lit(False))
    return hit


def build_recon(snap, report_dt):
    """Wholesale funding vs the TM1 trial balance: by GL account, by GL account + legacy bank, by GL account + entity (cost center)."""
    names = (
        spark.table(GL_ACCOUNT_TABLE)
        .select(f.col("`Account ID`").cast("string").alias("gl_account"), f.col("`Account Desc`").alias("gl_account_name"),
                f.col("`Z_Account Attributes.ReconGroup`").alias("recon_group"))
        .groupBy("gl_account").agg(f.first("gl_account_name").alias("gl_account_name"), f.first("recon_group").alias("recon_group"))
    )
    tm1 = (
        spark.table(TM1_TABLE)
        .filter(
            (f.col("Versions") == "ACTUAL") & (f.col("DataSources") == "TotalCur")
            & (f.col("FinanceMeasures") == "EndBal") & f.col("Periods").endswith("YTD")
            & (f.col("Accounts") != '2328128')
        )
        .filter(~excluded_pair(f.col("Accounts"), f.col("Entities")))
        # TM1 is stored at calendar month-end, so match on EOMONTH(report date) (e.g. 2026-10-30 -> 2026-10-31)
        .filter(f.to_date(f.col("prcs_dte").cast("string"), "yyyyMMdd") == f.last_day(f.lit(report_dt)))
        .select(
            f.col("Accounts").cast("string").alias("gl_account"),
            f.col("Entities").cast("string").alias("entity_id"),
            # TM1 carries the legacy bank in Projects; "No Project" means none
            f.when(f.trim(f.regexp_replace(f.col("projects").cast("string"), "No Project", "")) == "", f.lit("(no project)"))
             .otherwise(f.trim(f.regexp_replace(f.col("projects").cast("string"), "No Project", ""))).alias("legacy_bank"),
            f.col("VValue").cast("double").alias("gl_value"),
        )
    )
    wf = snap.filter(f.col("gl_account_number").isNotNull() & ~excluded_pair(f.col("gl_account_number"), f.col("cost_center_id"))).select(
        f.col("gl_account_number").alias("gl_account"),
        f.coalesce(f.col("cost_center_id"), f.lit("(unmapped)")).alias("entity_id"),
        f.coalesce(f.col("legacy_bank"), f.lit("(unmapped)")).alias("legacy_bank"),
        f.col("legal_entity_id"),
        f.col("current_balance").cast(DEC).alias("wf_balance"),
    )
    status = lambda v: f.when(f.abs(v) <= RECON_TOLERANCE, "MATCH").otherwise("VARIANCE")

    # By GL account, with the TM1 entities that carry the balance
    wf_acct = wf.groupBy("gl_account").agg(
        f.sum("wf_balance").alias("wf_balance"),
        f.concat_ws(", ", f.sort_array(f.collect_set("legal_entity_id"))).alias("wf_legal_entities"),
    )
    gl_acct = tm1.groupBy("gl_account").agg(
        f.sum("gl_value").cast(DEC).alias("gl_balance"),
        f.concat_ws(", ", f.sort_array(f.collect_set(f.when(f.col("gl_value") != 0, f.col("entity_id"))))).alias("gl_entities"),
    )
    by_account = (
        wf_acct.join(gl_acct, "gl_account", "left").join(names, "gl_account", "left")
        .withColumn("gl_balance", f.coalesce(f.col("gl_balance"), f.lit(0).cast(DEC)))
        .withColumn("variance", f.col("wf_balance") - f.col("gl_balance"))
        .withColumn("status", status(f.col("variance")))
        .select("gl_account", "gl_account_name", "recon_group", "wf_balance", "gl_balance",
                "variance", "status", "wf_legal_entities", "gl_entities")
        .orderBy(f.abs(f.col("variance")).desc(), "gl_account")
    )

    # By GL account and legacy bank: only the GL accounts that wholesale funding maps to
    wf_bank = wf.groupBy("gl_account", "legacy_bank").agg(
        f.sum("wf_balance").alias("wf_balance"),
        f.concat_ws(", ", f.sort_array(f.collect_set("legal_entity_id"))).alias("wf_legal_entities"),
    )
    gl_bank = (
        tm1.join(wf.select("gl_account").distinct(), "gl_account", "left_semi")
        .groupBy("gl_account", "legacy_bank").agg(
            f.sum("gl_value").cast(DEC).alias("gl_balance"),
            f.concat_ws(", ", f.sort_array(f.collect_set(f.when(f.col("gl_value") != 0, f.col("entity_id"))))).alias("gl_entities"),
        )
    )
    zero = f.lit(0).cast(DEC)
    by_bank = (
        wf_bank.join(gl_bank, ["gl_account", "legacy_bank"], "full_outer").join(names, "gl_account", "left")
        .withColumn("wf_balance", f.coalesce(f.col("wf_balance"), zero))
        .withColumn("gl_balance", f.coalesce(f.col("gl_balance"), zero))
        .withColumn("variance", f.col("wf_balance") - f.col("gl_balance"))
        .withColumn("status", status(f.col("variance")))
        .select("gl_account", "gl_account_name", "recon_group", "legacy_bank", "wf_balance", "gl_balance",
                "variance", "status", "wf_legal_entities", "gl_entities")
        .orderBy("gl_account", "legacy_bank")
    )

    # By GL account and entity: only the GL accounts that wholesale funding maps to
    wf_ent = wf.groupBy("gl_account", "entity_id").agg(
        f.sum("wf_balance").alias("wf_balance"),
        f.concat_ws(", ", f.sort_array(f.collect_set("legal_entity_id"))).alias("wf_legal_entities"),
    )
    gl_ent = (
        tm1.join(wf.select("gl_account").distinct(), "gl_account", "left_semi")
        .groupBy("gl_account", "entity_id").agg(f.sum("gl_value").cast(DEC).alias("gl_balance"))
    )
    by_entity = (
        wf_ent.join(gl_ent, ["gl_account", "entity_id"], "full_outer").join(names, "gl_account", "left")
        .withColumn("wf_balance", f.coalesce(f.col("wf_balance"), zero))
        .withColumn("gl_balance", f.coalesce(f.col("gl_balance"), zero))
        .withColumn("variance", f.col("wf_balance") - f.col("gl_balance"))
        .withColumn("status", status(f.col("variance")))
        .select("gl_account", "gl_account_name", "recon_group", "entity_id", "wf_legal_entities", "wf_balance",
                "gl_balance", "variance", "status")
        .orderBy("gl_account", "entity_id")
    )
    return by_account, by_bank, by_entity


def build_maturity(snap):
    """Balance by maturity bucket, and by instrument / product across buckets."""
    bal = f.col("current_balance").cast(DEC)
    yld = f.when(f.col("estimated_yield").isNotNull(), bal)
    summary = (
        snap.groupBy("maturity_bucket").agg(
            f.count(f.lit(1)).alias("rows"),
            f.sum(bal).alias("balance"),
            f.sum(f.col("estimated_yield") * yld).alias("_yield_x_bal"),
            f.sum(yld).alias("_yield_bal"),
        )
        .withColumn("wtd_avg_est_yield", f.when(f.col("_yield_bal") != 0, f.col("_yield_x_bal") / f.col("_yield_bal")))
        .drop("_yield_x_bal", "_yield_bal")
    )
    summary = to_pandas(summary).set_index("maturity_bucket").reindex(BUCKET_ORDER).fillna({"rows": 0, "balance": 0.0})
    summary["rows"] = summary["rows"].astype(int)
    total = summary["balance"].sum()
    summary["pct_of_total"] = summary["balance"] / total if total else 0.0
    summary = summary.reset_index()
    summary.loc[len(summary)] = ["Total", int(summary["rows"].sum()), total, None, 1.0 if total else 0.0]

    detail = to_pandas(snap.groupBy("primary_instrument_type", "product_type", "maturity_bucket").agg(f.sum(bal).alias("balance")))
    detail[["primary_instrument_type", "product_type"]] = detail[["primary_instrument_type", "product_type"]].fillna("(blank)")
    matrix = detail.pivot_table(index=["primary_instrument_type", "product_type"], columns="maturity_bucket",
                                values="balance", aggfunc="sum", fill_value=0.0)
    matrix = matrix.reindex(columns=BUCKET_ORDER, fill_value=0.0)
    matrix["Total"] = matrix.sum(axis=1)
    matrix = matrix.reset_index()
    totals = matrix.drop(columns=["primary_instrument_type", "product_type"]).sum()
    matrix.loc[len(matrix)] = ["Total", ""] + totals.tolist()
    return summary, matrix


def format_table(ws, pdf, header_row):
    """Header style, number formats and column widths for a table written with index=False."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    fill = PatternFill("solid", fgColor="1F3864")
    for j, name in enumerate(pdf.columns, start=1):
        cell = ws.cell(row=header_row, column=j)
        cell.fill, cell.font = fill, Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(wrap_text=True, vertical="center")

        lname = str(name).lower()
        first = pdf[name].dropna().iloc[0] if pdf[name].notna().any() else None
        if lname == "pct_of_total":
            fmt = "0.0%"
        elif lname == "days_to_maturity":
            fmt = "0"
        elif lname == "months_remaining":
            fmt = "0.0"
        elif pdf[name].dtype.kind == "f" and any(k in lname for k in ("rate", "spread", "yield")):
            fmt = "0.000%"
        elif pdf[name].dtype.kind == "f":
            fmt = "#,##0.00"
        elif pdf[name].dtype.kind in "iu" and "balance" in lname:
            fmt = "#,##0"
        elif hasattr(first, "hour"):
            fmt = "yyyy-mm-dd hh:mm:ss"
        elif hasattr(first, "year") and hasattr(first, "month"):
            fmt = "yyyy-mm-dd"
        else:
            fmt = None

        longest = max([len(str(name))] + [len(str(v)) for v in pdf[name].head(200)])
        ws.column_dimensions[get_column_letter(j)].width = min(max(longest + 2, 10), 40)
        if fmt:
            for i in range(len(pdf)):
                ws.cell(row=header_row + 1 + i, column=j).number_format = fmt


if not run_report:
    print("Run report skipped (Create Run Report = no).")
else:
    available_dates = [r[0] for r in final_df.select("as_of_date").distinct().orderBy("as_of_date").collect()]
    report_dt = report_date_input or available_dates[-1]
    if report_dt not in available_dates:
        raise ValueError(f"Report Date {report_dt} is not in this run. Available: {', '.join(str(d) for d in available_dates)}")

    snap = final_df.filter(f.col("as_of_date") == f.lit(report_dt))
    basis = snap.filter(f.col("internal_transaction_flag") == "FALSE") if REPORT_EXCLUDE_INTERNAL else snap
    table_sdf = final_df if report_table_scope == "all dates" else snap
    report_warnings = list(validation_warnings)

    sheets = {}   # sheet name -> list of (pandas frame, title or None)
    print(f"Run report for {report_dt}")

    # Final table
    final_pdf = to_pandas(table_sdf.orderBy("as_of_date", "legacy_bank", "contract_id", "tranche"))
    sheets["Final Table"] = final_pdf
    print("\nFinal table:")
    display(table_sdf.orderBy("as_of_date", "legacy_bank", "contract_id", "tranche"))

    # GL recon
    recon_account_pdf = recon_bank_pdf = recon_entity_pdf = None
    try:
        by_account, by_bank, by_entity = build_recon(basis, report_dt)
        recon_account_pdf, recon_bank_pdf, recon_entity_pdf = to_pandas(by_account), to_pandas(by_bank), to_pandas(by_entity)
        print("\nGL recon by account:")
        display(by_account)
        print("\nGL recon by legacy bank:")
        display(by_bank)
        n_bank_var = int((recon_bank_pdf["status"] == "VARIANCE").sum())
        if n_bank_var:
            report_warnings.append(f"GL recon by legacy bank: {n_bank_var} GL account and bank combination(s) differ from TM1 by more than ${RECON_TOLERANCE:,.2f}")
        n_var = int((recon_account_pdf["status"] == "VARIANCE").sum())
        if n_var:
            report_warnings.append(f"GL recon: {n_var} GL account(s) differ from TM1 by more than ${RECON_TOLERANCE:,.2f}")
        if recon_account_pdf["gl_balance"].eq(0).all():
            report_warnings.append("GL recon: no TM1 balances were found for this date, check the filters and the report date")
    except Exception as e:   # keep the rest of the report if the GL tables are unavailable
        report_warnings.append(f"GL recon was not built: {str(e).splitlines()[0]}")
        print(f"GL recon was not built: {e}")

    # Maturity buckets
    maturity_summary_pdf, maturity_matrix_pdf = build_maturity(basis)
    print("\nMaturity buckets:")
    display(maturity_summary_pdf)

    # Balance bridge: Final Table total to the GL Recon wf_balance total (report date)
    cb = f.col("current_balance").cast(DEC)
    def total(sdf, col=cb):
        return float(sdf.agg(f.sum(col)).first()[0] or 0)
    total_all = total(snap)
    internal_leg = total_all - total(basis)
    no_gl = total(basis.filter(f.col("gl_account_number").isNull()))
    excluded = total(basis.filter(f.col("gl_account_number").isNotNull() & excluded_pair(f.col("gl_account_number"), f.col("cost_center_id"))))
    expected_recon = total_all - internal_leg - no_gl - excluded
    recon_total = float(recon_account_pdf["wf_balance"].sum()) if recon_account_pdf is not None else None
    bridge = [
        ("Bridge: Final Table total (current_balance, report date)", f"${total_all:,.2f}"),
        ("Bridge: less internal TPS second leg", f"${internal_leg:,.2f}"),
        ("Bridge: less rows with no GL account", f"${no_gl:,.2f}"),
        ("Bridge: less excluded recon pairs", f"${excluded:,.2f}"),
        ("Bridge: equals expected GL Recon wf_balance", f"${expected_recon:,.2f}"),
        ("Bridge: GL Recon wf_balance as reported", f"${recon_total:,.2f}" if recon_total is not None else "(recon not built)"),
    ]
    if report_table_scope == "all dates":
        bridge.append(("Bridge: note", "The Final Table tab holds all dates, so summing it includes other months. The bridge is for the report date only."))
    if recon_total is not None and abs(recon_total - expected_recon) > RECON_TOLERANCE:
        report_warnings.append(f"GL Recon wf_balance (${recon_total:,.2f}) does not equal the Final Table total less the bridge items (${expected_recon:,.2f})")
    print("\nBalance bridge (report date):")
    for label, value in bridge:
        print(f"  {label.replace('Bridge: ', ''):<60}{value}")

    # Run info
    cc_counts = {(r[0] or "(none)"): r[1] for r in full_df.filter(f.col("as_of_date") == f.lit(report_dt)).groupBy("cost_center_source").count().collect()}
    info = [
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Environment", environment),
        ("Output", f"{view_type}: {target_name} ({write_mode})"),
        ("Source file", file_location),
        ("Source tab", source_sheet),
        ("Report date", str(report_dt)),
        ("As-of dates in run", f"{available_dates[0]} to {available_dates[-1]} ({len(available_dates)} month-ends)"),
        ("Final table tab", report_table_scope),
        ("Rows in final table", f"{final_df.count():,}"),
        ("Rows on report date", f"{snap.count():,}"),
        ("Recon tolerance", f"${RECON_TOLERANCE:,.2f}"),
        ("Recon and maturity basis", "external rows only (internal_transaction_flag = FALSE)" if REPORT_EXCLUDE_INTERNAL else "all rows"),
        ("Recon exclusions", "; ".join(["TM1 GL 2328128 (repo)"] + [f"GL {g} at entity {e}" for g, e in RECON_EXCLUDED_PAIRS])),
        ("Cost center source (report date)", ", ".join(f"{k} {v:,}" for k, v in sorted(cc_counts.items()))),
    ] + bridge + [("Warning", w) for w in report_warnings]
    info_pdf = pd.DataFrame(info, columns=["Item", "Value"])

    os.makedirs(report_folder, exist_ok=True)
    report_path = os.path.join(report_folder, f"{report_file_name}_{report_dt:%Y%m%d}.xlsx")
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        info_pdf.to_excel(writer, sheet_name="Run Info", index=False)
        format_table(writer.sheets["Run Info"], info_pdf, 1)
        writer.sheets["Run Info"].column_dimensions["B"].width = 100

        guide_pdf = pd.DataFrame({"column": FINAL_COLUMNS, "how it is derived": [COLUMN_COMMENTS[c].replace("\n", " ") for c in FINAL_COLUMNS]})
        guide_pdf.to_excel(writer, sheet_name="Column Guide", index=False)
        format_table(writer.sheets["Column Guide"], guide_pdf, 1)
        writer.sheets["Column Guide"].column_dimensions["B"].width = 140

        final_pdf.to_excel(writer, sheet_name="Final Table", index=False)
        format_table(writer.sheets["Final Table"], final_pdf, 1)
        writer.sheets["Final Table"].freeze_panes = "B2"

        if recon_account_pdf is not None:
            recon_account_pdf.to_excel(writer, sheet_name="GL Recon", index=False)
            format_table(writer.sheets["GL Recon"], recon_account_pdf, 1)
            writer.sheets["GL Recon"].freeze_panes = "A2"
            recon_bank_pdf.to_excel(writer, sheet_name="GL Recon by Bank", index=False)
            format_table(writer.sheets["GL Recon by Bank"], recon_bank_pdf, 1)
            writer.sheets["GL Recon by Bank"].freeze_panes = "A2"
            recon_entity_pdf.to_excel(writer, sheet_name="GL Recon by Entity", index=False)
            format_table(writer.sheets["GL Recon by Entity"], recon_entity_pdf, 1)
            writer.sheets["GL Recon by Entity"].freeze_panes = "A2"

        maturity_summary_pdf.to_excel(writer, sheet_name="Maturity Buckets", index=False, startrow=2)
        ws = writer.sheets["Maturity Buckets"]
        ws.cell(row=1, column=1).value = f"Maturity bucket schedule as of {report_dt} (current balance, days from as-of date)"
        format_table(ws, maturity_summary_pdf, 3)
        matrix_row = 3 + len(maturity_summary_pdf) + 3
        ws.cell(row=matrix_row - 1, column=1).value = "By instrument and product"
        maturity_matrix_pdf.to_excel(writer, sheet_name="Maturity Buckets", index=False, startrow=matrix_row - 1)
        format_table(ws, maturity_matrix_pdf, matrix_row)
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 28

    print(f"\nRun report saved: {report_path}")

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from silver_prod.p021.tm1_financetrialbalancepbi where prcs_dte = '20261031'