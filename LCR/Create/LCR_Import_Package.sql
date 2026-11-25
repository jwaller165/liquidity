-- Databricks notebook source
-- MAGIC %md
-- MAGIC # LCR Import Package
-- MAGIC Builds the five Power BI imports (CoreDeposits, WholesaleFunding, Secured, Securities, GeneralLedger) and the shared dimensions. Every object is a view, so the notebook can be rerun at any time.
-- MAGIC
-- MAGIC | Object | Feeds |
-- MAGIC |---|---|
-- MAGIC | `finance.staging.lcr_line_def`, `lcr_class_map`, `lcr_gl_section_map` | Shared dimensions. Change a mapping here and every import follows. |
-- MAGIC | `finance.staging.lcr_core_deposits` | CoreDeposits |
-- MAGIC | `finance.staging.lcr_wholesale_funding` | WholesaleFunding (brokered, FHLB, Fed funds, long-term debt) |
-- MAGIC | `finance.staging.lcr_general_ledger` and `lcr_gl_recon` | GeneralLedger and the recon |
-- MAGIC | `finance.staging.lcr_secured` | Secured (collateral by pledgee and level, plus deposit balance by pledgee) |
-- MAGIC | `finance.staging.lcr_securities` | Securities (HQLA categories). Both read `hqla_collateral_summary` from the HQLA & Collateral notebook, so run that notebook first. |
-- MAGIC
-- MAGIC Start date for every view is `DATE'2026-01-01'`. Change it in each view if you need more history.

-- COMMAND ----------


SELECT * FROM silver_dev.tpg_reports_pnfp.pg91_pledges_to_pledgee_portfolio_consolidate

-- COMMAND ----------

