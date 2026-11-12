# Stage 1: Raw Data Integrity Audit

**Project:** FRE 6123, *Is the Naïve Hedge Still Hard to Beat?* (replication and extension of Cao & Conlon, 2025)
**Audit date:** 2026-11-11 · **Data pulled:** 2026-11-09 (per `data/raw/manifest.csv`)
**Scope:** raw files under `data/raw/` only. No weekly returns were built, no generic-to-contract mapping or roll rule was applied, and no hedge models were run. Daily log changes were used only to screen for anomalies.

---

## How to read this report

Every claim is tagged with one of three labels:

| Label | Meaning |
|---|---|
| **[VERIFIED]** | Directly checked in the raw files by the audit script; reproducible. |
| **[INTERPRETATION]** | A reasonable explanation of a verified fact, not proven by the files alone. |
| **[UNRESOLVED]** | Cannot be settled from the files we have; needs an outside check or a team decision. |

The anomaly IDs (A01 to A34) refer to rows in `audit/results/anomaly_register.csv`.

---

## 1. Reproducing the audit

```
py -3.12 -m venv audit/.venv
audit/.venv/Scripts/python.exe -m pip install -r audit/requirements.txt
audit/.venv/Scripts/python.exe -I audit/raw_data_audit.py
```

- **Environment used:** Python 3.12.8, pandas 3.1.1, numpy 2.5.4. The `mlfe` conda environment named in the project context does not exist on this machine, so an isolated venv was created under `audit/.venv`.
- **Read-only guarantee [VERIFIED]:** the script computes a SHA-256 hash of all 41 files under `data/raw/` before and after the run and stops with an error if any hash changes. `audit/results/run_log.txt` records `raw_files_unchanged_after_run=True`, and each file's hash is listed in the inventory.
- **No live cross-check:** outbound network access is blocked in this environment, so the FRED series could not be re-downloaded for comparison. This is why the FRED gap questions remain **[UNRESOLVED]**.

### Outputs

| File | Contents |
|---|---|
| `results/raw_data_inventory.csv` | One row per file and value column: path, source, identifier, type, size, SHA-256, columns, dtypes, frequency, first/last valid date, rows, valid observations, blanks, non-numeric values, duplicate/unsorted dates, nonpositive prices, weekend rows |
| `results/data_quality_summary.csv` | One row per series: Wednesday coverage (whole span and to Jun-2023), largest calendar gap, stale runs, outlier counts by class, largest daily move |
| `results/manifest_comparison.csv` | Manifest metadata against the actual files, plus unexpected and missing files |
| `results/anomaly_register.csv` | 34 anomalies with evidence, classification, severity, why it matters, risk if ignored, recommended action and verification test |
| `results/supporting/*.csv` | Evidence tables: Wednesday coverage with missing dates, cross-source level ratios (overall and by year), daily outlier screen, contract-calendar checks, generic roll-cycle test, Henry Hub date-alignment tests |

---

## 2. Executive summary

### 2.1 Coverage by market

Wednesday counts run from the first Wednesday in the series' span to 2026-11-04. "Missing" means no valid price on that Wednesday.

| Market | Spot series (span) | Missing Wednesdays (spot) | Futures generics (span) | Missing Wednesdays (front) | Verdict for Stage 2 |
|---|---|---|---|---|---|
| WTI | FRED `DCOILWTICO` 1986-01-02 to 2026-11-03 | **164 / 1,922 (8.5%)** | `CL1-3` 1990-01-02 to 2026-11-09 | 20 (holidays and closures) | Usable with qualifications (A02, A03, A04) |
| GBP/USD | `GBPUSD` 1990-01-01 to 2026-11-09 | 0 / 1,923 | `BP1-3` 1990-01-02 to 2026-11-09 (US cents) | 19 | Usable (divide BP by 100) |
| S&P 500 | `SPX` 1990-01-02 to 2026-11-09 | 21 | `SP1-2` to 2021-09-17; `ES1-2` from 1997-09-09 | 16 (SP1), 13 (ES1) | Usable (choose SP→ES switch point) |
| Gold | `XAU` 1990-01-02 to 2026-11-09 (LBMA PM file empty) | 6 | `GC1-3` 1990-01-02 to 2026-11-09 | 20 | Usable (disclose XAU substitution) |
| Bitcoin | `BRR` 2016-11-14 to 2026-11-09 | 0 / 521 | `BTC1-3` 2017-12-15 to 2026-11-09 | 6 | Usable with sensitivity (A17, A19) |
| Natural gas | `NGUSHHUB` 1999-01-04 to 2026-11-09 | 21 / 1,453 (1.4%) | `NG1-3` 1990-04-03 to 2026-11-09 | 20 | **Needs decisions first** (A22, A25) |
| Regime | `CFNAI` 1967-03 to 2026-09; `USREC` 1854-12 to 2026-10 | no missing months | n/a | n/a | Usable; last ~5 weeks have no CFNAI label |

