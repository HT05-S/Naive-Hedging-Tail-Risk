# Methodology Decision Log (Stage 1B)

**Date:** 2026-11-11, with additions on 2026-11-12 · **Status:** approved by the team (Hina Tomar, Kavin Dhanasekaran, Sai Kishore) on 2026-11-13, together with the final report.
Full reasoning and evidence: `audit/DATA_REMEDIATION_REPORT.md`. Every rule below is coded in `src/frm_data/config.py` and was fixed from data coverage, contract specifications or the published methodology. None was chosen by looking at hedge performance; no hedge has been estimated.

Status key: **CONFIRMED** = established by data or by the paper's text · **ASSUMPTION** = a reasoned choice that the data cannot prove · **APPROVED** = a choice the team signed off on 2026-11-13 · **UNRESOLVED** = an open question.

## A. Data sources

| ID | Decision | Status | Basis |
|---|---|---|---|
| A1 | WTI spot = FRED `DCOILWTICO` (EIA Cushing). Local file is identical to live FRED and to EIA's own `RWTCd.xls` (9,537 values; same 1,117 blank dates). | CONFIRMED | `wti_missing_data_analysis.csv`, `external_verification` |
| A2 | `USCRWTIC` is never used as spot (equals CL1 on 86% of days). | CONFIRMED | Stage 1 A05 |
| A3 | Henry Hub spot is a composite. Intervals starting before 2007-04-01 use Bloomberg `NGUSHHUB`; intervals starting on or after it use FRED/EIA `DHHNGSP`. Each weekly return uses one source at both ends. | APPROVED | FRED has a Wednesday price in only 13–53% of weeks per year before 2007, and ≥ 96% of weeks from 2008 (2007 is the transition year, 77%). |
| A4 | FRED-only natural gas is the main spot-source sensitivity: 1,022 returns from 2007-04-11. | APPROVED | Same file; filter `spot_source == "FRED:DHHNGSP"`. |
| A5 | Gold spot = Bloomberg `XAU` (the LBMA PM file is empty). GBP spot = Bloomberg `GBPUSD` (the paper used WM/Reuters). | CONFIRMED substitution | Stage 1 |
| A6 | Bitcoin spot = `BRR`. `XBTUSD` is carried in the dataset as a sensitivity. | APPROVED | BRR is fixed at 4 p.m. London. Correlation with CME futures is 0.942 for BRR and 0.989 for XBTUSD, which points to a timing effect. |
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
| C1 | Target = every Wednesday. Primary observation rule (B): use Wednesday; else Tuesday; else Monday. Use the latest of these days on which all required spot and futures prices exist on the **same** day. | APPROVED |
| C2 | Strict Wednesday rule (A) is a sensitivity: the subset `strict_wednesday == True`. | APPROVED |
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
| D5 | CL and NG deviate. The paper's rule is infeasible because these contracts expire before their contract month, so the primary holds the nearest contract whose LTD is after the target Wednesday. | APPROVED |
| D6 | Alternative roll (sensitivity): CL/NG roll at the first day of the LTD month; BP/SP/ES/GC/BTC roll at LTD. Carried in `alt_fut_*` columns. | CONFIRMED rule |
| D7 | S&P: SP through SPU21, ES from ESZ21 (switch at the 2021-09-01 roll). The choice is immaterial: SP- vs ES-held weekly returns correlate 1.000, with a mean absolute difference of 0.0001. | APPROVED (low stakes) |
| D8 | BP futures ÷ 100 (cents to USD). Log returns are unaffected; levels and basis are. | CONFIRMED |
| D9 | Gold under the paper's rule samples the old contract on its first notice day in 36 intervals. This is kept, because it is the paper's rule. | APPROVED |
| D10 | WTI/NG primary samples the expiring contract 1–2 days before its LTD in 134 WTI and 85 NG rolls. | APPROVED as is (no margin rule added) |

## E. Open issues

| ID | Issue | Status |
|---|---|---|
| E1 | The paper's futures return construction is not stated. Its Table 2 moments match a spliced series under its stated roll rule (WTI: `CL1`; GBP/USD: roll on the 1st of the contract month). The replication therefore uses spliced returns (`src/frm_data/paper.py`); same-contract returns (D3) remain the setting for Bitcoin, natural gas and the robustness runs. See `REPLICATION_CONVENTIONS_NOTE.md`. | RESOLVED 2026-11-12 (inference from Table 2; team session) |
| E2 | The paper's 1,728 observations are reproduced: of the 1,748 Wednesdays from 1990-01-03 to 2023-06-28, 1,728 are days on which all four futures markets and the GBP/USD, S&P 500 and gold spot markets traded (`paper_calendar`, tested in `tests/test_paper_convention.py`). This gives 1,727 weekly returns; the paper may be counting dates. | RESOLVED 2026-11-12 |
| E3 | FRED WTI is 15–30% below CL1 on several days in late March 2020 (official EIA values). One sampled week (2020-03-25) is affected. | UNRESOLVED cause; kept |
| E4 | FRED WTI is 1–6% above CL1 since 2024. | UNRESOLVED cause; kept |
| E5 | Why Bloomberg `NGUSHHUB` changes date convention and precision (2-decimal vs 4-decimal eras). | UNRESOLVED |

## F. Additions of 2026-11-12

| ID | Decision | Status |
|---|---|---|
| F1 | Two data settings are kept side by side. **Paper setting** (`data/processed/weekly_paper_convention.csv`): strict Wednesdays, spliced futures, the paper's roll rule; used to replicate the four original markets over the paper's sample, 1990 to June 2023 (H1). **Our setting** (`weekly_market_returns.csv`): Wednesday-else-Tuesday-else-Monday and same-contract returns; used for the extension to 2026, for Bitcoin and natural gas (H2) and as the robustness run for H1. The extension uses our setting because spliced returns understate hedging effectiveness after 2023 (report, Section 5.8). | AGREED (team session) |
| F2 | In the paper setting, WTI spot (FRED) is missing on some Wednesdays. On those weeks spot and futures are both read on the nearest earlier day (Tuesday, then Monday); if neither has a price the week is dropped for WTI. 127 of 1,708 WTI weeks to June 2023 use an earlier day. | DONE |
| F3 | Natural gas spot (A3): keep the composite as the main series. Independent tests on the raw files (Monday counts, level match against FRED, daily-change correlation with NG1) confirm that Bloomberg `NGUSHHUB` is dated one trading day late from January 2020 to mid-March 2021 (B3). Robustness: FRED only (evaluation from April 2008). A second check, Bloomberg throughout with that window shifted back one day, is not yet built. | APPROVED (proposed by Sai) |
| F4 | Semivariance uses a target return of zero. Against the paper's Table 6, targets of zero, the mean and the median differ by at most 0.01 in hedging effectiveness. | DONE |
| F5 | Risk-minimising hedge ratios are found by grid search over 0.00 to 2.00 in steps of 0.01. Quantiles use linear interpolation; CVaR is the mean of the observations at or beyond the quantile. The Clayton parameter is fitted by maximum likelihood on rank-based pseudo-observations, with the same 10,000 uniform draws reused in every window. | DONE |

