-- Databricks notebook source
-- MAGIC %md
-- MAGIC # HQLA & Collateral
-- MAGIC Securities positions from TPG, with HQLA level and pledge code attached, pledged and unpledged side by side.
-- MAGIC
-- MAGIC | Object | What it is |
-- MAGIC |---|---|
-- MAGIC | `finance.reference.hqla_level_map`, `pledge_code_map` | Already created (levels and pledge codes) |
-- MAGIC | `finance.reference.lcr_account_map`, `lcr_safekeeping_map` | Account and safekeeping lookups from mappings.xlsx. **Fill in `legacy_bank` on the account map.** |
-- MAGIC | `finance.staging.tpg_*` | Thin views over the four TPG tables. Switching dev to prod is one edit per view. |
-- MAGIC | `finance.staging.hqla_collateral_positions` | One row per CUSIP, account and pledgee, month ends only |
-- MAGIC | `finance.staging.hqla_collateral_summary` | By date, level, pledge type and bank: pledged and unpledged market value in one row |
-- MAGIC
-- MAGIC Dates: TPG reports on the calendar month end (`eomdate`). `asofdate` is the last business day of that month, so it lines up with deposits, wholesale funding and the GL.

-- COMMAND ----------

-- DBTITLE 1,Lookup: lcr_account_map
-- legacy_bank is blank on purpose. Enter PNFP or SNV for each account (the source does not say).
-- treasury_flag comes from your sheet. lcr_securities only counts accounts flagged 'Yes' toward HQLA.
CREATE OR REPLACE VIEW finance.reference.lcr_account_map AS
SELECT
  *,
  regexp_replace(upper(trim(customer_account)), ' +', ' ') AS match_key
FROM VALUES
  -- customer_account, portfolio, subsidiary, treasury_flag, intent, legacy_bank
  ('165 PINB AFS', '165 PINB AFS', 'Investments - AFS', 'Yes', 'AFS', NULL),
  ('165 PINB HTM', '165 PINB HTM', 'Investments - HTM', 'Yes', 'HTM', NULL),
  ('AFS - PINNACLE BANK', '165 PINB AFS', 'Investments - AFS', 'Yes', 'AFS', NULL),
  ('AFS - PINNACLE NC INVESTMENTS INC', 'P16 PINC AFS', 'NC Investment Subsidiay - AFS', 'Yes', 'AFS', NULL),
  ('AFS - PINNACLE TRUST CO', '154 PTC AFS', 'Synovus Trust Company', 'No', 'AFS', NULL),
  ('AFS-PINNACLE FINANCIAL PARTNERS HOLDINGS', 'P02 PINH', 'PNFP Holdings', 'No', 'AFS', NULL),
  ('AFS-PINNACLE FINANCIAL PARTNERS PROPERTIES', 'P03 PINP', 'PNFP Properties', 'No', 'AFS', NULL),
  ('APEX CAPTIVE INSURANCE CO', 'P85 ACIC', 'APEX Captive Insurance', 'No', 'AFS', NULL),
  ('HTM - PINNACLE BANK', '165 PINB HTM', 'Investments - HTM', 'Yes', 'HTM', NULL),
  ('HTM -PINNACLE NC INVESTMENTS INC', 'P16 PINC HTM', 'NC Investment Subsidiay - HTM', 'Yes', 'HTM', NULL),
  ('P16 PINC AFS', 'P16 PINC AFS', 'NC Investment Subsidiay - AFS', 'Yes', 'AFS', NULL),
  ('P16 PINC HTM', 'P16 PINC HTM', 'NC Investment Subsidiay - HTM', 'Yes', 'HTM', NULL),
  ('AFS - PINNACLE FINANCIAL PARTNERS HOLDINGS', NULL, 'PNFP Holdings', 'No', 'AFS', NULL),
  ('AFS - PINNACLE FINANCIAL PARTNERS PROPERTIES', NULL, 'PNFP Properties', 'No', 'AFS', NULL),
  ('HTM - PINNACLE NC INVESTMENTS INC', NULL, 'NC Investment Subsidiay - HTM', 'Yes', 'HTM', NULL)
  AS t(customer_account, portfolio, subsidiary, treasury_flag, intent, legacy_bank)

-- COMMAND ----------