-- DBTITLE 1,Dimension: lcr_line_def
CREATE OR REPLACE VIEW finance.staging.lcr_line_def AS
SELECT * FROM VALUES
    -- line_number, section_number, section_name, line_name, schedule_ref, line_type
    ('1.01', '1', 'Retail Deposits', 'Stable Retail - Insured (NMD and TD >30d)', '32.a.1', 'OUTFLOW'),
    ('1.02', '1', 'Retail Deposits', 'Stable Retail - Insured TDs <=30d', '32.a.1.LT30', 'OUTFLOW'),
    ('1.03', '1', 'Retail Deposits', 'Other Retail - Uninsured (NMD and TD >30d)', '32.a.2', 'OUTFLOW'),
    ('1.04', '1', 'Retail Deposits', 'Other Retail - Uninsured TDs <=30d', '32.a.2.LT30', 'OUTFLOW'),
    ('2.01', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'Consumer ICS - Insured (NMD and >30d)', '32.g.5', 'OUTFLOW'),
    ('2.02', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'CDARS maturing <=30d - Insured', '32.g.5.LT30', 'OUTFLOW'),
    ('2.03', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'Consumer ICS - Uninsured (NMD and >30d)', '32.g.6', 'OUTFLOW'),
    ('2.04', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'Consumer ICS - Uninsured <=30d', '32.g.6.LT30', 'OUTFLOW'),
    ('2.05', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'Insured Affiliated Sweeps (BDSP)', '32.g.7', 'OUTFLOW'),
    ('2.06', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'Brokered CDs maturing <=30d', '32.g.1', 'OUTFLOW'),
    ('2.07', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'Brokered CDs maturing >30d', '32.g.2', 'OUTFLOW'),
    ('2.08', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'Brokered NMD', '32.g.3', 'OUTFLOW'),
    ('2.09', '2', 'Brokered, Reciprocal & Sweeps (Retail)', 'Brokered Term NMD', '32.g.3.Term', 'OUTFLOW'),
    ('3.01', '3', 'Unsecured Wholesale', 'Operational Commercial - Insured', '32.h.4 - Insured', 'OUTFLOW'),
    ('3.02', '3', 'Unsecured Wholesale', 'Operational Commercial - Uninsured', '32.h.4 - Uninsured', 'OUTFLOW'),
    ('3.03', '3', 'Unsecured Wholesale', 'Non-Operational Commercial - Insured (incl. excess operational)', '32.h.1.i', 'OUTFLOW'),
    ('3.04', '3', 'Unsecured Wholesale', 'Non-Operational Commercial - Uninsured (incl. excess operational)', '32.h.1.ii.A', 'OUTFLOW'),
    ('3.05', '3', 'Unsecured Wholesale', 'Wholesale TDs maturing <=30d', '32.h.1', 'OUTFLOW'),
    ('3.06', '3', 'Unsecured Wholesale', 'Insured TDs maturing >30d', '32.h.1.Insured', 'OUTFLOW'),
    ('3.07', '3', 'Unsecured Wholesale', 'Uninsured TDs maturing >30d', '32.h.1.Uninsured', 'OUTFLOW'),
    ('3.08', '3', 'Unsecured Wholesale', 'Commercial ICS - Reciprocal NMDs', '32.h.1.ii.B', 'OUTFLOW'),
    ('3.09', '3', 'Unsecured Wholesale', 'Commercial ICS - Reciprocal TDs <=30d', '32.h.1.ii.B', 'OUTFLOW'),
    ('3.10', '3', 'Unsecured Wholesale', 'Commercial ICS - Reciprocal TDs >30d', '32.h.1.ii.B', 'OUTFLOW'),
    ('3.11', '3', 'Unsecured Wholesale', 'Insured Sweep Wholesale', '32.h.1.ii.B', 'OUTFLOW'),
    ('3.12', '3', 'Unsecured Wholesale', 'Uninsured Sweep Wholesale', '32.h.1.ii.B', 'OUTFLOW'),
    ('3.13', '3', 'Unsecured Wholesale', 'Unsecured Portion of Secured Funding', '32.h', 'OUTFLOW'),
    ('3.14', '3', 'Unsecured Wholesale', 'Financial Sector Entity - Non-Operational (incl. FSE excess operational)', '32.h.2', 'OUTFLOW'),
    ('4.01', '4', 'Secured Funding', 'Secured - Level 1 collateral', '32.j.1.i', 'OUTFLOW'),
    ('4.02', '4', 'Secured Funding', 'Secured - Level 2A collateral', '32.j.1.ii', 'OUTFLOW'),
    ('4.03', '4', 'Secured Funding', 'Secured - Level 2B collateral', '32.j.1.iv', 'OUTFLOW'),
    ('4.04', '4', 'Secured Funding', 'Secured - Non-HQLA collateral', '32.j.1.vi', 'OUTFLOW'),
    ('4.05', '4', 'Secured Funding', 'FHLB Advances', 'TBD', 'OUTFLOW'),
    ('4.06', '4', 'Secured Funding', 'FHLB Advances maturing >30d (memo)', 'n/a', 'MEMO'),
    ('5.01', '5', 'Contractual Obligations & Collateral', 'Fed Funds Purchased', 'TBD', 'OUTFLOW'),
    ('5.02', '5', 'Contractual Obligations & Collateral', 'Debt Maturing <=30 Days (LTD)', 'TBD', 'OUTFLOW'),
    ('5.03', '5', 'Contractual Obligations & Collateral', 'Collateral Outflow', '32.f', 'OUTFLOW'),
    ('5.04', '5', 'Contractual Obligations & Collateral', 'Long-Term Debt maturing >30d (memo)', 'n/a', 'MEMO'),
    ('5.06', '5', 'Contractual Obligations & Collateral', 'Fed Funds Purchased maturing >30d (memo)', 'n/a', 'MEMO'),
    ('6.01', '6', 'Unfunded Commitments', 'Mortgage Commitments', '32.d', 'OUTFLOW'),
    ('6.02', '6', 'Unfunded Commitments', 'Retail Loan Commitments', '32.e.ii', 'OUTFLOW'),
    ('6.03', '6', 'Unfunded Commitments', 'Credit Facility - Commercial (Working Capital/Other)', '32.e.iii', 'OUTFLOW'),
    ('6.04', '6', 'Unfunded Commitments', 'Liquidity Facility - Commercial Customer', '32.e.iv', 'OUTFLOW'),
    ('6.05', '6', 'Unfunded Commitments', 'Credit or Liquidity Facility - Bank', '32.e.v', 'OUTFLOW'),
    ('6.06', '6', 'Unfunded Commitments', 'Credit Facility - Non-Bank Financial', '32.e.vi', 'OUTFLOW'),
    ('6.07', '6', 'Unfunded Commitments', 'Liquidity Facility - Non-Bank Financial', '32.e.vii', 'OUTFLOW'),
    ('6.08', '6', 'Unfunded Commitments', 'Liquidity Facility - SPEs', '32.e.viii', 'OUTFLOW'),
    ('7.01', '7', 'Inflows', 'Retail Loan Inflows', 'TBD', 'INFLOW'),
    ('7.02', '7', 'Inflows', 'Commercial Loan Inflows', 'TBD', 'INFLOW'),
    ('8.01', '8', 'Secured Deposit Balances', 'Secured deposits - PSE (balance, see Secured)', 'n/a', 'MEMO'),
    ('8.02', '8', 'Secured Deposit Balances', 'Secured deposits - Non-PSE (balance, see Secured)', 'n/a', 'MEMO'),
    ('9.99', '9', 'Review', 'Unclassified wholesale funding (review)', 'n/a', 'REVIEW')
  AS t(line_number, section_number, section_name, line_name, schedule_ref, line_type)

-- COMMAND ----------