### 2.2 The most important findings

1. **Bloomberg Henry Hub appears to be dated one trading day late from January 2020 to April 2021** (A25, new). In that window its daily changes are uncorrelated with same-day NG1 futures (0.03) but correlated with the previous day's (0.34), and it matches FRED's previous-day value in 14 of 16 months. The window contains COVID and Winter Storm Uri, both H2 stress windows.
2. **Bloomberg Henry Hub has no prints for the peak of Winter Storm Uri** (2021-02-16 to 02-18, including Wednesday 02-17, when FRED shows $23.86) (A22).
3. **FRED WTI spot is missing on 164 Wednesdays, not 19** as the project context states. The gaps cluster in 1994 to 2006 (A02).
4. **FRED WTI has traded 1 to 6% above CL1 since 2024**, after decades at a ratio of 1.000, and was ~30% below CL1 in late March 2020 (A03, A04).
5. **Three series, not one, print negative on 2020-04-20.** That includes the series chosen as WTI spot (FRED, −36.98) (A01).
6. **Bloomberg's "WTI Cushing spot" (`USCRWTIC`) is futures-based.** It equals CL1 to the cent on 86% of days, so it must not be used as spot (A05).
7. **One verified bad print:** `NGUSHHUB` = 0.2571 on 2025-09-29, against 2.93 at FRED and 3.27 for NG1 (A21).
8. **Confirmed conventions:** BP futures are quoted in US cents (÷100); GC generics follow the active cycle (G, J, M, Q, V, Z); BP generics skip serial months; the SP chain contains 12 never-traded contracts tied on one date (A07, A14, A08, A10).

### 2.3 Overall verdict

**The raw data is suitable for Stage 2 with qualifications.** No futures generic shows a verified price error. For GBP/USD, S&P 500 and gold the data is ready now. WTI is usable, but the size of its spot gap should be confirmed or explicitly accepted. Natural gas needs two decisions before its spot series is fixed (Section 7). This is not a statement that the data is clean or complete. Section 8 lists what this audit could not check.

---

## 3. Inventory and manifest comparison

### 3.1 What is in `data/raw/`

The folder holds 41 files: 30 Bloomberg price files, 7 contract calendars, 4 FRED series and `manifest.csv`.

**[VERIFIED] Basic integrity holds in every file:**
- no duplicate dates and no unsorted dates;
- no unparseable dates and no non-numeric values;
- no weekend rows, except in 7-day crypto series (`BRR`, `XBTUSD`) and in monthly series whose first-of-month date falls on a weekend.

**[VERIFIED] Blanks.** Only the two FRED daily series contain blanks:

| Series | Blank rows | Total rows |
|---|---:|---:|
| `DCOILWTICO` | 1,117 | 10,654 |
| `DHHNGSP` | 2,059 | 7,781 |

**[VERIFIED] Nonpositive prices.** Three series contain a nonpositive price, all on 2020-04-20:

| Series | Price on 2020-04-20 |
|---|---:|
| `CL1` | −37.63 |
| `USCRWTIC` | −37.63 |
| `DCOILWTICO` | −36.98 |

**[VERIFIED] One empty file.** `GOLDLNPM_Index.csv` (LBMA Gold PM) contains a header and no data.

### 3.2 Manifest against files

**[VERIFIED] Every manifest row has a matching file, and every first date, last date and row count matches.**
- The manifest's row counts for the two FRED series include blank rows. Valid observations are 9,537 (`DCOILWTICO`) and 5,722 (`DHHNGSP`), not 10,654 and 7,781.
- Series the manifest itself marks as starting later than expected:

