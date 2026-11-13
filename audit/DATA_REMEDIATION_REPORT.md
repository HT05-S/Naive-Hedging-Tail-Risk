# Stage 1B: Data Remediation, Futures-Contract Validation and Weekly Dataset Construction

**Project:** FRE 6123, *Is the Naïve Hedge Still Hard to Beat?*
**Date:** 2026-11-11 · **Raw data pulled:** 2026-11-09 · **External verification downloads:** 2026-11-11
**Scope:** this stage fixes data problems and builds a provisional weekly spot/futures return dataset. It does **not** estimate hedge ratios, form hedged portfolios, compute hedge effectiveness or draw any conclusion about H1 or H2.

Labels used throughout:

| Label | Meaning |
|---|---|
| **[VERIFIED]** | Checked directly in our files or downloads by the scripts; reproducible |
| **[PAPER]** | Stated explicitly by Cao & Conlon (2025), with location |
| **[INFERENCE]** | Follows from verified facts or the paper's rules but is not proven |
| **[UNRESOLVED]** | Cannot be settled with the material available |
| **[DECISION]** | A choice the team must approve (listed in Section 11) |

---

## 1. Reproducing this stage

```
pip install -r requirements.txt            # includes xlrd for the EIA files
python audit/stage1b_remediation.py        # about 2 minutes, all outputs
python -m pytest -q tests                  # the automated checks
```

- **Raw data untouched [VERIFIED].** All 41 files under `data/raw/` are hashed before and after the run, and the script stops if any hash changes (`audit/results/stage1b_run_log.txt`: `raw_files_unchanged_after_run=True`). A test also checks every file against the SHA-256 recorded in the Stage 1 inventory.
- **Stage 1 outputs untouched.** `audit/RAW_DATA_AUDIT.md` and its CSVs are kept as evidence. Where this stage corrects a Stage 1 statement, the correction is recorded in Section 2 of this report.
- **External data.** Network access was available in this session. Current FRED (`DCOILWTICO`, `DHHNGSP`) and EIA (`RWTCd.xls`, `RNGWHHDd.xls`) files were downloaded to `data/external/verification_2026-11-11/`, outside `data/raw/`. Their SHA-256 hashes are recorded in `wti_missing_data_analysis.csv`.

---

## 2. Executive summary

### 2.1 What the weekly dataset contains

`data/processed/weekly_market_returns.csv`: one row per market per target Wednesday. Each row records both observation dates, the prices, the held contract, the generic used at each end, the rollover status, flags and the reason any return is missing.

| Market | Spot | Futures (held contract) | Returns: original (Jan 1990–Jun 2023) | Returns: extension (Jul 2023–Nov 2026) | Full sample | Strict-Wednesday subset |
|---|---|---|---|---|---|---|
| WTI | FRED/EIA | CL, matched contract | 1,710 of 1,747 | 175 of 175 | 1,885 | 1,637 |
| GBP/USD | Bloomberg GBPUSD | BP ÷ 100 | 1,747 | 175 | 1,922 | 1,890 |
| S&P 500 | SPX | SP to SPU21, then ES | 1,747 | 175 | 1,922 | 1,886 |
| Gold | XAU | GC (G J M Q V Z) | 1,745 | 175 | 1,920 | 1,884 |
| Bitcoin | BRR (XBTUSD sensitivity) | CME BTC | n/a | n/a | 463 (2017-12-27 to 2026-11-04) | 453 |
| Natural gas | Bloomberg HH to 2007-03, FRED/EIA from 2007-04 | NG | n/a | n/a | 1,449 (1999-01-13 to 2026-11-04) | 1,420 |

The paper reports 1,728 observations for the original period. We do not reproduce that number, and we did not try to (Section 4.1, item 7).

### 2.2 The most important findings

1. **The WTI spot gaps are real gaps in the official source [VERIFIED].** Our FRED file is identical to the current FRED series and to EIA's own spreadsheet: the same 9,537 values and the same 1,117 blank dates. No official spot value exists to recover.
   - Under the primary rule (Wednesday, else Tuesday, else Monday), only **19 weeks** have no observation, which removes 37 of 1,747 original-period returns.
   - The strict Wednesday rule would remove 279.
   - Weeks lost under either rule are not calmer or more volatile than retained weeks, measured by CL1's weekly move (Section 3).
2. **The negative WTI prints never enter a weekly return [VERIFIED].**
   - The prints (CL1 −37.63, FRED −36.98) are on Monday 2020-04-20.
   - Every Wednesday price used is positive, and so is every Tuesday or Monday fallback price.
   - No rule we tested touches the negative print: the matched-contract rule, the earlier-roll alternative, a split roll at expiry, or a generic splice.
   - The paper never mentions negative prices.
3. **The paper's futures returns appear to be spliced front-month series [INFERENCE].**
   - Our weekly **spot** moments reproduce the paper's Table 2 almost exactly for WTI and the S&P 500. For example, WTI spot minimum −0.481 (2020-03-18) and maximum 0.462 (2020-05-06) match exactly, and excess kurtosis is 9.79 vs 9.78.
   - Our matched-contract WTI **futures** returns do not match: skew −1.29, excess kurtosis 19.5, minimum −0.636.
   - A spliced CL1 series matches the paper almost exactly: skew −0.53 (paper −0.52), excess kurtosis 10.7 (11.0), minimum −0.482 (−0.482).
   - The difference comes from roll weeks. In April 2020 the June contract genuinely fell from 26.04 to 13.78, a log return of −0.636. A splice would instead record −0.366.
   - We keep matched-contract returns as primary, because they are what a hedger earns (Section 5).