-- DBTITLE 1,Dimension: lcr_class_map
-- rule SPLIT : op_balance goes to line_number_op, ledger_balance minus op_balance goes to line_number
-- rule LEDGER: all of the balance goes to line_number
CREATE OR REPLACE VIEW finance.staging.lcr_class_map AS
SELECT * FROM VALUES
    -- source_system, lcr_class, rule, line_number_op, line_number, entity_type, insurance_status, note
    ('deposits_reg', 'BrokeredNMDLT30', 'LEDGER', NULL, '2.08', 'Brokered', 'n/a', 'Extract has no insured flag; all treated as 32.g.3 (insured)'),
    ('deposits_reg', 'BrokeredTimeGT30', 'LEDGER', NULL, '2.07', 'Brokered', 'n/a', NULL),
    ('deposits_reg', 'BrokeredTimeLT30', 'LEDGER', NULL, '2.06', 'Brokered', 'n/a', NULL),
    ('deposits_reg', 'FSEOperationalInsured', 'SPLIT', '3.01', '3.14', 'FSE', 'Insured', 'op_balance to 3.01; remainder to FSE non-op 32.h.2. Confirm.'),
    ('deposits_reg', 'FSEOperationalUninsured', 'SPLIT', '3.02', '3.14', 'FSE', 'Uninsured', 'op_balance to 3.02; remainder to FSE non-op 32.h.2. Confirm.'),
    ('deposits_reg', 'FSEReciprocalNMD', 'LEDGER', NULL, '3.14', 'FSE', 'n/a', NULL),
    ('deposits_reg', 'FSEReciprocalTimeGT30', 'LEDGER', NULL, '3.14', 'FSE', 'n/a', NULL),
    ('deposits_reg', 'FSEReciprocalTimeLT30', 'LEDGER', NULL, '3.14', 'FSE', 'n/a', NULL),
    ('deposits_reg', 'FSETraditionalNMD', 'LEDGER', NULL, '3.14', 'FSE', 'n/a', NULL),
    ('deposits_reg', 'FSETraditionalTimeGT30', 'LEDGER', NULL, '3.14', 'FSE', 'n/a', NULL),
    ('deposits_reg', 'FSETraditionalTimeLT30', 'LEDGER', NULL, '3.14', 'FSE', 'n/a', NULL),
    ('deposits_reg', 'NFSEOperationalInsured', 'SPLIT', '3.01', '3.03', 'NFSE', 'Insured', 'op_balance to 3.01; remainder (excess) to 3.03'),
    ('deposits_reg', 'NFSEOperationalUninsured', 'SPLIT', '3.02', '3.04', 'NFSE', 'Uninsured', 'op_balance to 3.02; remainder (excess) to 3.04'),
    ('deposits_reg', 'RetailReciprocalInsuredNMD', 'LEDGER', NULL, '2.01', 'Retail', 'Insured', NULL),
    ('deposits_reg', 'RetailReciprocalInsuredTimeGT30', 'LEDGER', NULL, '2.01', 'Retail', 'Insured', NULL),
    ('deposits_reg', 'RetailReciprocalInsuredTimeLT30', 'LEDGER', NULL, '2.02', 'Retail', 'Insured', NULL),
    ('deposits_reg', 'RetailReciprocalUninsuredNMD', 'LEDGER', NULL, '2.03', 'Retail', 'Uninsured', 'Moved from Other Retail per prior workbook (32.g.6)'),
    ('deposits_reg', 'RetailReciprocalUninsuredTimeGT30', 'LEDGER', NULL, '2.03', 'Retail', 'Uninsured', 'Moved from Other Retail per prior workbook (32.g.6)'),
    ('deposits_reg', 'RetailReciprocalUninsuredTimeLT30', 'LEDGER', NULL, '2.04', 'Retail', 'Uninsured', 'Moved from Other Retail per prior workbook (32.g.6)'),
    ('deposits_reg', 'RetailTraditionalInsuredNMD', 'LEDGER', NULL, '1.01', 'Retail', 'Insured', NULL),
    ('deposits_reg', 'RetailTraditionalInsuredTimeGT30', 'LEDGER', NULL, '1.01', 'Retail', 'Insured', NULL),
    ('deposits_reg', 'RetailTraditionalInsuredTimeLT30', 'LEDGER', NULL, '1.02', 'Retail', 'Insured', NULL),
    ('deposits_reg', 'RetailTraditionalUninsuredNMD', 'LEDGER', NULL, '1.03', 'Retail', 'Uninsured', NULL),
    ('deposits_reg', 'RetailTraditionalUninsuredTimeGT30', 'LEDGER', NULL, '1.03', 'Retail', 'Uninsured', NULL),
    ('deposits_reg', 'RetailTraditionalUninsuredTimeLT30', 'LEDGER', NULL, '1.04', 'Retail', 'Uninsured', NULL),
    ('deposits_reg', 'SecuredNonPSE', 'LEDGER', NULL, '8.02', 'Secured', 'n/a', 'Feeds Outflow - Secured (recon only here)'),
    ('deposits_reg', 'SecuredPSE', 'LEDGER', NULL, '8.01', 'Secured', 'n/a', 'Feeds Outflow - Secured (recon only here)'),
    ('deposits_reg', 'WholesaleReciprocalInsuredNMD', 'LEDGER', NULL, '3.08', 'NFSE', 'Insured', NULL),
    ('deposits_reg', 'WholesaleReciprocalInsuredTimeGT30', 'LEDGER', NULL, '3.10', 'NFSE', 'Insured', NULL),
    ('deposits_reg', 'WholesaleReciprocalInsuredTimeLT30', 'LEDGER', NULL, '3.09', 'NFSE', 'Insured', NULL),
    ('deposits_reg', 'WholesaleReciprocalUninsuredNMD', 'LEDGER', NULL, '3.08', 'NFSE', 'Uninsured', NULL),
    ('deposits_reg', 'WholesaleReciprocalUninsuredTimeGT30', 'LEDGER', NULL, '3.10', 'NFSE', 'Uninsured', NULL),
    ('deposits_reg', 'WholesaleReciprocalUninsuredTimeLT30', 'LEDGER', NULL, '3.09', 'NFSE', 'Uninsured', NULL),
    ('deposits_reg', 'WholesaleTraditionalInsuredNMD', 'LEDGER', NULL, '3.03', 'NFSE', 'Insured', NULL),
    ('deposits_reg', 'WholesaleTraditionalInsuredTimeGT30', 'LEDGER', NULL, '3.06', 'NFSE', 'Insured', NULL),
    ('deposits_reg', 'WholesaleTraditionalInsuredTimeLT30', 'LEDGER', NULL, '3.05', 'NFSE', 'Insured', NULL),
    ('deposits_reg', 'WholesaleTraditionalUninsuredNMD', 'LEDGER', NULL, '3.04', 'NFSE', 'Uninsured', NULL),
    ('deposits_reg', 'WholesaleTraditionalUninsuredTimeGT30', 'LEDGER', NULL, '3.07', 'NFSE', 'Uninsured', NULL),
    ('deposits_reg', 'WholesaleTraditionalUninsuredTimeLT30', 'LEDGER', NULL, '3.05', 'NFSE', 'Uninsured', NULL),
    ('deposits_reg', 'BDSPLT30', 'LEDGER', NULL, '2.05', 'Brokered', 'Insured', 'BDSP sweep class. Maps to line 2.05 (32.g.7). Confirm the line.'),
    ('deposits_reg', 'SecuredPSENMD', 'LEDGER', NULL, '8.01', 'Secured', 'n/a', 'Feeds Outflow - Secured (balance only here)'),
    ('deposits_reg', 'SecuredPSETimeLT30', 'LEDGER', NULL, '8.01', 'Secured', 'n/a', 'Feeds Outflow - Secured (balance only here)'),
    ('deposits_reg', 'SecuredPSETimeGT30', 'LEDGER', NULL, '8.01', 'Secured', 'n/a', 'Feeds Outflow - Secured (balance only here)'),
    ('deposits_reg', 'SecuredNonPSENMD', 'LEDGER', NULL, '8.02', 'Secured', 'n/a', 'Feeds Outflow - Secured (balance only here)'),
    ('deposits_reg', 'SecuredNonPSETimeLT30', 'LEDGER', NULL, '8.02', 'Secured', 'n/a', 'Feeds Outflow - Secured (balance only here)'),
    ('deposits_reg', 'SecuredNonPSETimeGT30', 'LEDGER', NULL, '8.02', 'Secured', 'n/a', 'Feeds Outflow - Secured (balance only here)'),
    ('wholesalefunding', 'BrokeredNMD', 'LEDGER', NULL, '2.08', 'Brokered', 'n/a', 'Brokered NMD, any maturity bucket'),
    ('wholesalefunding', 'BrokeredTermNMDLT30', 'LEDGER', NULL, '2.06', 'Brokered', 'n/a', 'Term NMD maturing <=30d, treated like brokered CDs <=30d (100%).'),
    ('wholesalefunding', 'BrokeredTermNMDGT30', 'LEDGER', NULL, '2.09', 'Brokered', 'n/a', NULL),
    ('wholesalefunding', 'BrokeredCDLT30', 'LEDGER', NULL, '2.06', 'Brokered', 'n/a', NULL),
    ('wholesalefunding', 'BrokeredCDGT30', 'LEDGER', NULL, '2.07', 'Brokered', 'n/a', NULL),
    ('wholesalefunding', 'FHLBAdvanceLT30', 'LEDGER', NULL, '4.05', 'FHLB', 'n/a', NULL),
    ('wholesalefunding', 'FHLBAdvanceGT30', 'LEDGER', NULL, '4.06', 'FHLB', 'n/a', 'Memo line: outside the 30 day window'),
    ('wholesalefunding', 'FedFundsPurchasedLT30', 'LEDGER', NULL, '5.01', 'FedFunds', 'n/a', NULL),
    ('wholesalefunding', 'FedFundsPurchasedGT30', 'LEDGER', NULL, '5.06', 'FedFunds', 'n/a', 'Memo line: outside the 30 day window'),
    ('wholesalefunding', 'LTDSeniorLT30', 'LEDGER', NULL, '5.02', 'LTD', 'n/a', NULL),
    ('wholesalefunding', 'LTDSeniorGT30', 'LEDGER', NULL, '5.04', 'LTD', 'n/a', 'Memo line: outside the 30 day window'),
    ('wholesalefunding', 'LTDSubordinatedLT30', 'LEDGER', NULL, '5.02', 'LTD', 'n/a', NULL),
    ('wholesalefunding', 'LTDSubordinatedGT30', 'LEDGER', NULL, '5.04', 'LTD', 'n/a', 'Memo line: outside the 30 day window'),
    ('wholesalefunding', 'LTDTrustPreferredLT30', 'LEDGER', NULL, '5.02', 'LTD', 'n/a', NULL),
    ('wholesalefunding', 'LTDTrustPreferredGT30', 'LEDGER', NULL, '5.04', 'LTD', 'n/a', 'Memo line: outside the 30 day window'),
    ('wholesalefunding', 'LTDOtherLT30', 'LEDGER', NULL, '5.02', 'LTD', 'n/a', 'Long-Term Debt not senior, subordinated or trust preferred'),
    ('wholesalefunding', 'LTDOtherGT30', 'LEDGER', NULL, '5.04', 'LTD', 'n/a', 'Memo line: outside the 30 day window'),
    ('wholesalefunding', 'WFUnclassifiedLT30', 'LEDGER', NULL, '9.99', 'Review', 'n/a', 'Instrument type not recognised. Add a CASE branch in lcr_wholesale_funding.'),
    ('wholesalefunding', 'WFUnclassifiedGT30', 'LEDGER', NULL, '9.99', 'Review', 'n/a', 'Instrument type not recognised. Add a CASE branch in lcr_wholesale_funding.')
  AS t(source_system, lcr_class, rule, line_number_op, line_number, entity_type, insurance_status, note)