| Series | First date | Note |
|---|---|---|
| `USCRWTIC` | 2017 | |
| `BRR` | 2016-11-14 | |
| `NGUSHHUB` | 1999 | |
| `ES3` | 1997-12-18 | Also very sparse |

- SP1 and SP2 end on 2021-09-17 because CME delisted the big S&P contract. That end date is genuine.
- There are no unexpected files.

**[VERIFIED] Missing against the project context.** §5 of `FRE6123_Project_Context.md` lists `data/raw/eia/` (`RWTCd.xls`, `RNGWHHDd.xls`, `RWTC.csv`, `RNGWHHD.csv`), but that folder does not exist (A34). The claim that the EIA originals are identical to FRED, including the gaps, therefore cannot be checked.

Outside `data/raw/` (not audited): `__MACOSX/` contains macOS resource-fork files with no data value, and `Projects/fedfunds_2010_2026.csv` is unrelated to this project.

---

## 4. Market-by-market validation

### 4.1 WTI crude oil

- **[VERIFIED] Coverage.**
  - FRED spot runs from 1986-01-02 to 2026-11-03, a Tuesday, so the last FRED Wednesday is 2026-10-28.
  - CL1-3 run from 1990-01-02 to 2026-11-09.
  - FRED is missing 164 of 1,922 Wednesdays: 161 up to June 2023, and 122 blank days in 2003 alone.
  - CL1 traded on 705 of FRED's 1,117 blank days, so most of the gaps are not exchange holidays.
- **[VERIFIED] April 2020.**
  - On 2020-04-20, the day before the May contract expired: CL1 −37.63, `USCRWTIC` −37.63, FRED −36.98.
  - On 2020-04-21: CL1 10.01, the May contract's final settlement.
  - On 2020-04-22, a Wednesday, all three series are positive (FRED 13.64, CL1 13.78).
- **[VERIFIED] `USCRWTIC` equals CL1 on 85.9% of days.**
  - **[INTERPRETATION]** It is a front-month-futures-based assessment, not an independent physical spot price.
- **[VERIFIED] FRED/CL1 level ratio:**

| Period | Median FRED/CL1 |
|---|---:|
| 1990–2023 (each year) | 1.000 |
| 2024 onward | 1.012 |
| October 2026 (monthly median) | 1.06 |

  - **[UNRESOLVED]** It is not clear whether this reflects a change in the EIA/LSEG assessment method or a genuine physical premium. The steep 2022 backwardation produced no such premium.
- **[VERIFIED] 2020-03-19 to 03-31.** FRED moved independently of CL1 on several days, reaching 14.10 against CL1 at 20.09 on 2020-03-30.
  - **[INTERPRETATION]** Possibly a genuine physical Cushing dislocation during the storage crisis, but unconfirmed.

### 4.2 GBP/USD

- **[VERIFIED] Units.**
  - The median BP1/GBPUSD ratio is 99.96 (p1 98.70, p99 100.38), so CME pound futures are quoted in **US cents**.
  - After dividing by 100, the median ratio is 0.9996.
- **[INTERPRETATION]** The sign of the remaining premium or discount follows covered interest parity: futures sit below spot when UK rates exceed US rates, and above spot when US rates are higher. The yearly median BP1/spot ratio is below 100 in most years from 1990 to 2016. It is above 100 in 2000, 2006 and every year from 2016 to 2025, which are broadly the periods when US rates were at or above UK rates (`cross_source_yearly_ratio.csv`). This was checked by eye, not against a rate series. This is a useful sanity check that spot and futures are aligned correctly.
- **[VERIFIED] Division by 100 is necessary** for any level-based check (basis, ratios). It does not change log returns.
- **[VERIFIED] Serial months.** The BP calendar lists serial months from 2017 onward, but the generics skip them:
  - 95% of quarterly-month expiries are followed by a G2/G1 spread jump the next day;
  - only 3% of serial-month expiries are.
- **[VERIFIED] BP3** has gaps of 39 days (to 1996-07-26) and 30 days (to 1990-04-18). BP3 is only needed for contract mapping.
- **[VERIFIED] Spot trades on US holidays** (0 missing Wednesdays) while futures do not (19 missing), so spot and futures dates must be paired.

### 4.3 S&P 500