-- DBTITLE 1,Lookup: lcr_safekeeping_map
CREATE OR REPLACE VIEW finance.reference.lcr_safekeeping_map AS
SELECT
  *,
  regexp_replace(upper(trim(safekeeping_location)), ' +', ' ') AS match_key
FROM VALUES
  ('Federal Home Loan Bank of Atlanta', 'FHLB-ATL'),
  ('Federal Home Loan Bank of Cincinnati', 'FHLB-CIN'),
  ('FEDERAL RESERVE BANK', 'FRB'),
  ('Pinnacle Trust & Investment Services - BONY', 'PTIS-BNY'),
  ('Raymond James - Repo', 'RJ-Repo'),
  ('Raymond James Collateral', 'RJ-Collateral'),
  ('Raymond James Financial', 'RJF'),
  ('Wells Fargo', 'Wells Fargo'),
  ('WELLS FARGO CME', 'Wells Fargo-CME'),
  ('Wilmington Trust', 'Wilmington Trust')
  AS t(safekeeping_location, short_name)

-- COMMAND ----------

-- DBTITLE 1,Source layer: tpg_pledged
-- The four TPG tables are read through these views. To move from dev to prod, change the table name here only.
CREATE OR REPLACE VIEW finance.staging.tpg_pledged AS
SELECT * FROM silver_dev.tpg_reports.pledgee

-- COMMAND ----------

-- DBTITLE 1,Source layer: tpg_pg91_book
CREATE OR REPLACE VIEW finance.staging.tpg_pg91_book AS
SELECT * FROM silver_dev.tpg_reports.pg91_pledges_to_pledgee_portfolio_consolidate

-- COMMAND ----------

-- DBTITLE 1,Source layer: tpg_pg92_unpledged
CREATE OR REPLACE VIEW finance.staging.tpg_pg92_unpledged AS
SELECT * FROM silver_dev.tpg_reports.pg92_unpledged_securities

-- COMMAND ----------

-- DBTITLE 1,Source layer: tpg_position_report
CREATE OR REPLACE VIEW finance.staging.tpg_position_report AS
SELECT * FROM silver_dev.tpg_reports.position_report

-- COMMAND ----------