-- COMMAND ----------

-- DBTITLE 1,Dimension: lcr_gl_section_map
-- Account level overrides for the GL recon. Anything not listed falls back to the GL hierarchy in lcr_general_ledger.
CREATE OR REPLACE VIEW finance.staging.lcr_gl_section_map AS
SELECT * FROM VALUES
    -- gl_bs_acct, recon_section
    ('2101509', 'Brokered Deposits'),
    ('2268035', 'Brokered Deposits'),
    ('2101632', 'Brokered Deposits'),
    ('2101517', 'Brokered Deposits - LIDs'),
    ('2101525', 'Brokered Deposits - LIDs'),
    ('2268076', 'Brokered Deposits - LIDs'),
    ('2410009', 'FHLB Advances'),
    ('2411007', 'FHLB Advances'),
    ('2321016', 'Fed Funds Purchased'),
    ('2321008', 'Fed Funds Purchased'),
    ('2376069', 'Senior Debt'),
    ('2376002', 'Subordinated Debt'),
    ('2400349', 'Subordinated Debt'),
    ('2400331', 'Trust Preferred'),
    ('2400364', 'Trust Preferred'),
    ('2420016', 'Trust Preferred')
  AS t(gl_bs_acct, recon_section)

-- COMMAND ----------

-- DBTITLE 1,Import 1: CoreDeposits
-- Brokered rows on GL 2101509, 2268035 and 2101632 are excluded here because WholesaleFunding carries them
-- and ties to the GL. Brokered LIDs (2101517, 2101525, 2268076) stay in core deposits.
CREATE OR REPLACE VIEW finance.staging.lcr_core_deposits AS
SELECT
  reg.asofdate,
  TRIM(reg.legacy_bank)                  AS legacy_bank,
  TRIM(reg.lcr_class)                    AS lcr_class,
  cm.rule,
  ld.section_number,
  ld.section_name,
  ld.line_number,
  ld.line_name,
  ld.schedule_ref,
  cm.line_number_op,
  ldo.line_name                          AS line_name_op,
  ldo.schedule_ref                       AS schedule_ref_op,
  cm.entity_type,
  cm.insurance_status,
  CAST(reg.gl_bs_acct AS STRING)         AS gl_bs_acct,
  reg.counterparty_type,
  reg.bdsp_flag,
  SUM(reg.ledger_balance)                AS ledger_balance,
  SUM(reg.op_balance)                    AS op_balance,
  SUM(reg.non_op_balance)                AS non_op_balance,
  SUM(reg.ics_reciprocal_balance)        AS ics_reciprocal_balance