- **[VERIFIED] Coverage.**
  - SP1/SP2 run from 1990-01-02 to 2021-09-17.
  - ES1/ES2 run from 1997-09-09, the E-mini launch.
  - ES3 is missing 34% of Wednesdays, with gaps of up to 1,092 days before 2007.
  - The overlap between SP and ES is 1997-09-09 to 2021-09-17, about 24 years.
- **[VERIFIED] SP1 equals ES1 to the cent** on 25.8% of days in 1997–2020 and 82.8% in 2021 (98% in 2021 Q2–Q3).
  - **[INTERPRETATION]** CME settled the big contract off E-mini prices as its liquidity disappeared. SP and ES levels are therefore effectively interchangeable during the overlap.
- **[VERIFIED] The two generics roll on different days.**
  - The big SP's last trading day was the Thursday (SPM21: 2021-06-17); ES's was the Friday.
  - On 2021-06-18, SP1 already shows the September contract (4153.5 = ES2), while ES1 shows the expiring June contract's final settlement (4187.25).
- **[VERIFIED] Phantom SP contracts.** `SP_contracts.csv` contains 12 contracts (SPZ21 through SPZ6) that were listed but delisted rather than traded to expiry. All have `LAST_TRADEABLE_DT = 2021-09-17`, and several use single-digit-year tickers.
- **[VERIFIED] SPX is the price index.** The ES1/SPX yearly median ranges from 0.997 to 1.006, which tracks interest rates minus the dividend yield. This is consistent with the paper's "S&P 500 Composite".

### 4.4 Gold

- **[VERIFIED] Spot.** LBMA Gold PM (`GOLDLNPM`), the paper's spot series, has no data. XAU covers 1990-01-02 to 2026-11-09 and is missing 6 Wednesdays.
- **[VERIFIED] Futures.** GC1-3 cover 1990-01-02 to 2026-11-09 and are missing 20 Wednesdays.
- **[VERIFIED] Delivery-month structure.** The GC calendar lists all 12 months, but the generics roll through the active months only (G, J, M, Q, V, Z):
  - 88% of active-month expiries are followed by a next-day spread jump;
  - 19% of inactive-month expiries are.
- **[VERIFIED] 2026-01-30.** XAU fell 9.0% and GC1 11.4% on the same day, corroborated across sources.
  - **[INTERPRETATION]** A genuine market event, not an error.
- **[INTERPRETATION]** XAU and COMEX settlement are sampled at different times. GC1/XAU p1/p99 is 0.990/1.011, and on volatile days spot sits above the front future (for example 2026-01-28).

### 4.5 Bitcoin

- **[VERIFIED] Spot.**
  - `BRR` runs from 2016-11-14 to 2026-11-09 and is never missing on a Wednesday.
  - It included weekend values up to 2022, almost none in 2023–2025, and some again in 2026 (A18). This has no effect on Wednesday sampling.
- **[VERIFIED] Futures.**
  - BTC1-3 start on Friday 2017-12-15, before CME bitcoin futures began trading (first trade date 2017-12-18).
  - The 2017-12-15 print of BTC1 (19,500) is 10.9% above BRR.
  - The calendar's earliest contract is BTCF18 (A17, **[UNRESOLVED]**).
- **[VERIFIED] Basis noise.** The BTC1/BRR daily ratio has wide tails (p1 0.945, p99 1.057).
  - **[INTERPRETATION]** BRR fixes at 4 pm London and CME settles around 4 pm New York. Intraday crashes between the two times appear as basis, as on 2019-06-26/27 (A20) and on Wednesday 2018-01-17, when BRR printed 9,489 against XBTUSD 11,377 (A19).

### 4.6 Natural gas

- **[VERIFIED] Coverage.**
  - Bloomberg `NGUSHHUB` runs from 1999-01-04 and is missing 21 Wednesdays.
  - FRED `DHHNGSP` runs from 1997-01-07 but is about 70% blank in 1997–2006 (405 Wednesdays missing in total). A 1997 start is therefore not possible with FRED.
  - NG1-3 run from 1990-04-03.
- **[VERIFIED] Bloomberg against FRED:**
  - identical in 2019 (median |log difference| 0.000);
  - Bloomberg apparently lagged one trading day from 2020-01 to 2021-04 (A25);
  - from mid-2021, aligned on the same day but not identical (median difference about 0.5–1.5%).
