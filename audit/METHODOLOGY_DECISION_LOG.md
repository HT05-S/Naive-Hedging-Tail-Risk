# Methodology Decision Log (Stage 1B)

**Date:** 2026-11-11 · **Status:** provisional until approved by the team.
Full reasoning and evidence: `audit/DATA_REMEDIATION_REPORT.md`. Every rule below is coded in `src/frm_data/config.py` and was fixed from data coverage, contract specifications or the published methodology. None was chosen by looking at hedge performance; no hedge has been estimated.

Status key: **CONFIRMED** = established by data or by the paper's text · **ASSUMPTION** = a reasoned choice that the data cannot prove · **NEEDS APPROVAL** = a choice the team must sign off · **UNRESOLVED** = an open question.

## A. Data sources

| ID | Decision | Status | Basis |
|---|---|---|---|
| A1 | WTI spot = FRED `DCOILWTICO` (EIA Cushing). Local file is identical to live FRED and to EIA's own `RWTCd.xls` (9,537 values; same 1,117 blank dates). | CONFIRMED | `wti_missing_data_analysis.csv`, `external_verification` |
| A2 | `USCRWTIC` is never used as spot (equals CL1 on 86% of days). | CONFIRMED | Stage 1 A05 |
| A3 | Henry Hub spot is a composite. Intervals starting before 2007-04-01 use Bloomberg `NGUSHHUB`; intervals starting on or after it use FRED/EIA `DHHNGSP`. Each weekly return uses one source at both ends. | NEEDS APPROVAL | FRED has a Wednesday price in only 13–53% of weeks per year before 2007, and ≥ 96% of weeks from 2008 (2007 is the transition year, 77%). |
| A4 | FRED-only natural gas is the main spot-source sensitivity: 1,022 returns from 2007-04-11. | NEEDS APPROVAL | Same file; filter `spot_source == "FRED:DHHNGSP"`. |
| A5 | Gold spot = Bloomberg `XAU` (the LBMA PM file is empty). GBP spot = Bloomberg `GBPUSD` (the paper used WM/Reuters). | CONFIRMED substitution | Stage 1 |
| A6 | Bitcoin spot = `BRR`. `XBTUSD` is carried in the dataset as a sensitivity. | NEEDS APPROVAL | BRR is fixed at 4 p.m. London. Correlation with CME futures is 0.942 for BRR and 0.989 for XBTUSD, which points to a timing effect. |
| A7 | EIA files: an earlier project decision not to keep them (they matched FRED). In this stage the EIA files were downloaded again into `data/external/verification_2026-11-11/` purely for verification. | CONFIRMED | User clarification; new downloads |

## B. Observation-level exclusions

Raw values are kept on disk. Each exclusion is listed in `data/processed/processed_data_log.csv`.

| ID | Exclusion | Status |
|---|---|---|
| B1 | `NGUSHHUB` 2005-09-26 to 2005-10-06: a stale 14.50 during the post-Rita Henry Hub shutdown. FRED has no print on any of these days, while NG1 kept moving. | CONFIRMED artifact |
| B2 | `NGUSHHUB` 2025-09-29 = 0.2571, against 2.93 at FRED. It is a Monday, so no weekly interval in any option uses it. | CONFIRMED artifact (bad print) |
| B3 | `NGUSHHUB` 2020-01-01 to 2021-03-12 is dated by gas-flow day, not trade day. The window is not used in the primary series, because FRED covers it. | CONFIRMED date convention (whether Bloomberg intended it or erred is UNRESOLVED) |
| B4 | `BTC1-3` rows dated 2017-12-15 predate the CME launch (first trade date 2017-12-18). | CONFIRMED |
| B5 | Negative WTI prices on 2020-04-20 are not excluded. No weekly interval uses them (Section 4 of the report). | CONFIRMED |

## C. Weekly sampling and returns