FROM finance.staging.deposits_reg reg
LEFT JOIN finance.staging.lcr_class_map cm
  ON cm.lcr_class = TRIM(reg.lcr_class)
 AND cm.source_system = 'deposits_reg'
LEFT JOIN finance.staging.lcr_line_def ld
  ON ld.line_number = cm.line_number
LEFT JOIN finance.staging.lcr_line_def ldo
  ON ldo.line_number = cm.line_number_op
WHERE reg.eobm_flag = 'Y'
  AND reg.asofdate >= DATE'2026-01-01'
  AND reg.internal_flag = 'N'
  AND (reg.product_type <> 'Brokered' OR reg.subproduct_group = 'LIDs')
  AND NOT (reg.lcr_class LIKE 'Brokered%' AND CAST(reg.gl_bs_acct AS STRING) IN ('2101509', '2268035', '2101632'))
GROUP BY ALL

-- COMMAND ----------

-- DBTITLE 1,Import 2: WholesaleFunding
CREATE OR REPLACE VIEW finance.staging.lcr_wholesale_funding AS
WITH wf AS (
  SELECT
    w.as_of_date                         AS asofdate,
    w.whlsefndg_id,
    w.tranche,
    w.primary_instrument_type,
    w.sub_instrument_type,
    w.product_type,
    w.account_number,
    w.counterparty_name,
    w.counterparty_type,
    CASE WHEN w.maturity_bucket = '0-30 days' THEN 'LT30' ELSE 'GT30' END AS maturity_bucket,
    w.contract_total_balance,
    w.gl_account_number,
    w.level6_id,
    SUM(w.current_balance)               AS current_balance
  FROM finance.reporting.wholesalefunding w
  WHERE w.internal_transaction_flag = FALSE
    AND w.as_of_date >= DATE'2026-01-01'
  GROUP BY ALL
),
fam AS (
  SELECT
    wf.*,
    CASE
      WHEN primary_instrument_type = 'Brokered Deposit' AND product_type = 'Brokered NMD'      THEN 'BrokeredNMD'
      WHEN primary_instrument_type = 'Brokered Deposit' AND product_type = 'Brokered Term NMD' THEN 'BrokeredTermNMD'
      WHEN primary_instrument_type = 'Brokered Deposit' AND sub_instrument_type = 'Brokered CD' THEN 'BrokeredCD'
      WHEN primary_instrument_type = 'FHLB Advance'                                            THEN 'FHLBAdvance'
      WHEN primary_instrument_type = 'Fed Funds Purchased'                                     THEN 'FedFundsPurchased'
      WHEN primary_instrument_type = 'Long-Term Debt' AND sub_instrument_type = 'Senior Debt'  THEN 'LTDSenior'
      WHEN primary_instrument_type = 'Long-Term Debt' AND sub_instrument_type = 'Subordinated Debt' THEN 'LTDSubordinated'
      WHEN primary_instrument_type = 'Long-Term Debt' AND sub_instrument_type = 'Trust Preferred Securities' THEN 'LTDTrustPreferred'
      WHEN primary_instrument_type = 'Long-Term Debt'                                          THEN 'LTDOther'
      ELSE 'WFUnclassified'
    END AS lcr_family,
    CASE
      WHEN product_type LIKE 'HoldCo%' THEN 'HoldCo'
      WHEN product_type LIKE 'Bank%'   THEN 'Bank'
    END AS issuer_level
  FROM wf
),
cls AS (
  SELECT
    fam.*,
    CASE WHEN lcr_family = 'BrokeredNMD' THEN lcr_family ELSE CONCAT(lcr_family, maturity_bucket) END AS lcr_class
  FROM fam
)
SELECT
  c.asofdate,
  c.lcr_class,
  c.lcr_family,
  c.issuer_level,
  ld.section_number,
  ld.section_name,
  ld.line_number,
  ld.line_name,
  ld.schedule_ref,
  ld.line_type,
  cm.entity_type,
  c.whlsefndg_id,
  c.tranche,
  c.primary_instrument_type,
  c.sub_instrument_type,
  c.product_type,
  c.account_number,
  c.counterparty_name,
  c.counterparty_type,
  c.maturity_bucket,
  c.gl_account_number,
  c.level6_id,
  c.contract_total_balance,
  c.current_balance