- **[VERIFIED] Bloomberg-specific defects:**
  - no prints during the Uri peak (A22);
  - one bad print on 2025-09-29 (A21);
  - 14.50 repeated for 9 trading days after Hurricane Rita in 2005, when FRED is blank (A26);
  - the last two values (2026-11-06 and 2026-11-09) are identical (A29).
- **[VERIFIED] Genuine spikes** are corroborated by both spot sources:

| Date | Bloomberg | FRED |
|---|---:|---:|
| 2024-01-12 | 13.72 | 13.20 |
| 2026-01-23 | 33.80 | 30.72 |
| 2026-01-26 | 31.12 | 25.01 |

  The sources differ by up to 24% at the peak (A23).
- **[VERIFIED] Weak basis.** The NG1/spot ratio has p1 0.87 and p99 1.35, the widest of the six markets (A28). Generic roll gaps are large: NG1 fell 47% when the squeezed Feb-2026 contract expired (A24).

### 4.7 Macroeconomic series

- **[VERIFIED] CFNAI.** Monthly from 1967-03 to 2026-09, with no missing months. Its minimum is −18.36 (April 2020). Since 1990, 47.2% of months are negative.
- **[VERIFIED] USREC.** Monthly from 1854-12 to 2026-10, with no missing months. Recession months since 1990:
  - 1990-08 to 1991-03
  - 2001-04 to 2001-11
  - 2008-01 to 2009-06
  - 2020-03 to 2020-04

  These match NBER chronology under FRED's convention (the month after the peak through the trough).
- **[INTERPRETATION]** CFNAI is revised over time, and our file is a single current vintage, so the paper's regime split may differ slightly. USREC's recent zeros are provisional until NBER makes its determination.

---

## 5. The significant issues, explained

The issues below are ordered by how much they could change the project's conclusions.

### Issue 1: Natural-gas spot dated one day late, Jan-2020 to Apr-2021 (A25) — high

- **What was found.**
  - In 14 of 16 months, Bloomberg Henry Hub on day *t* matches FRED on day *t−1*.
  - Its daily changes correlate 0.03 with same-day NG1 futures and 0.34 with the previous day's, against 0.31 same-day in 2017–2019.
  - FRED is normal in the same window.
  - Example: FRED jumps on 2021-02-11 (6.50); Bloomberg jumps on 2021-02-12 (6.51).
- **Why it matters.** Hedging works because spot and futures react to the same news on the same day. Basis risk is the part of the spot move the futures position does not offset. If the spot leg is shifted by a day, every week's spot return covers Tuesday to Tuesday while the futures return covers Wednesday to Wednesday.
- **What could go wrong.** About 70 weeks, including COVID and Uri, would show basis noise created by the data rather than by the market. Measured hedge effectiveness would fall for every model. Because OLS shrinks the hedge ratio when spot and futures look less correlated, the artifact would tend to favour OLS over the naïve hedge, which is exactly the H2 question.
- **Recommended solution.** For January 2020 to April 2021, use FRED `DHHNGSP` (which is complete in that window) as the NG spot, or shift Bloomberg back one trading day under a documented rule. Report a sensitivity either way. **This is your decision (D2).**
- **How to verify.** After the fix, the correlation of daily spot changes with same-day NG1 in the window should return to the 0.3 level seen in 2017–19 and 2021–23. Weekly spot–futures correlation in the window should be similar to neighbouring years.

### Issue 2: Uri peak missing in Bloomberg (A22) — high

- **What was found.** Bloomberg has no Henry Hub prices for 2021-02-16, 17 and 18. FRED shows 11.32, **23.86** and 8.56. The peak falls on a Wednesday.
- **Why it matters.** Uri is a named H2 stress window, and the spot spike with almost no futures response (NG1 3.22) is the textbook case of basis risk: no futures hedge, at any ratio, protects against it.
- **What could go wrong.** A "use the previous day" fallback rule would record 6.51 (from 02-12) for that Wednesday. The stress analysis would then miss the event entirely and overstate how well hedges worked during Uri.
- **Recommended solution.** Fill only the missing Bloomberg days from FRED, under a documented rule; the two sources' median ratio is about 1.000. Alternatively, keep Bloomberg only and present Uri with FRED as a side analysis. **Decision D3.**
- **How to verify.** A weekly table for January to March 2021 under both options, showing the spot return, futures return and hedged return.

### Issue 3: FRED WTI spot gaps and their size (A02) — high