4. **Bloomberg Henry Hub is dated by gas-flow day from January 2020 to mid-March 2021 [VERIFIED pattern, INFERENCE as to cause].**
   - In that window Bloomberg has no price on any of the 56 NYMEX trading Mondays.
   - It prints on 5 NYMEX holidays (Good Friday, July 3, Thanksgiving, Christmas, New Year's Day).
   - Its daily changes track the previous day's NG1 (correlation 0.34) and not the same day's (0.02).
   - FRED shows none of these features. The cause is a dating convention, which this stage establishes from the calendar alone, not from correlations.
   - **Stage 1's "matches FRED's previous-day value in 14 of 16 months" overstated the match.** Exact previous-day equality occurs on only 9% of days; what Stage 1 measured was which value was *closer*.
5. **Winter Storm Uri is present only in FRED [VERIFIED].**
   - FRED: Feb 16 $11.32, Feb 17 $23.86, Feb 18 $8.56. Bloomberg has no price on any of those days.
   - With FRED, the two Uri weeks are the most extreme spot returns in the natural-gas sample: +1.85 and −2.14 log. Futures moved only +0.10 and −0.08.
   - These two weeks alone move the spot 1% CVaR from −0.41 to −0.54 and the spot–futures correlation from 0.665 to 0.569.
6. **The natural-gas spot–futures correlation is 0.569 [VERIFIED]** after correct dating, matched contracts and the composite spot source. The FRED segment (2007–2026) gives 0.534 and the Bloomberg segment (1999–2007) 0.725.
   - The earlier project figure of 0.675 cannot be reproduced. It is close to the ex-Uri value (0.665) and to Bloomberg spot as delivered (0.662), which lacks Uri.
   - This low correlation is mainly economic basis risk (Section 6.6). It has not been "fixed" and must not be.
7. **Generic-to-contract mapping is confirmed [VERIFIED].**
   - Rule: Bloomberg generic k on date d is the k-th contract of the cycle whose last tradeable date (LTD) is on or after d.
   - **Test result:** 789 of 1,598 expiries confirm the rule outright. Most of the rest have calendar spreads too small to tell the two cases apart, and none of those contradicts the rule. The exceptions are two NG expiries with conflicting test results and one ES expiry-day artifact.
   - **Phantom contracts:** the 12 phantom SP contracts are excluded.

### 2.3 Corrections to earlier project material

| Item | Earlier statement | This stage |
|---|---|---|
| EIA data | Context doc lists `data/raw/eia/`; Stage 1 called it "absent". | The team retrieved EIA WTI and Henry Hub, compared them with FRED, and **decided not to keep them**; the missing folder reflects that decision. Those original files no longer exist, so their equivalence was not verified at the time of this audit. Instead, current EIA files were downloaded and compared value by value with our FRED files: identical (Section 3.1). |
| Henry Hub date shift | Stage 1: "matches FRED's previous-day value in 14 of 16 months". | Overstated: exact previous-day matches are rare (9% of days). The decisive evidence is the calendar pattern (missing Mondays, prints on holidays). |
| WTI missing Wednesdays | Stage 1: 164 | 165 when 2026-11-04 is included (FRED's last value is Tuesday 2026-11-03). 161 fall in the original period. |
| FRED blanks | Stage 1: "FRED gap question unresolved (network blocked)" | Resolved: the gaps are in EIA's own data. |
| NG correlation | Context: 0.675 | 0.569 (primary). See finding 6. |

---

## 3. WTI missing-data investigation (Part 2)

Evidence: `audit/results/wti_missing_data_analysis.csv` (record types `external_verification`, `blank_by_year`, `blank_run_length`, `blank_weekday`, `approach_comparison`, `missing_wednesday`).

### 3.1 Does our file reflect the source? [VERIFIED]

| Check | Result |
|---|---|
| Local FRED vs live FRED (2026-11-11) | 10,654 rows each; 9,537 values identical; 1,117 blanks on the same dates |
| Local FRED vs EIA `RWTCd.xls` | All 9,537 values identical. EIA lists no rows on FRED's blank dates, so EIA has no value to recover |
| Henry Hub (same checks) | Local = live FRED = EIA (5,722 values; 2,059 blank FRED rows, none valued in EIA) |

FRED's blank rows are calendar placeholders: EIA simply did not publish a price that day.

### 3.2 Pattern of the gaps [VERIFIED]

- **Blank days since 1990:** 1,037. They form 767 runs: 601 are single days, and the longest run is 9 rows.
- **Weekdays:** spread across the week, with Mondays most common (314).
- **When:** concentrated in 1994–2006, peaking in 2003 (122 blank days; 25 missing Wednesdays), plus 2011 (48 blank days, including 2 consecutive Wednesdays in July).
- **Exchange open:** NYMEX traded (CL1 has a price) on 705 of the 1,117 blank dates.
- **Missing Wednesdays, 1990 to 2026-11-04: 165.**
  - Original period: 161. Of these, 146 are EIA gaps on NYMEX trading days and 15 are exchange holidays or closures.
  - Extension: 4. Of these, 3 are holidays, and 2026-11-04 falls after FRED's last value.

### 3.3 Treatments compared

All three approaches keep spot and futures on the same date and never fill a price.

| Approach (original period, 1,747 possible returns) | Returns kept | Returns lost | Weeks with no observation | Returns with a displaced end date | Holding period (days: count) |
|---|---|---|---|---|---|
| **A. Strict Wednesday** | 1,468 | **279 (16.0%)** | 163 | 0 | 7: 1,468 |
| **B1. Lookback 1 day (Wed, else Tue)** | 1,670 | 77 | 40 | 113 | 6: 86, 7: 1,495, 8: 89 |
| **B2. Lookback 2 days (Wed, else Tue, else Mon), primary** | **1,710** | **37 (2.1%)** | **19** | 136 | 5: 15, 6: 90, 7: 1,495, 8: 93, 9: 17 |
| **C. Independent official recovery** | 0 recovered | n/a | n/a | n/a | n/a |

| Approach (extension, 175 possible) | Kept | Lost |
|---|---|---|
| A strict | 169 | 6 |
| B2 primary | 175 | 0 |

**Why one missing week costs two returns.** If week T has no observation, the return ending at T has no end point. The return ending at T+1 then has no start point. We do not bridge to T−1, because that would be a 14-day return treated as a weekly one.

**Approach C is infeasible.**
- **EIA:** the publisher itself is blank on every gap date.
- **USCRWTIC:** equals CL1 to the cent on 86% of days (Stage 1 A05), so it is not independent spot.
- **CL1 itself:** a futures price.

Using any of these would replace spot with futures and remove the basis we want to measure.

**Is the missingness related to market conditions? [VERIFIED]** CL1 always has a price, so it can measure the market's weekly move in excluded and retained weeks:

| Weeks | Mean of CL1's absolute weekly log change |
|---|---|
| Lost under B2 | 0.041 |
| Kept under B2 | 0.039 |
| Lost under A | 0.036 |
| Kept under A | 0.039 |

There is no sign that missing weeks are stress weeks or quiet weeks. The losses are, however, concentrated in time (1994–2006), so A would under-weight that era. That is a sampling-composition effect, not a bias in returns.

**Effect on statistics.** Spot weekly standard deviation is 0.0565 under A and 0.0558 under B2. The spot–futures correlation is 0.959 under A and 0.951 under B2. The minimum and maximum are identical. Displaced weeks have 5–9-day holding periods, which add slightly to variance dispersion. That is the price of keeping 242 more returns.

### 3.4 Recommendation [DECISION]

- **Primary: B2.**
  - Use the latest of Wednesday, Tuesday or Monday on which all required prices exist on the same day.
  - The maximum lookback is 2 calendar days, and the observation can never reach back to or past the previous week's observation.
  - If none of the three days works, the week has no observation and the next week's return is undefined.
- **Sensitivity: A.** This is the `strict_wednesday == True` subset of the same file. A test confirms it equals an independent build with zero lookback.
- **Why:**
  - B2 never uses different dates for the two legs and never invents a price.
  - Holding periods stay within ±2 days of a week, and the same rule applies to every market.
  - It keeps 98% of returns instead of 84%.
  - It was **not** chosen to approach the paper's 1,728. B2 gives 1,710, and A would give 1,468.
- **Verification:**
  - `test_prices_match_raw_on_obs_dates` re-reads raw prices on the stored dates.
  - `test_prev_obs_is_previous_weeks_obs` and `test_week_after_missing_week_is_undefined` check that no return bridges a gap.
  - `test_strict_rule_is_subset` checks that A is a subset of B2.
- **Limitation:** the 19 lost weeks cannot be recovered from any official source we have.

---

## 4. Cao & Conlon's methodology and the April 2020 negative prices (Part 3)

### 4.1 What the paper states

Page numbers are journal pages of *J. Futures Markets* 45 (2025) 977–1005.

| Question | Paper | Our assessment |
|---|---|---|
| 1. Are negative WTI prices discussed? | **No.** The text, tables, footnote (one endnote, about options) and Data Availability Statement contain no mention of negative prices, April 2020 or any data cleaning [PAPER, full-text search]. | We do not attribute any treatment to the authors. |
| 2. Is their handling disclosed? | No. | [UNRESOLVED] |
| 3. Wednesday observations? | "weekly price data, specifically every Wednesday, spanning from January 1990 to June 2023" (Section 4, p. 983). Holiday Wednesdays are not addressed. | Holiday handling [UNRESOLVED]. |
| 4. Roll rule? | "those nearest to maturity, with a rollover to the subsequent contract occurring on the first day of the contract month" (Section 4, p. 983). | Feasible for BP, S&P, GC and BTC; **infeasible for CL and NG**, whose contracts expire before their contract month (Section 5.2). |
| 5. Returns? | Hedged returns are y<sub>long</sub> = −s<sub>t</sub> + b f<sub>t</sub> and y<sub>short</sub> = s<sub>t</sub> − b f<sub>t</sub> (Eq. 1–2, p. 981). Returns are "logarithmic differences in prices" (Table 2 note, p. 985). Section 4 also calls them "percentage changes" (p. 983). | We use log returns. How the futures return series is formed across rolls is **not stated**. |
| 6. Sources? | Table 1 (p. 983): Bloomberg for WTI, S&P and gold spot and all futures; Eikon for GBPUSD (WM/Reuters); LBM for gold. The Data Availability Statement (p. 1004) says the data "are available from Refinitiv". | Internally inconsistent; our sources differ in any case. |
| 7. Can the sample be reconstructed? | "a total of 1,728 weekly observations" (Section 4, p. 983). | Not from the stated rules. There are 1,748 Wednesdays from 1990-01-03 to 2023-06-28, so 1,747 possible returns. 1,747 − 19 = 1,728, where 19 is our count of WTI weeks with no observation. That is an arithmetic coincidence, not evidence of their procedure. |

### 4.2 What our data can verify about the paper [VERIFIED]

Our original-period weekly statistics compared with Table 2 (p. 985). The GBP and S&P columns of Table 2 were displaced in our text extraction and were re-assembled. Check them against the printed page.

| Series | Paper: skew / kurtosis* / min / max | Ours, matched contract | Ours, generic splice (diagnostic only) |
|---|---|---|---|
| WTI spot | −0.410 / 9.778 / −0.481 / 0.462 | −0.426 / 9.788 / −0.481 / 0.462 | n/a |
| WTI futures | −0.524 / 11.043 / −0.482 / 0.466 | **−1.288 / 19.535 / −0.636 / 0.466** | **−0.527 / 10.713 / −0.482 / 0.466** |
| S&P spot | −0.819 / 5.143 / −0.165 / 0.107 | −0.819 / 5.148 / −0.165 / 0.107 | n/a |
| S&P futures | −0.822 / 5.166 / −0.175 / 0.111 | −0.847 / 5.216 / −0.175 / 0.111 | −0.822 / 5.180 / −0.175 / 0.111 |
| Gold futures | −0.290 / 4.473 / −0.131 / 0.129 | −0.298 / 4.436 / −0.132 / 0.129 | −0.304 / 4.445 / −0.130 / 0.129 |
| GBP futures | −0.961 / 6.134 / −0.103 / 0.050 | −0.955 / 6.281 / −0.102 / 0.050 | −1.091 / 7.633 / −0.120 / 0.050 |
| Gold spot (LBMA in paper, XAU here) | −0.266 / 4.101 / −0.124 / 0.137 | −0.231 / 5.369 / −0.148 / 0.138 | n/a |
| GBP spot (WMR in paper, Bloomberg here) | −0.823 / 4.854 / −0.091 / 0.055 | −0.961 / 6.120 / −0.100 / 0.050 | n/a |

\*The values match our *excess* kurtosis, so the paper's "kurtosis" column is excess kurtosis. Its text says so: "calculated as kurtosis − 3", p. 985.

What this establishes:
- **[VERIFIED]** The paper's WTI spot extremes come from the weeks ending 2020-03-18 and 2020-05-06. Our values for those weeks are identical, so the paper's sample does contain March–May 2020 and uses Wednesday sampling.
- **[INFERENCE]** The paper's WTI futures moments match a front-month series spliced across contracts, not a matched-contract series. A matched series must contain the CLM20 week ending 2020-04-22 (−0.636), and the paper's minimum is −0.482. For financial futures the two constructions barely differ, because calendar spreads are small. We cannot rule out other constructions that produce similar moments.

### 4.3 April 2020 event review [VERIFIED]

Evidence: `audit/results/wti_april2020_review.csv`, with 63 daily rows (2020-03-02 to 2020-05-29) and 13 weekly rows. Contract identities come from `CL_contracts.csv` and the validated generic mapping. They are not assumed from generic labels.

Contract calendar: **CLJ20** LTD 2020-03-20 · **CLK20** (May) LTD **2020-04-21** · **CLM20** (June) LTD 2020-05-19.

| Date | Day | FRED spot | CL1 (contract) | CL2 (contract) | Used in a weekly return? |
|---|---|---|---|---|---|
| 04-15 | Wed | 19.96 | 19.87 (K20) | 26.04 (M20) | Yes: end of week 04-15 (K20) and start of week 04-22 (M20) |
| 04-17 | Fri | 18.31 | 18.27 (K20) | 25.03 (M20) | No |
| **04-20** | **Mon** | **−36.98** | **−37.63 (K20)** | 20.43 (M20) | **No.** It is not a Wednesday, and no fallback was needed because 04-22 was available |
| 04-21 | Tue | 8.91 | 10.01 (K20, LTD) | 11.57 (M20) | No |
| 04-22 | Wed | 13.64 | 13.78 (**M20**) | 20.69 (N20) | Yes: end of week 04-22 |

Bloomberg's CL1 switches from K20 to M20 on 04-22, the first trading day after K20's LTD. The identity holds: M20 is CL2 at 11.57 on 04-21 and CL1 at 13.78 on 04-22.

Weekly returns for the interval ending 2020-04-22 under each construction:

| Construction | Contract(s) | Futures log return | Touches −37.63? |
|---|---|---|---|
| **Primary (hold nearest contract with LTD after the target Wednesday)** | M20: 26.04 to 13.78 | **−0.636** | No |
| Alternative (roll on the first day of the LTD month) | M20 from 04-01 | −0.636 | No |
| Expiry split roll (K20 to its LTD, then M20) | K20 19.87 to 10.01, then M20 11.57 to 13.78 | −0.511 | No (uses the 04-21 final settlement) |
| CL1 generic splice (not a position return) | K20 19.87 on 04-15 to M20 13.78 on 04-22 | −0.366 | No |
| Paper's literal rule | Would hold K20 until May 1 | **Undefined**: K20 does not trade after 04-21 | n/a |

Spot for the same week: 19.96 to 13.64, a log return of −0.381, defined.

Other April 2020 facts:
- **Week ending 03-25:** CLJ20 expired on 03-20. The held K20 is CL2 at 20.83 on 03-18 and CL1 at 24.49 on 03-25, a return of +0.162. FRED spot that week moved only +0.013, because FRED was 13–30% below CL1 on 03-20 and on every day from 03-24 to 03-30 (it matched CL1 on 03-23). These are official EIA values. The cause is [UNRESOLVED]: possibly an assessment against a different delivery month during the expiry period.
- **Weeks ending 03-18 and 05-06:** these give the extreme spot returns (−0.481, +0.462) that match the paper.

### 4.4 Negative-price treatment [DECISION]

- **Raw values kept.** All three negative prints (FRED −36.98; CL1 −37.63; USCRWTIC −37.63) remain in `data/raw` and are not excluded. A test checks that they are still there.
- **No log of a nonpositive price.** The return function returns "undefined" for any nonpositive price, and the row is flagged `nonpositive_price` with exclusion reason "log return undefined". No sampled interval in any market triggers this (`nonpositive_price_weeks = 0`).
- **Why no exclusion is needed:** the negative price is a Monday close, and the primary observation rule takes Wednesday whenever Wednesday is valid. If Wednesday 2020-04-22 had been missing, the rule would have tried Tuesday 04-21, which is positive. Monday 04-20 is reached only if both later days are missing; it would then produce an *undefined* return and be flagged, not dropped silently or replaced.
- **The real stress is kept.** The June contract's −0.636 week is the largest futures loss in the WTI sample and stays in the data.
- **Sensitivity, if ever needed:** simple (arithmetic) returns are defined through a negative price, but they must be used for the whole backtest, never mixed with log returns. No current interval needs this.

---

## 5. Futures contracts and rollover (Part 5)

Evidence: `audit/results/roll_mapping_validation.csv`, record types `calendar_summary`, `generic_roll_summary`, `generic_roll_event` (1,598 rows), `held_roll_summary`, `held_contract_roll` (1,398 rows), `notice_period_check`, `sp_es_overlap` and `manual_roll_check`.

### 5.1 Contract calendars [VERIFIED]

| Root | Calendar rows | Usable in generic cycle | Excluded |
|---|---|---|---|
| CL, NG | 645, 583 | all (monthly) | none |
| BP | 272 | 179 (H M U Z) | 93 serial months |
| SP | 170 | 158 (H M U Z) | **12 phantoms.** Their LTD is the 2021-09-17 delisting date while their notice dates run to 2026 (rule: notice date more than 31 days after LTD) |
| ES | 138 | all | none |
| GC | 655 | 331 (G J M Q V Z) | 324 inactive months |
| BTC | 116 | all (monthly) | none |

### 5.2 Generic-to-contract mapping [VERIFIED]

**Hypothesis.** On date d, generic k is the k-th usable contract whose LTD is on or after d. Bloomberg rolls on the first trading day after the LTD.

**Identity test.** If the roll happens between d<sub>0</sub> (the LTD) and d<sub>1</sub> (the next day), then G1(d<sub>1</sub>) must be the same contract as G2(d<sub>0</sub>). We compare |ln G1(d<sub>1</sub>)/G2(d<sub>0</sub>)| with |ln G1(d<sub>1</sub>)/G1(d<sub>0</sub>)|, scaled by daily volatility. A second test checks for a one-day jump in ln(G2/G1).

| Root | Expiries | Confirmed | Contradicted | Not decisive (spread too small to tell) |
|---|---|---|---|---|
| CL | 442 | 140 | 0 | 301 (1 not testable: April 2020) |
| NG | 438 | 196 | 0 (2 conflicting) | 240 |
| BP | 147 | 83 | 0 | 64 |
| SP | 127 | 67 | 0 | 60 |
| ES | 117 | 66 | 1* | 49 |
| GC | 221 | 190 | 0 | 31 |
| BTC | 106 | 47 | 0 | 59 |

\*ESH11: on S&P expiry Fridays, G1 is the morning final settlement price, not a close, so the expiry-day spread spikes. Neither of our roll rules ever samples a contract on its LTD.

Testing alternative roll days, from 3 days before the LTD to 1 day after, rejects all of them. For example, CL rolling one day early is contradicted 23 times and confirmed twice.

"Not decisive" means the calendar spread was too small relative to daily volatility to tell. In those cases a one-day misidentification would also change returns by very little.

**Limitation.** We have only generics 1–3, not individual contract price files. A contract's price is available only while it is one of the three nearest. Every held contract in every interval was within that range (`intervals_contract_unavailable = 0` for all markets).

### 5.3 Held-contract rules

| Market | Paper's rule feasible? | Primary rule: contract c held over the week ending T if… | Alternative (sensitivity) | Roll executed at |
|---|---|---|---|---|
| GBP/USD (BP) | Yes | T < first day of c's contract month | T < LTD (expiry roll) | Close of the last weekly observation before the first of the month (0–6 days early) |
| S&P (SP, ES) | Yes | same | T < LTD | same |
| Gold (GC) | Yes, with a notice-day caveat | same | T < LTD (holds into the delivery month) | same |
| Bitcoin (BTC) | Yes | same | T < LTD | same |
| **WTI (CL)** | **No.** Contracts expire 4–16 days *before* their contract month | **T < LTD** (nearest contract still trading after T) | T < first day of the LTD month (about 3 weeks earlier) | Last observation 1–9 days before the old LTD (median 6) |
| **Natural gas (NG)** | **No.** Contracts expire 3–13 days before their contract month | T < LTD | T < first day of the LTD month | Last observation 1–9 days before the old LTD (median 6) |

**The CL/NG deviation.** "Nearest to maturity" plus a roll "on the first day of the contract month" cannot be applied to CL/NG, because the nearest contract stops trading before that day. The primary rule keeps "nearest to maturity" and rolls at the last weekly observation before expiry. This is the deviation closest to the paper's text, and the Table 2 evidence suggests their continuous series also held the nearest contract.

**[DECISION]** The primary rule sometimes samples the expiring contract 1–2 days before its LTD: 134 of 442 WTI rolls and 85 of 334 NG rolls. Those are thin, volatile days; April 20, 2020 was the penultimate day of CLK20. If you prefer a safety margin, a rule of "roll at least 3 business days before LTD" is a one-line change. The `alt_fut_*` columns already carry a much earlier roll.

**Physically delivered contracts [VERIFIED]:**
- **CL and NG:** the first notice day is after the LTD, so no rule we use reaches it.
- **Gold:** the first notice day is the last business day *before* the contract month. The paper's rule therefore samples the old contract on its first notice day in **36 intervals**, whenever a Wednesday falls on the month's last business day. Prices are valid settlements, but a real long hedger would normally have rolled already to avoid delivery notices. **[DECISION]** keep (paper's rule) or roll one business day earlier.
- **BP:** physically delivered currency, but its first notice day follows the LTD.
- **S&P and BTC:** cash settled.

**S&P transition [VERIFIED].**
- **Rule:** SP is held through SPU21, its last listed contract. ESZ21 is held from the interval ending 2021-09-01, at the regular roll.
- **Why it doesn't matter:** comparing SP-held and ES-held weekly returns for the same contract months over 1997-09 to 2021-08 (1,250 weeks) gives correlation 1.000 and a mean absolute difference of 0.0001.
- **ES alternative:** using ES from 1997 would be immaterial for results.

### 5.4 Matched-contract returns vs generic splices

The **generic splice** is the weekly log change of G1. In a roll week it compares two different contracts: the old one at the start and the new one at the end. The difference is the calendar spread, which is not a gain or loss to anyone holding a position.

The **matched-contract return** compares the same contract at both ends. The roll happens at the start-of-interval close, where the hedger closes the old contract and opens the new one at prices observed on the same day.

Manual checks (`manual_roll_check`):

| Week ending | Matched contract | Matched return | Splice return | Difference (the spread artifact) |
|---|---|---|---|---|
| WTI 2020-03-25 | CLK20 | +0.162 | +0.184 | +0.022 |
| WTI 2020-04-22 | CLM20 | −0.636 | −0.366 | +0.270 |
| NG 2021-02-24 (Uri) | NGJ21 | −0.081 | −0.120 | −0.039 |
| NG 2026-01-28 | NGH26 | +0.054 | +0.425 | +0.371 |
| NG 2026-02-04 | NGH26 | −0.074 | **−0.767** | −0.693 |
| S&P 2021-09-01 (SP to ES) | ESZ21 | +0.006 | +0.006 | 0.000 |

In January 2026 the expiring NGG26 spiked to 7.46 at expiry, while NGH26 traded near 3.7. A splice would book a false −77% log loss on a position nobody held.

**Recommendation.** Matched-contract returns are primary for all markets. A splice-based futures series could be produced later as a *paper-replication sensitivity* for H1 only, clearly labelled. **[DECISION]**

---

## 6. Natural gas: source selection (Part 4)

Evidence: `audit/results/natural_gas_source_comparison.csv` (record types `external_verification`, `coverage_by_period`, `alignment_by_month`, `alignment_by_year`, `alignment_window_summary`, `option_comparison`, `source_transition`) and `natural_gas_stress_events.csv`.

### 6.1 Coverage by period [VERIFIED]

| Period | Source | Valid days | NG1 trading days with no spot | Missing Wednesdays | Wednesdays aligned with NG1 | Median / 95th-pct gap vs other source (abs log) |
|---|---|---|---|---|---|---|
| 1999-01 to 2006-12 (417 Weds) | FRED | 573 | 1,426 | **324** | 93 | 0.33% / 3.1% (572 common days) |
| | Bloomberg | 1,994 | 4 | 4 | 413 | |
| 2007-01 to 2019-12 (678) | FRED | 3,217 | 79 | 19 | 659 | 0.24% / 2.2% |
| | Bloomberg | 3,252 | 23 | 6 | 672 | |
| 2020-01 to 2021-04 (70) | FRED | 334 | 2 | 1 | 69 | **3.0% / 11.9%** |
| | Bloomberg | 274 | **67** | 2 | 68 | |
| 2021-05 to 2026-11 (288) | FRED | 1,377 | 14 | 4 | 284 | 0.70% / 6.1% |
| | Bloomberg | 1,343 | 48 | 9 | 279 | |

FRED's Wednesday coverage by year:
- 1997: 53%
- 1998 to 2006: 13–35%
- 2007: 77% (it becomes daily-complete from April 2007)
- 2008 onwards: 96–100%

**Using FRED throughout would therefore shorten the usable natural-gas sample by 8 years**, starting it in April 2007 instead of January 1999 (roughly 1,020 instead of 1,450 weekly returns).

### 6.2 The 2020–21 timestamp problem [VERIFIED pattern]

| Diagnostic | 2019 | Jan 2020 to 12 Mar 2021 | 15 Mar to Dec 2021 |
|---|---|---|---|
| NYMEX trading Mondays missing in Bloomberg | 0 of 48 | **56 of 56** | 1 of 39 |
| Bloomberg prints on NYMEX holidays | 0 | **5** (04-10, 07-03, 11-26, 12-25, 01-01) | 0 |
| FRED prints on NYMEX holidays / missing Mondays | 0 / 1 | 0 / 0 | 0 / 0 |
| Bloomberg equals FRED same day (±0.005) | 64% | 6% | 4% |
| Bloomberg equals FRED previous day | 5% | 9% | 3% |
| Correlation of Bloomberg change with NG1, same day / previous day | 0.38 / 0.30 | **0.02 / 0.34** | 0.54 / 0.37 |
| Correlation of FRED change with NG1, same day / previous day | 0.29 / 0.23 | 0.31 / 0.16 | 0.47 / 0.37 |

**Interpretation [INFERENCE].**
- **The convention:** Henry Hub spot gas trades day-ahead. A price agreed on trade day D is for gas flowing on D+1, and Friday trades cover the weekend and Monday.
- **Bloomberg in the window:** a series dated by *flow* day has no Monday row, because Monday's gas was traded on Friday. It has rows on exchange holidays, because gas traded the day before still flows on the holiday. Bloomberg shows exactly this pattern in the window and nowhere else.
- **FRED/EIA:** FRED has the same trading-day calendar as NYMEX in every period, consistent with trade-day dating.
- **Error or convention:** the evidence comes from the calendar itself, not from correlation with futures. Whether Bloomberg's dating is an error or a deliberate convention is [UNRESOLVED]. Either way it is incompatible with futures settlements, which are dated by trade day.
- **Precision:** Bloomberg also switches between 2-decimal and 4-decimal values over time (4-decimal in 2013–17 and from 2020). That suggests its underlying assessment changed more than once [UNRESOLVED].

**Why we do not simply shift Bloomberg by one day.** A shifted series would still differ from FRED by a median of 3%, because exact matches are rare even after shifting. It would also still lack Uri. FRED is complete, correctly dated and official in this window, so there is no reason to repair Bloomberg.

### 6.3 Winter Storm Uri

| | Tue 02-16 | Wed 02-17 | Thu 02-18 | Fri 02-19 | NG1 (NGH21) 02-10 to 02-17 |
|---|---|---|---|---|---|
| FRED | 11.32 | **23.86** | 8.56 | 4.96 | 2.911 to 3.219 |
| Bloomberg | none | none | none | 6.67 | |

Weekly representation:

| Week ending | Primary (FRED): spot / futures / basis change | Bloomberg as delivered |
|---|---|---|
| 2021-02-17 | +1.848 / +0.101 / **+1.747** | No observation (Wed, Tue and the Monday holiday all missing) |
| 2021-02-24 | −2.143 / −0.081 / **−2.061** | Undefined (previous week missing) |

Implications, all [VERIFIED] as descriptive statistics with no hedge estimated:
- **Weekly spot returns:** the two Uri weeks are the minimum and maximum of all 1,449 natural-gas spot returns.
- **Basis:** they are also the two largest basis changes, larger than the next one (2018-01-03, +0.72) by a factor of 2.4–2.9.
- **Tail measures:** spot 1% CVaR is −0.537 with Uri and −0.413 without; 99% CVaR is 0.566 vs 0.463. Basis-change 1% CVaR is −0.453 vs −0.330.
- **Correlation:** 0.569 with Uri, 0.665 without.
- **Rolling windows:** a 52-week window that contains these weeks has its tails set by them for a full year, and a 260-week window for five years.
- **Sampling-day sensitivity:** Wednesday sampling happened to land on the peak day. Tuesday sampling would have seen 11.32, Thursday 8.56. In January 2026 the reverse happened: FRED peaked at 30.72 on Friday 01-23, but the sampled Wednesdays were 4.96 and 9.34. Single-day physical spikes interact with any fixed sampling day. That is a genuine feature of weekly spot data and is documented here, not adjusted.
- **What must not happen:** replacing the missing Bloomberg days with the previous day's price would remove the event. We do not do that. The primary series uses FRED, which observed it.

### 6.4 The September 2025 bad print [VERIFIED]

| | Fri 09-26 | **Mon 09-29** | Tue 09-30 | Wed 10-01 |
|---|---|---|---|---|
| Bloomberg | 2.86 | **0.2571** | 3.15 | 3.23 |
| FRED | 2.90 | 2.93 | 3.12 | 3.24 |
| NG1 | 2.835 (NGV25) | 3.267 (NGX25) | 3.303 | 3.476 |

- **Classification:** a single-day value about 90% below both neighbours and both other sources, which immediately reverts. It is treated as a bad print, not a market event.
- **Effect:** it is a Monday, so no weekly interval in any option uses it. Weekly returns are unaffected even for Bloomberg-only.
- **Handling:** the raw value is preserved and the exclusion is logged in `processed_data_log.csv`.

### 6.5 Source options compared (`option_comparison`)

| Option | Weekly returns | First return | Spot–futures correlation | Uri | Main problems |
|---|---|---|---|---|---|
| **A.** FRED + Bloomberg futures | 1,220 total, about 1,023 from 2007-04-04 | 1997, but sparse until 2007-04 | 0.538 (0.580 in 2007–19) | Kept | Unusable before 2007 (187 of 417 Wednesdays in 1999–2006 have no observation) |
| **B.** Bloomberg as delivered | 1,450 | 1999-01-13 | 0.662 | **Missing** | Flow-dated 2020–21, Rita stale run, bad print, precision changes |
| B with exclusions | 1,386 | 1999-01-13 | 0.668 | Missing | Loses 2020-01 to 2021-03 |
| **C. Composite (primary)** | **1,449** | **1999-01-13** | **0.569** | **Kept** | One source transition, at 2007-04 |

### 6.6 Preserving basis risk

Natural gas has by far the lowest spot–futures correlation in the dataset (0.569, against 0.94–0.996 elsewhere). The table below separates what this stage *removed* from what it *kept*.

| Source of low correlation | Present? | Treatment |
|---|---|---|
| 1. Genuine economic basis (weather, storage, pipeline constraints, day-ahead vs next-month delivery) | Yes, dominant. Even in 2007–2019 with clean FRED data, correlation is 0.58 | **Kept and measured** |
| 2. Settlement-time differences (spot traded in the morning, futures settled in the afternoon) | Yes, inherent | Kept; cannot be fixed with daily data |
| 3. Timestamp errors (Bloomberg flow-dated 2020–21) | Yes in Bloomberg | **Removed** by using FRED there |
| 4. Contract-roll artifacts (splices) | Yes in generics (e.g., 2026-02-04, −0.77) | **Removed** by matched-contract returns |
| 5. Missing data | Small (2 weeks; Rita) | Flagged; never filled |
| 6. Bad prints | 1 (2025-09-29) | Excluded and logged; affected no weekly return |
| 7. Source-definition differences | Bloomberg vs FRED in 2007–19: correlation 0.591 vs 0.580, spot std 0.087 vs 0.085 | Transition does not create an artifact; on 2007-04-04 both print 7.46 |

The segment difference, 0.725 for 1999–2007 vs 0.534 for 2007–2026, mainly reflects **era**, not source. In the overlap years both sources give the same correlation. Natural-gas spot became much more weather-spike-driven after 2007.

**Low correlation is not evidence that the naive hedge fails.** It tells us that basis risk will matter in Stage 2. Whether an estimated hedge ratio improves on 1:1 out of sample is an empirical question for the backtest.

### 6.7 Recommendation [DECISION]

- **Primary: Option C.**
  - Bloomberg `NGUSHHUB` for weekly intervals starting before 2007-04-01; FRED/EIA `DHHNGSP` from then on. Each return uses one source at both ends.
  - Within each segment, a missing price is never taken from the other source.
  - The switch date was fixed from coverage alone: the first month from which FRED reports on ≥ 90% of NG1 trading days.
  - The Bloomberg segment (1999-01 to 2007-03) has passed these checks:
    - trade-day calendar, with no missing Mondays and no holiday prints;
    - a median gap of 0.3% to FRED on the 572 days both report;
    - one artifact (Rita) excluded.
- **Sensitivity: Option A** (FRED only). Filtering the same file on `spot_source == "FRED:DHHNGSP"` gives 1,022 returns from 2007-04-11; the separately built Option A starts one week earlier.
- **Why not A as primary:** it discards 1999–2006, which contains major tail events (winter 2000–01, February 2003, Katrina/Rita) that matter for a tail-risk study. A remains the cleanest single-source check.
- **Your preferred combination**, FRED spot + Bloomberg futures, is fully adopted from 2007 onward. Before 2007 it is not feasible.

---

## 7. Weekly observation and return methodology (Part 6)

**Observation rule.** For target Wednesday T, the observation date is the latest day d ∈ {T, T−1, T−2} on which all of the following exist **on the same day d**:
- the spot price from the source of the interval ending at T;
- the spot price from the source of the interval starting at T;
- the price of the contract held over the interval ending at T;
- the price of the contract held over the next interval.

The observation date can never be on or before the previous week's observation.

**Returns.** For the interval (obs<sub>T−7</sub>, obs<sub>T</sub>] with held contract c:
- r<sub>spot</sub> = ln(S(obs<sub>T</sub>) / S(obs<sub>T−7</sub>)), with S from one source;
- r<sub>fut</sub> = ln(F<sub>c</sub>(obs<sub>T</sub>) / F<sub>c</sub>(obs<sub>T−7</sub>)), with the same contract c.

**Definitions:**
- **Basis level:** ln(S/F<sub>c</sub>).
- **Basis change (the 1:1 residual, used here only as a data diagnostic):** Δb = r<sub>spot</sub> − r<sub>fut</sub>.

**Validity.** A return is defined only if:
- both observations exist;
- the holding period is ≤ 9 days;
- all four prices are > 0.

Otherwise `return_defined = False`, with the reason in `exclusion_reason`.

**No look-ahead [VERIFIED by test].** The held contract is chosen from the published contract calendar only. Prices dated after T are never used for row T. Rebuilding with all prices after 2020-04-22 deleted gives identical rows up to that date.

**Sample definitions.**

| Sample | Definition | Actual |
|---|---|---|
| H1 original | Target Wednesdays 1990-01-03 to 2023-06-28 | First return 1990-01-10; 1,710–1,747 returns |
| H1 extension | 2023-07-05 to 2026-11-04 (last Wednesday before the 2026-11-09 pull) | 175 returns each |
| Bitcoin | From the first Wednesday after the CME launch (2017-12-18 trade date) | First return 2017-12-27; 463 returns |
| Natural gas | From the first Bloomberg Henry Hub Wednesday | First return 1999-01-13; 1,449 returns |

**Deviations from the proposal.** These need a proposal amendment **[DECISION]**:
- natural gas starts in 1999, not 1997 (no Bloomberg spot before 1999; FRED too sparse);
- WTI spot is FRED/EIA, not Bloomberg;
- gold spot is XAU, not LBMA;
- GBP spot is Bloomberg, not WM/Reuters.

**Data dictionary.** See the Appendix.

---

## 8. Validation (Part 7)

### 8.1 Automated tests

`tests/test_stage1b.py`, 31 tests, all passing:

| Requirement | Tests |
|---|---|
| 1. Missing and duplicate dates | `test_duplicate_dates_rejected`, `test_unsorted_dates_rejected`, `test_blanks_become_nan_not_filled`, `test_one_row_per_market_week` |
| 2. Spot–futures alignment | `test_prices_match_raw_on_obs_dates` (300 random rows re-read from raw by an independent parser), `test_obs_date_within_lookback` |
| 3. Positive prices for logs | `test_logs_only_of_positive_prices`, `test_returns_recompute` |
| 4. No silent bridging | `test_prev_obs_is_previous_weeks_obs`, `test_week_after_missing_week_is_undefined` |
| 5. Contract identity and expiry | `test_contract_identity_independent_rank` (all 9,561 defined rows, rank re-derived from the calendar), `test_held_contract_alive_and_before_trigger`, `test_cycles_and_phantoms`, `test_contract_months_never_go_backwards`, `test_sp_to_es_switch` |
| 6. Roll-adjusted returns | `test_same_contract_both_ends`, plus the manual checks below |
| 7. BP units | `test_bp_unit_normalisation` |
| 8. Sample boundaries | `test_sample_boundaries` |
| 9. Missing-week handling | `test_strict_rule_is_subset`, `test_week_after_missing_week_is_undefined` |
| 10. Stress-event preservation | `test_stress_events_preserved`, `test_exclusions_logged` |
| 11. No look-ahead | `test_no_lookahead`, `test_held_contract_rule_uses_calendar_only` |
| 12. Raw immutability | `test_hashes_equal_stage1_inventory`, `test_no_processed_output_inside_raw` |
| Manual checks | Six hand-computed weeks with prices copied from the raw CSVs: WTI 2020-03-18, 2020-04-15, 2020-04-22; NG 2021-02-17, 2021-02-24, 2026-02-04 |

Two defects were caught by these tests during development and fixed:
- CSV output had been rounding prices to 6 significant digits.
- The exclusion log had omitted exclusions that no interval happened to touch.

### 8.2 Economic validation (`audit/results/weekly_validation_summary.csv`)

Full samples:

| Market | Returns | Spot std | Futures std | Correlation | Basis-change std | Largest abs basis change | Roll intervals | Excluded |
|---|---|---|---|---|---|---|---|---|
| WTI | 1,885 | 0.0556 | 0.0546 | 0.953 | 0.017 | 0.256 (2020-04-22) | 439 | 37 |
| GBP/USD | 1,922 | 0.0130 | 0.0131 | 0.990 | 0.002 | 0.028 | 147 | 0 |
| S&P 500 | 1,922 | 0.0223 | 0.0225 | 0.996 | 0.002 | 0.012 | 147 | 0 |
| Gold | 1,920 | 0.0225 | 0.0226 | 0.966 | 0.006 | 0.060 | 221 | 2 |
| Bitcoin | 463 | 0.0913 | 0.0908 | 0.942 | 0.031 | 0.152 | 107 | 0 |
| Natural gas | 1,449 | 0.1291 | 0.0736 | 0.569 | 0.106 | 2.061 (Uri) | 333 | 3 |

- **Alternative roll rule:** correlation with spot is nearly unchanged (WTI 0.943, NG 0.546; others identical to 3 decimals).
- **Bitcoin:** the XBTUSD spot sensitivity correlates 0.989 with futures, against 0.942 for BRR, and BRR vs XBTUSD correlate 0.938.
  - BRR is fixed at 4 p.m. London. CME futures settle in the U.S. afternoon (external facts, not verifiable in our files).
  - The roughly 5-hour gap in a 24/7 market adds basis noise that is about timing, not economics. **[DECISION]** BRR stays primary as pre-specified, with XBTUSD as a required sensitivity.

---

## 9. Financial reasoning for each material issue (Part 9)

| Issue | 1. What the data shows | 2. Why it matters for hedging | 3. Possible distortion | 4. Options considered | 5. Recommendation | 6. Verification | 7. Remaining limits |
|---|---|---|---|---|---|---|---|
| **WTI spot gaps** | 165 missing Wednesdays; EIA itself is blank | A hedge return needs spot and futures over the *same* interval | Filling spot with futures removes basis, so hedges look perfect. Bridging gaps creates 2-week "weekly" returns that inflate variance and VaR | A strict; B lookback 1 or 2 days; C recovery | B2 primary, A sensitivity | Raw re-read tests; strict-subset test; selection-bias check | 19 weeks unrecoverable |
| **Negative WTI price** | −37.63 / −36.98 on Monday 2020-04-20 | Log returns are undefined through a nonpositive price | Replacing it with 0.01 creates an invented −700% return. Deleting and bridging hides the stress | Flag-only; simple-return sensitivity | Kept in raw; no interval uses it | `test_stress_events_preserved`; April table | None for weekly data |
| **Roll construction** | Generic splices include calendar spreads (e.g., +0.27 in April 2020, −0.69 in Feb 2026) | The hedger earns the held contract's return, not a spread between contracts | Splices create false futures gains and losses at rolls. This misstates futures volatility, the tail, and the residual risk of a 1:1 hedge, in both directions | Splice; matched contract; split roll at expiry | Matched contract (primary); splice only as a replication diagnostic | Independent rank test; manual weeks | No individual-contract files; generic depth is 3 |
| **CL/NG roll rule** | Paper's rule is infeasible for contracts that expire before their month | The rule decides which contract's risk is being hedged | Rolling too late samples thin, expiring contracts (penultimate-day prices) | Nearest-to-LTD; roll in the LTD month | Nearest-to-LTD primary, earlier roll as sensitivity | `held_roll_summary`; alt columns | Penultimate-day sampling in about 30% of rolls |
| **NG spot dating** | Bloomberg flow-dated, Jan 2020 to Mar 2021 | Spot and futures must refer to the same trading day | A one-day offset turns timing into fake basis. Same-day correlation falls to 0.02 | Shift Bloomberg; FRED; composite | FRED in that window (composite) | Calendar diagnostics | Cause unresolved |
| **Uri** | Spot ×6 in a week; futures +10% | This is genuine basis risk at its most extreme | Dropping it understates tail risk. Keeping it means a few weeks drive NG tail statistics | Bloomberg (misses it); FRED (keeps it) | Keep (FRED) | Manual tests | Sensitive to the sampling weekday |
| **Bad print, Sep 2025** | 0.2571 vs about 2.9 | A single bad price creates two false ±2.4 log moves | False extreme losses and gains | Keep; exclude and log | Exclude and log | Log test | None |
| **S&P product switch** | Big SP delisted after Sep 2021 | Continuity of the hedge instrument | Splicing products at an arbitrary date | ES throughout; SP then ES at a roll | SP then ES at the 2021-09 roll | SP/ES overlap correlation 1.000 | None material |
| **Gold first notice day** | Paper's rule samples the old contract on its FND in 36 weeks | A hedger avoids delivery notices | Small; settlements remain valid | Paper's rule; roll a day earlier | Keep paper's rule (pending approval) | `notice_period_check` | n/a |
| **BTC timing** | BRR at 4 p.m. London vs U.S. afternoon futures settlement | Timing mismatch in a 24/7 market | Adds artificial basis noise | BRR; XBTUSD | BRR primary, XBTUSD sensitivity | Correlation diagnostics | Exact settlement times not in our files |

---

## 10. What remains provisional

1. Every **[DECISION]** item (Section 11). The dataset can be regenerated in about 2 minutes after any change to `src/frm_data/config.py`.
2. How the paper built its futures series. The splice evidence is strong but indirect, and it matters for how close an H1 replication can get.
3. FRED WTI's 15–30% discount to CL1 in late March 2020, and its 1–6% premium since 2024. Both are official EIA values, kept as observed, with causes [UNRESOLVED].
4. The cause of Bloomberg's Henry Hub date and precision changes.
5. CFNAI and USREC regime labels are not yet attached to weekly rows. That belongs in Stage 2 setup. CFNAI ends 2026-09, so the last 5 weeks will have no label.

---

## 11. Questions requiring approval

1. **Weekly rule:** B2 (Wednesday, else Tuesday, else Monday, same day for both legs) as primary, and strict Wednesday as sensitivity?
2. **Natural-gas spot:** the composite (Bloomberg before 2007-04, FRED after) as primary, and FRED-only from 2007-04 as sensitivity? The alternative is FRED-only as primary, with a sample starting in 2007.
3. **CL/NG roll:** keep "nearest contract whose LTD is after the target Wednesday", or add a margin (e.g., roll at least 3 business days before LTD) to avoid penultimate-day prices?
4. **Paper replication:** add a clearly labelled spliced-generic futures series as an H1 replication-only sensitivity, given the Table 2 evidence?
5. **Bitcoin spot:** keep BRR as primary, with XBTUSD as sensitivity?
6. **Gold:** keep the paper's first-of-month roll (36 first-notice-day samplings), or roll one business day earlier?
7. **Proposal amendment:** natural gas from 1999; WTI spot from FRED/EIA; gold XAU; GBP Bloomberg; matched-contract futures returns.
8. **Uri reporting:** keep the observed Wednesday prices as primary. In Stage 2, report natural-gas results with and without the two Uri weeks as a pre-specified robustness check?

---

## 12. Files created and changed

**Created**
- **Code:**
  - `src/frm_data/__init__.py`, `config.py` (all rules), `io.py`, `contracts.py`, `weekly.py`, `validation.py`
  - `audit/stage1b_remediation.py` (the run script)
  - `tests/test_stage1b.py`
- **Data:**
  - `data/processed/weekly_market_returns.csv` (9,609 rows: 6 markets × target weeks)
  - `data/processed/processed_data_log.csv` (253 excluded raw observations, 48 undefined intervals, substitutions)
- **External verification:** `data/external/verification_2026-11-11/` (live FRED CSVs and EIA XLS files)
- **Results:**
  - `audit/results/wti_missing_data_analysis.csv`
  - `audit/results/wti_april2020_review.csv`
  - `audit/results/natural_gas_source_comparison.csv`
  - `audit/results/natural_gas_stress_events.csv`
  - `audit/results/roll_mapping_validation.csv`
  - `audit/results/weekly_validation_summary.csv`
  - `audit/results/stage1b_run_log.txt`
- **Documents:**
  - `audit/DATA_REMEDIATION_REPORT.md` (this file)

**Changed**
- `requirements.txt` (at the top level): includes `xlrd`, used only for the EIA verification files. `xlrd` was installed into `audit/.venv`.

**Not changed:** anything under `data/raw/`, the Stage 1 report and its CSVs, the project context document and the proposal.

---

## Appendix: data dictionary for `data/processed/weekly_market_returns.csv`

| Column | Meaning |
|---|---|
| `market` | WTI, GBPUSD, SP500, GOLD, BTC, NATGAS |
| `sample_period` | `original_1990_2023`, `extension_2023_2026` (H1); `h2_full` (BTC, NATGAS) |
| `target_wed` | The Wednesday this row represents (interval end) |
| `obs_date`, `prev_obs_date` | Actual observation dates at interval end and start (same for both legs) |
| `holding_days` | `obs_date − prev_obs_date` in calendar days |
| `obs_displaced_days`, `prev_obs_displaced_days` | Days before the target Wednesday (0 = Wednesday) |
| `strict_wednesday` | Both ends on target Wednesdays (Approach A subset) |
| `spot_source`, `spot_price_prev`, `spot_price`, `spot_logret` | Spot leg (one source for both ends) |
| `fut_root`, `fut_contract`, `fut_contract_month`, `fut_ltd` | Held contract (primary rule) |
| `roll_trigger` | Date that ends this contract's eligibility under the primary rule |
| `roll_at_interval_start` | Contract differs from the previous interval's (the roll happened at `prev_obs_date`) |
| `fut_generic_prev`, `fut_generic` | Bloomberg generic carrying that contract's price at each end |
| `fut_price_prev`, `fut_price`, `fut_logret` | Matched-contract futures leg (BP ÷ 100) |
| `alt_roll_rule`, `alt_fut_contract`, `alt_fut_price_prev`, `alt_fut_price`, `alt_fut_logret` | Same dates, alternative roll rule |
| `spot_alt_source`, `spot_alt_*` | BTC only: XBTUSD on the same dates |
| `nonpositive_price` | Any of the four prices ≤ 0 |
| `reason_obs_missing` | Which required price was missing when no observation date was found |
| `exclusion_reason` | Why the return is undefined (blank if defined) |
| `return_defined`, `in_primary_sample` | The return is valid and belongs to the primary sample |