FROM cls c
LEFT JOIN finance.staging.lcr_class_map cm
  ON cm.lcr_class = c.lcr_class
 AND cm.source_system = 'wholesalefunding'
LEFT JOIN finance.staging.lcr_line_def ld
  ON ld.line_number = cm.line_number

-- COMMAND ----------

-- DBTITLE 1,Import 3: GeneralLedger
-- Rebuilt from the old gl_lkup temp view. Changes:
--   legacy_bank is trimmed (the old view returned ' PNFP' and ' SNV' with a leading space, which breaks joins to deposits)
--   hard coded dates removed: every month end from the start date, with asofdate = last business day of the month
--   Trust preferred (level 6 TRUSTPREFSEC) added
--   recon_section added so long-term debt, FHLB, Fed funds and brokered each have their own block
CREATE OR REPLACE VIEW finance.staging.lcr_general_ledger AS
SELECT
  dim_dates.last_business_day_of_month                                AS asofdate,
  dim_dates.date                                                      AS eomdate,
  COALESCE(NULLIF(TRIM(REPLACE(tm1.projects, 'No Project', '')), ''), 'UNASSIGNED') AS legacy_bank,
  gl.`Level 4 ID`                                                     AS level4_id,
  gl.`Level 5 ID`                                                     AS level5_id,
  gl.`Level 6 ID`                                                     AS level6_id,
  gl.`Account ID`                                                     AS gl_bs_acct,
  gl.`Account Desc`                                                   AS gl_bs_acct_name,
  COALESCE(
    sm.recon_section,
    CASE
      WHEN gl.`Level 4 ID` = 'DEPOSITS'                                  THEN 'Core Deposits'
      WHEN gl.`Level 5 ID` = 'REPUR'                                     THEN 'Repurchase Agreements'
      WHEN gl.`Level 6 ID` = 'TRUSTPREFSEC'                              THEN 'Trust Preferred'
      WHEN gl.`Level 6 ID` = 'FUNDSPUR'                                  THEN 'Fed Funds Purchased'
      WHEN gl.`Level 6 ID` IN ('2410009', '2411007')                     THEN 'FHLB Advances'
      WHEN gl.`Level 6 ID` = 'NOTESPAYREG'                               THEN 'Other Notes Payable'
      ELSE 'Other'
    END
  )                                                                   AS recon_section,
  SUM(CAST(tm1.vvalue AS DOUBLE))                                     AS gl_balance
FROM silver_prod.p021.tm1_financetrialbalancepbi tm1
JOIN silver_prod.reference_data.d_gl_account gl
  ON tm1.Accounts = gl.`Account ID`
JOIN finance.default.dim_dates dim_dates
  ON dim_dates.date = TO_DATE(tm1.prcs_dte, 'yyyyMMdd')
LEFT JOIN finance.staging.lcr_gl_section_map sm
  ON sm.gl_bs_acct = gl.`Account ID`
WHERE Versions = 'ACTUAL'
  AND DataSources = 'TotalCur'
  AND FinanceMeasures = 'EndBal'
  AND (
    gl.`Level 4 ID` = 'DEPOSITS'
    OR gl.`Level 5 ID` = 'REPUR'      -- repos sit under FUNDREP / REPUR, not DEPOSITS
    OR gl.`Level 6 ID` IN ('FUNDSPUR', 'NOTESPAYREG', '2411007', '2410009', 'TRUSTPREFSEC')
  )
  AND RIGHT(Periods, 3) = 'YTD'
  AND dim_dates.date >= DATE'2026-01-01'
  AND dim_dates.date = dim_dates.end_of_month
GROUP BY ALL

-- COMMAND ----------