| ID | Decision | Status |
|---|---|---|
| C1 | Target = every Wednesday. Primary observation rule (B): use Wednesday; else Tuesday; else Monday. Use the latest of these days on which all required spot and futures prices exist on the **same** day. | NEEDS APPROVAL |
| C2 | Strict Wednesday rule (A) is a sensitivity: the subset `strict_wednesday == True`. | NEEDS APPROVAL |
| C3 | A return is defined only between consecutive weekly observations, with a holding period of 5–9 days. A return is never formed across a missing week. | CONFIRMED rule |
| C4 | Log returns only; computed only when both prices are > 0. Nothing is interpolated, forward-filled or backfilled. | CONFIRMED rule |
| C5 | No independent-source recovery of WTI spot (Approach C), because no compatible source exists. | CONFIRMED |
| C6 | Samples: H1 original period 1990-01-10 to 2023-06-28 (returns); extension 2023-07-05 to 2026-11-04; BTC from 2017-12-27; NG from 1999-01-13. | CONFIRMED |

## D. Futures contracts and rolls

| ID | Decision | Status |
|---|---|---|
| D1 | Bloomberg generic k on date d = the k-th cycle contract whose LTD ≥ d. Confirmed on 789 of 1,598 expiries; most of the rest have spreads too small to test, and none of those contradicts the rule. Two NG expiries give conflicting test results; one ES case is an expiry-day settlement-timing effect. | CONFIRMED |
| D2 | Phantom contracts (notice date more than 31 days after LTD) are excluded: the 12 SP placeholders tied at 2021-09-17. | CONFIRMED |
| D3 | Futures returns use the **same contract** at both ends of every interval. Rolls happen at a weekly observation close, so the spliced price gap between contracts never enters a return. | CONFIRMED rule |
| D4 | BP, SP/ES, GC and BTC follow the paper's rule: roll before the first day of the contract month (executed at the last weekly observation before it). | CONFIRMED (paper, Section 4, p. 983) |
| D5 | CL and NG deviate. The paper's rule is infeasible because these contracts expire before their contract month, so the primary holds the nearest contract whose LTD is after the target Wednesday. | NEEDS APPROVAL |
| D6 | Alternative roll (sensitivity): CL/NG roll at the first day of the LTD month; BP/SP/ES/GC/BTC roll at LTD. Carried in `alt_fut_*` columns. | CONFIRMED rule |
| D7 | S&P: SP through SPU21, ES from ESZ21 (switch at the 2021-09-01 roll). The choice is immaterial: SP- vs ES-held weekly returns correlate 1.000, with a mean absolute difference of 0.0001. | NEEDS APPROVAL (low stakes) |
| D8 | BP futures ÷ 100 (cents to USD). Log returns are unaffected; levels and basis are. | CONFIRMED |
| D9 | Gold under the paper's rule samples the old contract on its first notice day in 36 intervals. This is kept, because it is the paper's rule. | NEEDS APPROVAL |
| D10 | WTI/NG primary samples the expiring contract 1–2 days before its LTD in 134 WTI and 85 NG rolls. | NEEDS APPROVAL (margin rule optional) |

## E. Open issues

| ID | Issue | Status |
|---|---|---|
| E1 | The paper's futures return construction is not stated. Its Table 2 WTI futures moments match a spliced front-month series, not a matched-contract series. | UNRESOLVED (strong inference only) |
| E2 | The paper's 1,728 observations cannot be reproduced from its stated rules. 1,747 − 19 = 1,728 is an arithmetic coincidence with our 19 WTI no-observation weeks, not evidence. | UNRESOLVED |
| E3 | FRED WTI is 15–30% below CL1 on several days in late March 2020 (official EIA values). One sampled week (2020-03-25) is affected. | UNRESOLVED cause; kept |
| E4 | FRED WTI is 1–6% above CL1 since 2024. | UNRESOLVED cause; kept |
| E5 | Why Bloomberg `NGUSHHUB` changes date convention and precision (2-decimal vs 4-decimal eras). | UNRESOLVED |