- **What was found.** FRED WTI is missing 164 Wednesdays, 161 of them before July 2023. The gaps cluster in 1994–2006 (for example, 122 blank days in 2003). CL1 traded on 705 of the 1,117 blank days. The project context reports 19 missing weeks and 99.0% weekly spot coverage.
- **Why it matters.** WTI is the paper's headline market (naïve best in 9 of 12 cases). Each missing Wednesday either removes a hedged-return observation or forces a substitute day.
- **What could go wrong.**
  - The sample could differ from the paper's 1,728 weeks by about 8%.
  - A "latest earlier common day" rule would be applied about 160 times rather than 19.
  - If the gaps came from the pull rather than from FRED, we would be discarding good data without knowing it.
- **Recommended solution.** Before Stage 2, re-download `DCOILWTICO` from FRED and `RWTC` from EIA and compare them against this file. If the gaps are genuine, apply the common-date fallback and report how many weeks use it.
- **How to verify.** A diff report showing the count of dates where the fresh download has a value and our file is blank; zero means the file is faithful to the source.

> **[INTERPRETATION] A hint about the paper's sample.** There are 1,748 Wednesdays from January 1990 to June 2023. Front futures are missing on 17 of them (exchange holidays and closures such as 9/11 and the Nixon funeral). 1,748 − 17 = 1,731, so 1,730 returns, which is very close to the paper's 1,728. This suggests the paper dropped holiday weeks rather than substituting days. That is relevant to the sampling-rule decision (D4).

### Issue 4: FRED WTI above CL1 since 2024; March-2020 dislocation (A03, A04) — medium

- **What was found.**
  - The FRED/CL1 median ratio is 1.000 in every year from 1990 to 2023 (including 2022), 1.012 from 2024 on, and about 1.06 in October 2026.
  - At end-March 2020, FRED was 15–30% below CL1 for about a week, covering Wednesday 2020-03-25.
- **Why it matters.** A constant level gap would not matter for returns, but a gap that moves over time is basis risk. H1's "persistence to 2026" test relies on the 2023–2026 window, which is exactly where the drift appears.
- **What could go wrong.** A source artifact could be misread as evidence that the naïve hedge stopped working after 2023.
- **Recommended solution.** Check EIA's notes on the RWTC methodology. In Stage 2, report WTI results for 2023–2026 with FRED spot and, as a sensitivity, with CL1 as a spot proxy. Flag the March-2020 week and show results with and without it.
- **How to verify.** Weekly basis volatility by year, plus the sensitivity tables.

### Issue 5: Negative oil prices in three series (A01) — high (but contained)

- **What was found.** −37.63 (CL1 and `USCRWTIC`) and −36.98 (FRED) on Monday 2020-04-20. Wednesday prices are positive.
- **Why it matters.** The paper uses log returns, which are undefined for prices ≤ 0. The week around 2020-04-20 is one of the most extreme WTI observations and strongly influences the 1% tail.
- **What could go wrong.**
  - A fallback rule that reaches back to Monday would crash or silently produce NaN.
  - A roll rule that holds the May contract to expiry would book a huge artificial futures loss.
- **Recommended solution.** Never modify the raw value. Stage 2 code should assert that price > 0 before every log, and the roll rule must exit CLK20 before 2020-04-20. Both the paper's "first day of the contract month" convention and the context's "5 business days before LTD" proposal do this.
- **How to verify.** A unit test plus a printed review of the weekly rows for 2020-04-08 to 2020-05-06.

### Issue 6: `USCRWTIC` is not a real spot series (A05) — medium