SELECT * FROM finance.staging.lcr_general_ledger

-- COMMAND ----------

-- DBTITLE 1,Import 3b: GL recon
-- One row per month end, bank, section and GL account. variance = source minus GL.
-- WholesaleFunding has no bank column, so its sections are reconciled at bank = 'ALL' on both sides.
CREATE OR REPLACE VIEW finance.staging.lcr_gl_recon AS
WITH gl AS (
  SELECT
    asofdate,
    CASE WHEN recon_section IN ('Brokered Deposits', 'FHLB Advances', 'Fed Funds Purchased', 'Senior Debt',
                                'Subordinated Debt', 'Trust Preferred', 'Other Notes Payable')
         THEN 'ALL' ELSE legacy_bank END                           AS legacy_bank,
    recon_section,
    gl_bs_acct,
    MAX(gl_bs_acct_name)                                           AS gl_bs_acct_name,
    SUM(gl_balance)                                                AS gl_balance
  FROM finance.staging.lcr_general_ledger
  GROUP BY ALL
),
src AS (
  SELECT
    asofdate,
    legacy_bank,
    gl_bs_acct,
    'CoreDeposits'                                                 AS source_system,
    SUM(ledger_balance)                                            AS source_balance
  FROM finance.staging.lcr_core_deposits
  GROUP BY ALL
  UNION ALL
  SELECT
    asofdate,
    'ALL'                                                          AS legacy_bank,
    gl_account_number                                              AS gl_bs_acct,
    'WholesaleFunding'                                             AS source_system,
    SUM(current_balance)                                           AS source_balance
  FROM finance.staging.lcr_wholesale_funding
  GROUP BY ALL
),
src2 AS (
  SELECT
    s.asofdate, s.legacy_bank, s.gl_bs_acct, s.source_system, s.source_balance,
    COALESCE(sm.recon_section, CASE s.source_system WHEN 'CoreDeposits' THEN 'Core Deposits' ELSE 'Other' END) AS recon_section
  FROM src s
  LEFT JOIN finance.staging.lcr_gl_section_map sm
    ON sm.gl_bs_acct = s.gl_bs_acct
)
SELECT
  COALESCE(gl.asofdate, src2.asofdate)             AS asofdate,
  COALESCE(gl.legacy_bank, src2.legacy_bank)       AS legacy_bank,
  COALESCE(gl.recon_section, src2.recon_section)   AS recon_section,
  COALESCE(gl.gl_bs_acct, src2.gl_bs_acct)         AS gl_bs_acct,
  gl.gl_bs_acct_name,
  src2.source_system,
  COALESCE(gl.gl_balance, 0)                       AS gl_balance,
  COALESCE(src2.source_balance, 0)                 AS source_balance,
  COALESCE(src2.source_balance, 0) - COALESCE(gl.gl_balance, 0) AS variance
FROM gl
FULL OUTER JOIN src2
  ON gl.asofdate = src2.asofdate
 AND gl.legacy_bank = src2.legacy_bank
 AND gl.gl_bs_acct = src2.gl_bs_acct

-- COMMAND ----------

-- DBTITLE 1,Import 4: Secured
-- Collateral rows: pledged market value by pledgee type and HQLA level, only for pledgees that belong in Outflow - Secured.
-- Deposit balance rows: deposits held against collateral, by pledgee type. PSE counts only the non-reciprocal balances
-- (product_type <> 'Reciprocal', the same idea as the old 'Non ICS' rule). Opioid is folded into ATI and CollateralSwap
-- is respelled to match the pledge map.
-- ASSUMPTION: deposits_reg has collateral_flag (the old extract did). If the name differs, edit the second SELECT.
CREATE OR REPLACE VIEW finance.staging.lcr_secured AS
SELECT
  s.asofdate,
  s.legacy_bank,
  s.pledgee_type,
  s.pledged_inst,
  s.pledge_group,
  s.hqla_level,
  'Collateral'                       AS row_type,
  SUM(s.pledged_mv)                  AS amount
FROM finance.staging.hqla_collateral_summary s
WHERE s.pledge_status = 'Pledged'
  AND s.secured_funding_flag
GROUP BY ALL
UNION ALL
SELECT
  reg.asofdate,
  TRIM(reg.legacy_bank)              AS legacy_bank,
  CASE reg.collateral_flag
    WHEN 'Opioid'         THEN 'ATI'
    WHEN 'CollateralSwap' THEN 'Collateral Swap'
    ELSE reg.collateral_flag
  END                                AS pledgee_type,
  CAST(NULL AS STRING)               AS pledged_inst,
  CAST(NULL AS STRING)               AS pledge_group,
  'Deposit Balance'                  AS hqla_level,
  'DepositBalance'                   AS row_type,
  SUM(reg.ledger_balance)            AS amount
FROM finance.staging.deposits_reg reg
WHERE reg.eobm_flag = 'Y'
  AND reg.asofdate >= DATE'2026-01-01'
  AND reg.internal_flag = 'N'
  AND COALESCE(reg.collateral_flag, 'N') <> 'N'
  AND (reg.collateral_flag <> 'PSE' OR COALESCE(reg.product_type, '') <> 'Reciprocal')
GROUP BY ALL

-- COMMAND ----------