-- DBTITLE 1,View: hqla_collateral_positions
-- Changes from the original query:
--   no hard coded date: every calendar month end from the start date
--   LEFT JOINs to pg91 and position_report, so a missing match no longer drops a position
--   HQLA level from hqla_level_map (Exact beats Prefix, longest prefix wins), pledge code from pledge_code_map
--   anything unmatched shows as UNMAPPED instead of disappearing
CREATE OR REPLACE VIEW finance.staging.hqla_collateral_positions AS
WITH month_ends AS (
  SELECT d.date AS eomdate, d.last_business_day_of_month AS asofdate
  FROM finance.default.dim_dates d
  WHERE d.date = d.end_of_month
    AND d.date >= DATE'2026-01-01'
),
pg91_book AS (
  SELECT trim(Cusip) AS Cusip, As_Of_Date, CustomerAccount, PledgeName,
         SUM(PledgedBookValue) AS PledgedBookValue
  FROM finance.staging.tpg_pg91_book
  GROUP BY 1, 2, 3, 4
),
unpledged AS (
  SELECT
    me.asofdate,
    me.eomdate,
    trim(u.Cusip)            AS Cusip,
    u.SecurityDesc           AS CusipDescription,
    u.CustomerName           AS CustomerAccount,
    pr.CustomerAccountNumber AS Portfolio,
    'Unpledged'              AS PledgeStatus,
    CAST(NULL AS STRING)     AS PledgedToInstitution,
    u.SafeKeepingLocation    AS SafekeepingLocation,
    u.StatedMaturityDate     AS MaturityDate,
    u.CpnRate                AS CouponRate,
    u.UnpledgedAmount        AS OriginalPar,
    u.UnpledgedParValue      AS ParValue,
    u.UnpledgedBookValue     AS BookValue,
    u.UnpledgedMarketValue   AS FairValue,
    CAST(0 AS DECIMAL(24,2))                                   AS PledgedMarketValue,
    CAST(COALESCE(u.UnpledgedMarketValue, 0) AS DECIMAL(24,2)) AS UnpledgedMarketValue
  FROM finance.staging.tpg_pg92_unpledged u
  JOIN month_ends me
    ON u.as_of_date = me.eomdate
  LEFT JOIN finance.staging.tpg_position_report pr
    ON u.TransNo = pr.PositionID AND u.as_of_date = pr.AsOfDate
  WHERE u.HoldingCompName = 'PINNACLE FINANCIAL PARTNERS INC'
),
pledged AS (
  SELECT
    me.asofdate,
    me.eomdate,
    trim(g.Cusip)              AS Cusip,
    g.CusipDescription,
    g.CustomerAccount,
    g.CustomerAccount          AS Portfolio,
    'Pledged'                  AS PledgeStatus,
    g.PledgedToInstitutionName AS PledgedToInstitution,
    g.SafekeepingLocationName  AS SafekeepingLocation,
    g.MaturityDate,
    g.CouponRate,
    g.PledgedOriginalPar       AS OriginalPar,
    g.PledgeParValue           AS ParValue,
    b.PledgedBookValue         AS BookValue,
    g.PledgeFairValue          AS FairValue,
    CAST(COALESCE(g.PledgeFairValue, 0) AS DECIMAL(24,2)) AS PledgedMarketValue,
    CAST(0 AS DECIMAL(24,2))                              AS UnpledgedMarketValue
  FROM finance.staging.tpg_pledged g
  JOIN month_ends me
    ON g.AsOfDate = me.eomdate
  LEFT JOIN pg91_book b
    ON trim(g.Cusip) = b.Cusip
   AND g.AsOfDate = b.As_Of_Date
   AND g.CustomerAccount = b.CustomerAccount
   AND g.PledgedToInstitutionName = b.PledgeName
),
pos AS (
  SELECT * FROM pledged
  UNION ALL
  SELECT * FROM unpledged
),
desc_level AS (
  SELECT CusipDescription, hqla_level, gl_group, security_name2, match_type
  FROM (
    SELECT
      d.CusipDescription, m.hqla_level, m.gl_group, m.security_name2, m.match_type,
      ROW_NUMBER() OVER (PARTITION BY d.CusipDescription ORDER BY m.match_rank, m.match_len DESC) AS rn
    FROM (SELECT DISTINCT CusipDescription FROM pos) d
    LEFT JOIN finance.reference.hqla_level_map m
      ON (m.match_type = 'Exact'
          AND regexp_replace(upper(trim(d.CusipDescription)), ' +', ' ') = m.match_key)
      OR (m.match_type = 'Prefix'
          AND startswith(regexp_replace(upper(trim(d.CusipDescription)), ' +', ' '), m.match_key)
          -- single letter prefixes (T, B) only match when a space follows, so an unlisted TEXAS or BOSTON muni
          -- is no longer read as a Treasury. Anything this blocks shows up in Check 1 as UNMAPPED.
          AND (length(m.match_key) > 1
               OR substr(regexp_replace(upper(trim(d.CusipDescription)), ' +', ' '), 2, 1) = ' '))
  ) x
  WHERE rn = 1
),
enriched AS (
  SELECT
    p.*,
    COALESCE(l.hqla_level, 'UNMAPPED')  AS hqla_level,
    l.gl_group,
    l.security_name2,
    l.match_type                        AS level_match_type,
    CASE WHEN p.PledgeStatus = 'Pledged' THEN COALESCE(pm.pledged_inst, 'UNMAPPED') END AS pledged_inst,
    CASE WHEN p.PledgeStatus = 'Pledged' THEN COALESCE(pm.pledge_group, 'UNMAPPED') END AS pledge_group,
    am.subsidiary,
    am.treasury_flag,
    am.intent,
    COALESCE(am.legacy_bank, 'UNASSIGNED') AS legacy_bank,
    sk.short_name                          AS safekeeping_short_name
  FROM pos p
  LEFT JOIN desc_level l
    ON p.CusipDescription IS NOT DISTINCT FROM l.CusipDescription
  LEFT JOIN finance.reference.pledge_code_map pm
    ON regexp_replace(upper(trim(p.PledgedToInstitution)), ' +', ' ') = pm.match_key
  LEFT JOIN finance.reference.lcr_account_map am
    ON regexp_replace(upper(trim(p.CustomerAccount)), ' +', ' ') = am.match_key
  LEFT JOIN finance.reference.lcr_safekeeping_map sk
    ON regexp_replace(upper(trim(p.SafekeepingLocation)), ' +', ' ') = sk.match_key
)
SELECT
  e.*,
  CASE
    WHEN e.PledgeStatus <> 'Pledged' THEN NULL
    WHEN e.pledge_group = 'PSE'      THEN 'PSE'
    ELSE e.pledged_inst
  END AS pledgee_type,
  -- Pledges that belong in Outflow - Secured. FHLB advances, FHLB LOC, swap margin and unmapped pledgees are left out.
  (e.PledgeStatus = 'Pledged'
   AND (e.pledge_group = 'PSE'
        OR e.pledged_inst IN ('ATI', 'Bankruptcy', 'Collateral Swap', 'CorpTrust', 'PNB Trust', 'Repo', 'STC'))) AS secured_funding_flag