- **What was found.** It equals CL1 to the cent on 86% of days and differs mainly around rolls.
- **Why it matters.** Using a futures price as "spot" makes basis risk zero by construction.
- **What could go wrong.** Every hedge would look nearly perfect and the naïve hedge would win trivially. The replication would look successful for the wrong reason.
- **Recommended solution.** Do not use `USCRWTIC` as the spot leg; keep it as a cross-check only. (The proposal's Table 1 lists Bloomberg as the WTI spot source and should be updated.)

### Issue 7: Natural-gas spot spikes and the source dependence of the tail (A23) — high

- **What was found.** Spot spikes of four to six times the futures price in January 2024 and January 2026, confirmed by both spot sources. The two sources disagree by up to 24% at the peak.
- **Why it matters.** These spikes will dominate NG 1%/99% VaR and CVaR. No futures hedge offsets them, so they will drive the H2 natural-gas conclusion.
- **What could go wrong.**
  - Treating them as outliers and removing them would bias H2 toward "the naïve hedge works".
  - Using one source without disclosure makes the tail estimate depend on that source.
- **Recommended solution.** Keep the spikes. Report NG tail effectiveness under the primary spot series and under the other source as a sensitivity.

### Issue 8: Generic roll discontinuities (A24, and 57 roll-adjacent outliers) — high, but expected

- **What was found.** Large jumps in generic futures series occur on or just after contract expiries. The most extreme is NG1 −47% on 2026-01-29.
- **Why it matters.** A generic series splices different contracts together, and the jump is the price difference between them, not a return anyone earned.
- **What could go wrong.** Without roll correction, futures appear to crash, hedges appear to fail, and natural-gas results become meaningless.
- **Recommended solution.** Use same-contract returns in Stage 2 (the method in context §6) and filter the GC and BP calendars to their cycles. Drop the 12 phantom SP contracts and order contracts by `LAST_TRADEABLE_DT`, never by ticker (A31, because tickers like `BTCZ7` mean Dec-2027 now).
- **How to verify.** No weekly futures return should span two contracts, and implied roll dates should coincide with the spread jumps in `generic_roll_cycle_test.csv`.

### Issue 9: Gold spot substitution (A13) — medium

- **What was found.** The LBMA PM file is empty. XAU is the only gold spot series.
- **Why it matters.** The paper used the London PM fix (3 pm London), while XAU and COMEX are sampled later. The timing gap adds a little basis noise to every model.
- **Recommended solution.** Use XAU and state the deviation in the paper. If an LBMA series can be obtained from another source, run a 1990–2023 robustness check.

### Issue 10: Bitcoin timing basis (A19, A20, A17) — medium

- **What was found.**
  - BRR (4 pm London) and CME settlement (about 4 pm New York) are five hours apart.
  - On Wednesday 2018-01-17, BRR caught the intraday crash low (9,489) while futures settled at 10,945.
  - The futures series also start one trading day before CME launched.
- **Why it matters.** H2 argues that Bitcoin's basis is unstable. Part of the measured basis is simply timing.
- **What could go wrong.** We could overstate the economic basis risk, or let one timing artifact in the first 52-week window shape all hedge ratios estimated in 2018–2019.
- **Recommended solution.** Keep BRR, which is the CME settlement reference, and run XBTUSD as a sensitivity. Start the futures sample on 2017-12-20, the first Wednesday on or after launch.

### Lower-priority issues

| ID | Issue | Handling |
|---|---|---|
| A21 | `NGUSHHUB` bad print on 2025-09-29 (a Monday) | Exclude via a documented list in Stage 2 |
| A26 | Rita stale run in 2005 (2 Wednesdays) | Flag; sensitivity |
| A11 | ES3 sparse before 2008 | Do not rely on ES3 before 2008 |
| A08 | BP3 gaps | Mapping only |
| A18 | BRR weekend coverage change | No effect on Wednesdays |
| A32 | SOXX `PX_LAST` unadjusted for splits; second drop of ~3.4× on 2026-11-05 unresolved | Use `TOT_RETURN_INDEX_GROSS_DVDS` only |
| A30, A31 | CFNAI ends 2026-09; USREC provisional | Leave the final weeks unlabelled |
| A29 | `NGUSHHUB` repeated last value | End sample by 2026-11-04 |

---

## 6. Differences from the project context (`FRE6123_Project_Context.md`)

| Context claim | Audit result |
|---|---|
| §5: EIA originals are in `data/raw/eia/` and are "identical to FRED, including the gaps" | **Contradicted:** the folder does not exist, so the claim cannot be verified (A34) |
| §6: WTI spot coverage 99.0%, "19 missing WTI weeks" | **Contradicted:** 164 Wednesdays missing (8.5%); 161 to Jun-2023 (A02) |
| §6: "The only non-positive price is the real WTI print of −$37.63" | **Incomplete:** FRED (the chosen spot) prints −36.98 and `USCRWTIC` −37.63 on the same day (A01) |
| §5: "The last common Wednesday across sources is 2026-11-04" | **Qualified:** FRED's last Wednesday is 2026-10-28; 11-04 only works with a fallback to Tuesday 11-03 (A06) |
| §5: `NGUSHHUB` is the NG primary; FRED is "too gapped before 2007" | **Confirmed but incomplete:** FRED is about 70% blank before 2007, and Bloomberg has a one-day dating shift (2020-01 to 2021-04), the missing Uri peak, a bad print and a stale Rita run (A25, A22, A21, A26) |
| §5: `USCRWTIC` "only starts 2017" | **Confirmed, and more serious:** it is futures-based (86% identical to CL1) (A05) |
| §6: "no duplicates, no unsorted dates, no stray non-numeric values" | **Confirmed** |
| §6: BP needs ÷100; median ratios about 1.00 | **Confirmed** (0.9996 after ÷100) |
| §6: GC generics skip non-active months; BP generics skip serial months | **Confirmed** (88% vs 19%; 95% vs 3%) |
| §6: contract calendars "complete for 1990–2026, with no missing contracts" | **Confirmed for each cycle**, but the SP chain also contains 12 phantom contracts tied on 2021-09-17 (A10) |
| §5: SP to 2021-09-17, ES from 1997-09 | **Confirmed**; also SP1 = ES1 to the cent on 83% of 2021 days, and the two roll on different days (A09) |
| §5: gold LBMA not accessible; use XAU | **Confirmed** (empty file) |
| §6: weekly correlations, usable-pair counts, roll-rule hit rates | **Not checked:** these require weekly returns and contract mapping (Stage 2) |
| §1: "Data pulled and validated; no further Bloomberg pulls needed" | **Not supported yet:** FRED re-download recommended; LBMA alternative optional |
| §8: use the `mlfe` conda env (Python 3.11.14, pandas 3.0.1) | That env does not exist here; this audit used Python 3.12.8 and pandas 3.1.1 |
| (Two copies of the context file) | The root copy and `Projects/` copy differ in paths and environment names; the root copy is the newer one |

The revised proposal also needs updating:
- natural gas 1997 → **1999**;
- WTI spot source "Bloomberg" → FRED/EIA;
- gold "LBMA" → XAU, with a disclosure.

---

## 7. Decisions needed from you

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | WTI spot gaps | (a) re-download FRED/EIA and compare before Stage 2; (b) accept the file and use a common-date fallback | (a), if anyone can download; otherwise (b) with the count disclosed |
| D2 | NG spot, Jan-2020 to Apr-2021 | (a) use FRED in that window; (b) shift Bloomberg by −1 trading day; (c) leave as is | (a); report (c) as a sensitivity |
| D3 | Uri missing days in Bloomberg | (a) fill only missing days from FRED; (b) Bloomberg only, Uri with FRED as a side analysis | (a), documented |
| D4 | Missing Wednesdays (holidays and FRED gaps) | (a) drop the week (closest to the paper's 1,728); (b) latest earlier common day, at most 7 days back | (a) for the replication; (b) as a sensitivity |
| D5 | S&P futures | (a) SP until a quarterly roll before 2021-09, then ES; (b) ES throughout from 1997 | (a) for the replication |
| D6 | Bitcoin spot | BRR primary with XBTUSD sensitivity; start 2017-12-20 | As stated |
| D7 | WTI 2023–2026 | FRED spot primary with CL1-proxy sensitivity | As stated |

---

## 8. Limitations of this audit (what it does not show)

- It cannot prove that Bloomberg's own prices are correct. It checks internal consistency and agreement across sources, but where only one source exists (most futures generics, SPX, GBPUSD before 2017) an error that matches the market's behaviour would go undetected.
- The FRED series were not compared with a fresh download, because network access was blocked.
- Outlier screening uses daily data and a robust z-score above 10 (rolling 250-day MAD), plus each series' three largest moves. Smaller errors are not detected. Corroboration compares other series over the same interval, but different closing times (gold, Bitcoin, GBP) can make genuine moves look uncorroborated, so the "suspect" and "needs review" labels in `daily_outlier_screen.csv` are prompts for review, not verdicts.
- Roll-cycle conclusions are statistical, based on spread jumps. Exact contract mapping is a Stage 2 task.
- Whether 2025–2026 events (gold 2026-01-30, NG January 2026, SOXX 2026-11-05) are real cannot be confirmed from outside sources here. They are classified by internal corroboration only.