-- DBTITLE 1,Import 5: Securities
-- HQLA securities by category. Only accounts flagged Treasury = 'Yes' in lcr_account_map count toward HQLA,
-- and Non-HQLA positions are left out (they matter only as collateral, see lcr_secured).
-- pledged_mv is every pledge, FHLB included (the conservative reading). pledged_fhlb_mv shows the FHLB part so it can be added back.
-- Due from Fed cash is not in TPG, so the 'Level 1 - Due from Fed' category has no source here yet.
CREATE OR REPLACE VIEW finance.staging.lcr_securities AS
SELECT
  s.asofdate,
  s.legacy_bank,
  CASE s.hqla_level
    WHEN 'Level 1'  THEN 'Level 1 - Securities'
    WHEN 'Level 2A' THEN 'Level 2A - Securities'
    WHEN 'Level 2B' THEN 'Level 2B - Securities'
  END                                                                   AS hqla_category,
  SUM(s.pledged_mv + s.unpledged_mv)                                    AS market_value,
  SUM(s.pledged_mv)                                                     AS pledged_mv,
  SUM(CASE WHEN s.pledged_inst IN ('FHLBLOC', 'FHLB - ATL ADV') THEN s.pledged_mv ELSE 0 END) AS pledged_fhlb_mv
FROM finance.staging.hqla_collateral_summary s
WHERE s.hqla_level IN ('Level 1', 'Level 2A', 'Level 2B', 'Non-HQLA')
  AND s.treasury_flag = 'Yes'
GROUP BY ALL

-- COMMAND ----------

select * from finance.staging.hqla_collateral_summary

-- COMMAND ----------

SELECT * FROM finance.staging.hqla_collateral_summary

-- COMMAND ----------

DESCRIBE finance.reporting.depositsplus_vw

-- COMMAND ----------

-- DBTITLE 1,Check 1: classes with no line (should return no rows)
SELECT 'deposits_reg' AS source_system, asofdate, lcr_class, SUM(ledger_balance) AS balance
FROM finance.staging.lcr_core_deposits
WHERE line_number IS NULL
GROUP BY ALL
UNION ALL
SELECT 'wholesalefunding', asofdate, lcr_class, SUM(current_balance)
FROM finance.staging.lcr_wholesale_funding
WHERE line_number IS NULL OR line_number = '9.99'
GROUP BY ALL

-- COMMAND ----------

select * from finance.staging.lcr_wholesale_funding

-- COMMAND ----------

-- DBTITLE 1,Check 2: no overlap between CoreDeposits and WholesaleFunding (should return no rows)
SELECT d.asofdate, d.gl_bs_acct, SUM(d.ledger_balance) AS core_balance
FROM finance.staging.lcr_core_deposits d
WHERE d.lcr_class LIKE 'Brokered%'
  AND d.gl_bs_acct IN (SELECT DISTINCT gl_account_number FROM finance.staging.lcr_wholesale_funding WHERE section_number = '2')
GROUP BY ALL

-- COMMAND ----------

-- DBTITLE 1,Check 3: bank labels (should be PNFP, SNV and nothing else)
SELECT 'core_deposits' AS src, legacy_bank, COUNT(*) AS n FROM finance.staging.lcr_core_deposits GROUP BY ALL
UNION ALL
SELECT 'general_ledger', legacy_bank, COUNT(*) FROM finance.staging.lcr_general_ledger GROUP BY ALL

-- COMMAND ----------

-- DBTITLE 1,Check 4: recon by section, latest month end
SELECT recon_section, legacy_bank, SUM(gl_balance) AS gl_balance, SUM(source_balance) AS source_balance, SUM(variance) AS variance
FROM finance.staging.lcr_gl_recon
WHERE asofdate = (SELECT MAX(asofdate) FROM finance.staging.lcr_gl_recon)
GROUP BY ALL
ORDER BY recon_section, legacy_bank

-- COMMAND ----------

-- DBTITLE 1,Check 5: recon items over $1M, latest month end
SELECT asofdate, legacy_bank, recon_section, gl_bs_acct, gl_bs_acct_name, gl_balance, source_balance, variance
FROM finance.staging.lcr_gl_recon
WHERE asofdate = (SELECT MAX(asofdate) FROM finance.staging.lcr_gl_recon)
  AND ABS(variance) > 1000000
ORDER BY ABS(variance) DESC

-- COMMAND ----------

-- DBTITLE 1,Check 6: secured collateral vs deposit balance by pledgee type, latest month end
SELECT pledgee_type,
       SUM(CASE WHEN row_type = 'Collateral'     THEN amount END) AS collateral_mv,
       SUM(CASE WHEN row_type = 'DepositBalance' THEN amount END) AS deposit_balance
FROM finance.staging.lcr_secured
WHERE asofdate = (SELECT MAX(asofdate) FROM finance.staging.lcr_secured)
GROUP BY ALL
ORDER BY pledgee_type

-- COMMAND ----------

-- DBTITLE 1,Check 7: HQLA dollars left out of lcr_securities (non-Treasury accounts), latest month end
SELECT treasury_flag, hqla_level, SUM(pledged_mv + unpledged_mv) AS market_value
FROM finance.staging.hqla_collateral_summary
WHERE asofdate = (SELECT MAX(asofdate) FROM finance.staging.hqla_collateral_summary)
  AND hqla_level IN ('Level 1', 'Level 2A', 'Level 2B')
GROUP BY ALL
ORDER BY treasury_flag, hqla_level