FROM enriched e

-- COMMAND ----------

-- DBTITLE 1,View: hqla_collateral_summary
-- Pledged and unpledged market value side by side, by date, bank, level and pledge type.
CREATE OR REPLACE VIEW finance.staging.hqla_collateral_summary AS
SELECT
  asofdate,
  eomdate,
  legacy_bank,
  PledgeStatus                       AS pledge_status,
  COALESCE(pledgee_type, 'Unpledged') AS pledgee_type,
  pledged_inst,
  pledge_group,
  secured_funding_flag,
  hqla_level,
  treasury_flag,
  subsidiary,
  SUM(PledgedMarketValue)            AS pledged_mv,
  SUM(UnpledgedMarketValue)          AS unpledged_mv,
  COUNT(*)                           AS position_count
FROM finance.staging.hqla_collateral_positions
GROUP BY ALL

-- COMMAND ----------

select
  eomdate,
  pledge_group,
  hqla_level,
  SUM(pledged_mv),
  sum(unpledged_mv),
  treasury_flag
from
  finance.staging.hqla_collateral_summary
--   treasury_flag = 'Y'
    group by all 

-- COMMAND ----------

-- DBTITLE 1,Check 1: unmapped HQLA levels (review, largest first)
SELECT asofdate, CusipDescription, SUM(PledgedMarketValue + UnpledgedMarketValue) AS market_value
FROM finance.staging.hqla_collateral_positions
WHERE hqla_level = 'UNMAPPED'
GROUP BY ALL
ORDER BY market_value DESC

-- COMMAND ----------

-- DBTITLE 1,Check 2: unmapped pledgees (review, largest first)
SELECT asofdate, PledgedToInstitution, SUM(PledgedMarketValue) AS pledged_mv
FROM finance.staging.hqla_collateral_positions
WHERE pledged_inst = 'UNMAPPED'
GROUP BY ALL
ORDER BY pledged_mv DESC

-- COMMAND ----------

-- DBTITLE 1,Check 3: accounts missing from lcr_account_map
SELECT asofdate, CustomerAccount, SUM(PledgedMarketValue + UnpledgedMarketValue) AS market_value
FROM finance.staging.hqla_collateral_positions
WHERE treasury_flag IS NULL
GROUP BY ALL
ORDER BY market_value DESC

-- COMMAND ----------

-- DBTITLE 1,Check 4: levels decided by a Prefix match (review the short prefixes T, B, FR)
SELECT CusipDescription, hqla_level, SUM(PledgedMarketValue + UnpledgedMarketValue) AS market_value
FROM finance.staging.hqla_collateral_positions
WHERE level_match_type = 'Prefix'
  AND asofdate = (SELECT MAX(asofdate) FROM finance.staging.hqla_collateral_positions)
GROUP BY ALL
ORDER BY market_value DESC

-- COMMAND ----------

-- DBTITLE 1,Check 5: pledged to FHLB by month end (the $1B question)
SELECT asofdate, pledged_inst, hqla_level, SUM(PledgedMarketValue) AS pledged_mv
FROM finance.staging.hqla_collateral_positions
WHERE pledged_inst IN ('FHLBLOC', 'FHLB - ATL ADV')
GROUP BY ALL
ORDER BY asofdate, pledged_inst, hqla_level

-- COMMAND ----------

-- DBTITLE 1,Check 6: market value by month end and status
SELECT asofdate, PledgeStatus, COUNT(*) AS positions, SUM(PledgedMarketValue + UnpledgedMarketValue) AS market_value
FROM finance.staging.hqla_collateral_positions
GROUP BY ALL
ORDER BY asofdate, PledgeStatus