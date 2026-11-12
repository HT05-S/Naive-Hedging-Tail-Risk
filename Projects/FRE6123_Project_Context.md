# FRE 6123 Group Project: Context and Status

*Last updated: 2026-11-10. Written for the team (Hina Tomar, Kavin Dhanasekaran, Sai Kishore) and for any AI assistant helping them. It summarizes every decision taken so far, so work can continue without re-deriving anything.*

---

## 1. Project at a glance

| Item | Status |
|---|---|
| Course | FRE 6123 Financial Risk Management (Prof. Adams), NYU Tandon, Fall 2026 |
| Team | Hina Tomar, Kavin Dhanasekaran, Sai Kishore |
| Topic area | Managing Tail Risks (sample topic list) |
| Primary paper | Cao, M., & Conlon, T. (2025). *Tail risk hedging: The superiority of the naïve hedging strategy.* Journal of Futures Markets, 45(8), 977–1005 (open access) |
| Title | **Is the Naïve Hedge Still Hard to Beat? Tail-Risk Hedging with Futures, 1990–2026, with Evidence from Bitcoin and Natural Gas** |
| Initial proposal | Submitted 2026-10-09 (4 hypotheses) |
| Professor feedback | Topic relevant and interesting, method clear; **narrow from four hypotheses** (replication alone involves six models) |
| Revised proposal | Final version prepared 2026-10-30: 2 hypotheses, exactly 4 pages, aligned with the rubric |
| Data | **Pulled and validated** (2026-11-09/10). No further Bloomberg pulls needed |
| Next phase | Build the weekly dataset and implement the six hedging models |

**Deadlines.** The course document lists: initial proposal Oct 9, revised proposal Oct 23, final written project Nov 6, presentations from Nov 20. The team understands the final deliverables are around Nov 20; **confirm the exact dates with the professor.**

**Grading.** Worth 30% of the course grade. The rubric scores six criteria: topic/thesis, evidence and sources (verifiable, with counterargument), analysis and persuasion, organization (with a conclusion), written presentation (complete citations), and oral presentation. Students are graded individually and are expected to contribute equally.

---

## 2. How the topic was chosen

- The **tail-risk topic** was chosen to suit the team's Python strength and buy-side and derivatives interests, with Bloomberg and WRDS available.
- The team's guidance was to **replicate a reputable paper and extend it slightly**, so that nobody questions the hypothesis.
- Nine candidate papers were reviewed (four on tail risk, five on credit risk). **Cao & Conlon (2025)** was chosen because:
  - its method is fully specified;
  - its data is reproducible with Bloomberg;
  - its extensions are clear;
  - it covers core FRM material (VaR, ES, hedge ratios, basis risk, out-of-sample testing).
- The backup paper is Fan, Londono & Xiao (2022, *JFE*), *Equity tail risk and currency risk premiums*.
- **Rejected:**
  - Ghaderi, Kilic & Seo (2022): a theoretical model.
  - Li (2023): needs CME Treasury options data.
  - Bao, Hou & Zhang (2023): too heavy for four weeks.
  - Han, Leggio & Shin (2023): a thin design.
  - Benzschawel et al. (2023): proprietary data.
  - Kaufmann et al. (2022): needs ICE index data.
  - Huang, Nozawa & Shi (2025): bond data across eight countries.

All PDFs are in `Projects/`.

---

## 3. The paper to replicate: Cao & Conlon (2025)

**Claim.** A naïve 1:1 futures hedge cannot be significantly or consistently outperformed by five sophisticated tail-risk-minimizing hedge-ratio models. The reason is **estimation error**: the advantage disappears in-sample.

**Data (paper).**
- Weekly prices **every Wednesday**, January 1990 to June 2023, giving **1,728 weekly observations**.
- Log returns.
- Four markets: WTI crude (NYMEX), GBP/USD (spot from WM/Reuters via Eikon; CME futures), S&P 500 (CME futures), and gold (LBM spot; COMEX futures). The rest is from Bloomberg.
- The nearest-to-maturity futures contract, **rolled on the first day of the contract month**.
- Recession and regime data: NBER recession indicator and the **CFNAI** (Chicago Fed National Activity Index) from FRED.

**Hedged returns.** Here *s* is the spot return, *f* the futures return, and *b* the hedge ratio set at *t−1*.
- Short hedger (long the spot position): *y = s − b·f*
- Long hedger: *y = −s + b·f*

**The six hedge-ratio models.** Each is re-estimated every week on a **rolling 52-week window**; the methods section mentions 260 weeks, but every results table uses 52.

| Model | How *b* is chosen |
|---|---|
| Naïve | *b* = 1, never estimated |
| OLS | Minimum-variance regression slope (equivalent to minimizing normal VaR/CVaR) |
| Historical simulation (HS) | Minimize empirical VaR or CVaR of the hedged return |
| Cornish–Fisher expansion (CFE) | Minimize VaR or CVaR adjusted for skewness and kurtosis (paper eqs. 7–8) |
| Clayton copula | Empirical marginals with a Clayton copula; 10,000 Monte Carlo draws, then minimize HS VaR or CVaR |
| Semivariance (SV) | Grid search for the *b* minimizing downside (or upside) semivariance around the median |

Risk levels: **1%, 5% and 10%** (downside) and **90%, 95% and 99%** (upside), for long and short hedgers.

**Evaluation.**
- **Hedging effectiveness:** HE = 1 − Risk(hedged)/Risk(unhedged), with risk measured as variance, VaR, CVaR (historical simulation) and semivariance.
- **Significance:** the Wilcox et al. (2014) test (Harrell–Davis quantile estimator plus percentile bootstrap, one-sided).
- **Robustness checks:**
  - a split by CFNAI sign (below- vs above-trend growth);
  - **in-sample vs out-of-sample**;
  - opportunity cost via mean–variance utility with risk aversion 6 and transaction costs of 0.03% × turnover (turnover = the sum of absolute changes in *b*);
  - variance reduction excluding the 5% tails;
  - a basis-risk split below and above the median.

**Key results (to replicate).**
- **95% CVaR reduction:** the naïve hedge cuts 95% CVaR by 66% (GBP/USD) to 89% (S&P 500).
- **Best model, out of 12 cases per market:**

  | Market | Naïve best in | Note |
  |---|---|---|
  | WTI | 9 / 12 | |
  | GBP/USD | 7 / 12 | |
  | S&P 500 | 4 / 12 | OLS best in 6 |
  | Gold | 6 / 12 | |

- **Statistical significance:** no model beats the naïve hedge significantly.
- **Economic regime:** in below-trend growth the naïve hedge is best in 5/6 (WTI), 4/6 (GBP) and 5/6 (S&P) downside cases, against 4, 3 and 0 in above-trend periods. Gold is the exception, where OLS is best.
- **In-sample:** the naïve hedge is best in only 1/12 cases (WTI) and 3/12 (the others). This is the estimation-error evidence.
- **Basis risk:** naïve is best when basis risk is low; **OLS leads when basis risk is high** (Table 13). This motivates H2.

---

## 4. Proposal history

**Initial proposal (Oct 9), four hypotheses:**
1. H1, replication;
2. H2, persistence to 2026;
3. H3, an AI cross-hedge (SOXX hedged with NQ/ES futures) plus Bitcoin and natural gas;
4. H4, a 52 vs 260-week window test, with an optional ML hedge.

**Professor's feedback:** *"four hypotheses are too many and it would be preferable if you could narrow your focus, which will allow for deeper analysis and interpretation of your results. This is particularly true, as replication of Cao and Conlon (2025) itself involves six models."*

**Revised proposal (current design):**
- **H1 (Replication and persistence):** for WTI crude oil, GBP/USD, the S&P 500 and gold, no estimated model significantly and consistently outperforms the naïve hedge in reducing VaR, CVaR or semivariance, either over the original sample (January 1990 to June 2023) or over its extension to 2026.
- **H2 (Generalization to new markets):** the same result holds for Bitcoin and natural gas, despite their heavy tails and unstable spot–futures relations.
- **Thesis:** the naïve hedge's advantage reflects estimation error, so it should persist out of sample but is most at risk where the spot–futures relation is unstable (high basis risk). Bitcoin and natural gas are therefore where H2 is most likely to fail.
- **Interpretation (the "depth" the professor asked for):**
  1. hedge-ratio stability;
  2. in-sample vs out-of-sample (the cost of estimation error);
  3. above vs below-median basis volatility;
  4. CFNAI regimes;
  5. stress windows: March 2020 and the November 2022 FTX collapse (Bitcoin); Winter Storm Uri, February 2021 (natural gas); August 2024 and April 2025 (all markets).
- **Optional, time permitting:** an AI-concentration lens. SOXX is used **only as a marker** to flag AI-stress weeks in 2023–2026 (including DeepSeek day, Jan 27, 2025), and the **S&P 500 index vs its own futures** hedge is compared in those weeks against other weeks. This is a sub-analysis of H1, not a hypothesis. Cross-hedging AI-heavy portfolios is future work.
- **Dropped:** the AI cross-hedge, the 52 vs 260-week window test, the ML hedge and the fixed-beta benchmark. **All six models are kept.**
- **Division of work (Table 3 of the revised proposal):**

| Member | Analytical responsibilities | Written and oral components |
|---|---|---|
| Hina Tomar | Bloomberg/FRED data for the six markets; rolled futures series; naïve, OLS and HS hedges; extension to 2026 (H1) | Data and core replication; presents motivation, data and replication results |
| Kavin Dhanasekaran | Cornish–Fisher, Clayton copula and semivariance hedges; hedge-ratio stability; in-sample vs out-of-sample analysis | Advanced models and estimation error; presents the model comparison |
| Sai Kishore | Evaluation framework (effectiveness, Wilcox test, utility); basis-risk and CFNAI analysis; Bitcoin and natural gas (H2) with stress windows | Evaluation and new-market results; presents H2 results and conclusions |

**Correction needed in the final paper:** the revised proposal states natural gas 1997–2026, but **the data supports 1999–2026** (see §6).

---

## 5. Data: what we have and where

All data is under `data/raw/`, relative to the FRM folder: `/Users/kishore/Documents/NYU_FRE/FRM/data/raw/`.

```
data/raw/bloomberg/<TICKER_WITH_UNDERSCORES>.csv   date,PX_LAST   (daily, trading days, unadjusted, no fill)
data/raw/bloomberg/<ROOT>_contracts.csv            ticker,LAST_TRADEABLE_DT,FUT_NOTICE_FIRST (all contracts incl. expired)
data/raw/fred/<SERIES_ID>.csv                      date,<SERIES_ID>   (FRED "." converted to blank)
data/raw/eia/RWTCd.xls, RNGWHHDd.xls (+ RWTC.csv, RNGWHHD.csv)   EIA originals; identical to FRED (provenance only)
data/raw/manifest.csv                              ticker,field,first_date,last_date,rows,pulled_on,notes
```

The data was pulled on 2026-11-09 at the NYU Bloomberg terminal with `blpapi` (pull report: `~/Downloads/bloomberg_pull_report.md` on Sai's machine). The data spec is a Claude Doc, *FRE 6123 Data Requirements: Naïve Hedge Project* (private link; ask Sai).

**Final source per market:**

| Market | Spot (primary) | Futures generics | Generic roll cycle | Usable sample |
|---|---|---|---|---|
| WTI crude oil | FRED `DCOILWTICO` (EIA Cushing). Bloomberg `USCRWTIC Index` only starts 2017 | `CL1/2/3 Comdty` | Every month | 1990 – Nov 2026 |
| GBP/USD | `GBPUSD Curncy` | `BP1/2/3 Curncy`, **quoted in US cents: divide by 100** | Mar, Jun, Sep, Dec | 1990 – Nov 2026 |
| S&P 500 | `SPX Index` (price index) | `SP1/2 Index` to 2021-09-17 (delisted); `ES1/2/3 Index` from 1997-09 | Mar, Jun, Sep, Dec | 1990 – Nov 2026 (SP then ES) |
| Gold | `XAU Curncy`. LBMA `GOLDLNPM Index` is **not accessible** at NYU; state the substitution in the paper | `GC1/2/3 Comdty` | **Feb, Apr, Jun, Aug, Oct, Dec only** | 1990 – Nov 2026 |
| Bitcoin | `BRR Index` (CME CF Bitcoin Reference Rate); backup `XBTUSD Curncy` | `BTC1/2/3 Curncy` | Every month | Dec 2017 – Nov 2026 |
| Natural gas | **Bloomberg `NGUSHHUB Index`** (from 1999-01-04). FRED/EIA `DHHNGSP` is too gapped before 2007 | `NG1/2/3 Comdty` (from 1990-04) | Every month | **1999 – Nov 2026** |
| Regime | FRED `CFNAI` (monthly, to Sep 2026), `USREC` (monthly, to Oct 2026) | — | — | — |
| Optional AI lens | `SOXX US Equity` (`PX_LAST`, `TOT_RETURN_INDEX_GROSS_DVDS`) | — | — | Jul 2001 – Nov 2026 |

The last common Wednesday across sources is **2026-11-04**: FRED ends Nov 3 and Bloomberg Nov 9.

---

## 6. Validation findings (done 2026-11-09/10)

**Completeness** (weekly Wednesdays; a *usable pair* is a week with both a spot return and a roll-corrected futures return):

| Market | Weeks | Spot | Futures | Usable pairs | Complete | After 52-week warm-up | Pairs to Jun-2023 (paper: 1,728) |
|---|---:|---:|---:|---:|---:|---:|---:|
| WTI | 1,923 | 99.0% | 100% | 1,885 | 98.1% | 1,833 | 1,710 |
| GBP/USD | 1,923 | 100% | 100% | 1,922 | 100% | 1,870 | 1,747 |
| S&P 500 (SP → ES) | 1,923 | 100% | 100% | about 1,921 | 100% | about 1,869 | 1,654 (SP only) |
| Gold | 1,923 | 99.9% | 100% | 1,920 | 99.9% | 1,868 | 1,745 |
| Bitcoin | 464 | 100% | 100% | 463 | 100% | 411 | — |
| Natural gas | 1,453 | 99.9% | 100% | 1,450 | 99.9% | 1,398 | — |

**Other checks:**
- **Integrity:** no duplicates, no unsorted dates, no stray non-numeric values. The only non-positive price is the real **WTI print of −$37.63 on 2020-04-20**. CL1 was the expiring May contract until 04-21; Bloomberg switched on 04-22. Never take the log of a non-positive price. Wednesday roll-corrected returns never touch this print.
- **Units:** futures/spot paired median ratios are about 1.00 everywhere once BP is divided by 100.
- **Weekly spot vs roll-corrected front-futures correlation:** WTI 0.945, gold 0.967, GBP 0.990, S&P 0.996, Bitcoin 0.942, **natural gas 0.675**. The natural gas basis is genuinely weak, which is the H2 story. Gold's daily correlation of 0.887 was a close-time artifact; at weekly frequency it is 0.97.
- **Contract calendars:** complete for 1990–2026, with no missing contracts in any root's cycle.
- **EIA vs FRED:** EIA's originals (WTI `RWTC`, Henry Hub `RNGWHHD`) are **identical** to FRED, including the gaps. No public source fills them.

**How Bloomberg generics map to contracts (tested empirically).**
- A generic switches to the next contract on the **first trading day after the front contract's `LAST_TRADEABLE_DT`**.
- Share of roll events consistent with this rule at offset 0: CL 95%, NG 97%, ES 99%, BTC 98%. For GC it is 94–100% on active months, and for BP 86–97% on quarterly months.
- **Gold generics skip non-active months** (they cycle Feb, Apr, Jun, Aug, Oct, Dec), and **BP generics skip serial months** (they cycle Mar, Jun, Sep, Dec). Filter the calendars to these cycles before mapping.
- **Mapping rule:** on date *t*, generic *k* is the *k*-th unexpired contract in the root's cycle, where unexpired means `LAST_TRADEABLE_DT` ≥ *t*. Generics 1–3 plus the calendars therefore identify the exact contract on every date, and **no individual-contract pull is needed**.

**Roll-corrected futures returns:**
- If no roll happened between *t−1* and *t*: *r = ln G1(t) − ln G1(t−1)*.
- If a roll happened: *r = ln G1(t) − ln G2(t−1)* (the same contract, which was generic 2 yesterday).
- For a custom roll date that comes *earlier* than Bloomberg's, hold generic 2 between the custom roll date and expiry.

---

## 7. Open decisions for the team

1. **Weekly sampling rule (recommended):** use Wednesday or, if either leg is missing, **the latest earlier day on which both spot and futures have prices** (at most 7 days back). This recovers all 19 missing WTI weeks without creating fake basis, because spot and futures are always priced on the same day.
2. **Roll rule:**
   - The paper's rule ("first day of the contract month") works directly for GC, BP, ES/SP and BTC, whose contracts expire inside their contract month: hold generic 2 from the 1st of the contract month until expiry.
   - CL and NG expire in the *prior* month, so pick an equivalent, e.g. roll 5 business days before `LAST_TRADEABLE_DT`.
3. **S&P 500:** use SP until its 2021-09 delisting and ES after (recommended for the replication), or ES throughout from 1997.
4. **Gold spot:** `XAU Curncy` instead of LBMA PM; disclose it as a deviation from the paper.
5. **Natural gas sample:** 1999–2026 (update the proposal's 1997).
6. **Bitcoin warm-up:** the first 52-week estimate is available from about December 2018.
7. **CFNAI lag:** the CFNAI runs to Sep 2026, so the last ~5 weeks (Oct–Nov 2026) have no regime label yet.
8. **Close-time mismatches:** GBP spot (NY close) vs CME settlement, and BRR (4 pm London) vs CME. Accept these and mention them.

---

## 8. Environment

- **Use the `iaqf` mamba environment** on Sai's machine: `~/mamba/envs/iaqf/bin/python`. It has Python 3.11.14, pandas 3.0.1, numpy 2.4.2, scipy 1.17.1, statsmodels 0.14.6 and matplotlib 3.10.8.
- Teammates should create an equivalent environment with these packages. Note that pandas 3.x changes some defaults (copy-on-write, string dtype).
- `xlrd` is needed only to read the EIA `.xls` files. It is not installed in `iaqf`; the EIA data is already saved as CSV.
- On Sai's machine, the Anaconda base `pandas` is broken (missing `__init__.py`). Do not use `~/opt/anaconda3/bin/python3`.
- The validation scripts written so far lived in a temporary folder and are **not** in the repository. The logic is described in §6; recreate it as `src/` code during implementation.

---

## 9. File map (FRM folder)

| Path | What it is |
|---|---|
| `Projects/FRE 6123 Group Project Description and Evaluation Criteria Fall 20261.docx` | Course guidelines and rubric |
| `Projects/FRE 6123_Sample_Group_Project_Topics_Fall_20261.docx` | Professor's topic list |
| `Projects/Journal of Futures Markets - 2025 - Cao - Tail Risk Hedging ….pdf` | **Primary paper** |
| `Projects/*.pdf` (8 others) | Other candidate papers reviewed |
| `Projects/FRE6123_Initial_Proposal_Tomar_Dhanesankar_Kishore.docx` | Initial proposal as submitted Oct 9 (Kavin's surname misspelled in it) |
| `Projects/FRE6123_Revised_Proposal_Tomar_Dhanasekaran_Kishore.docx` | **Current revised proposal** (also copied to `~/Downloads`) |
| `Projects/Team_Pitch_Naive_Hedge.docx` | Internal team pitch; outdated (pre-feedback design with the AI cross-hedge) |
| `Projects/FRE6123_Initial_Proposal_Tail_Risk_Hedging.docx` | Early draft of the initial proposal; superseded |
| `data/raw/…` | Raw data (see §5) |

---

## 10. Next steps

1. **Build the weekly dataset:**
   - load the raw files;
   - divide BP by 100;
   - map generics to contracts with the calendars;
   - apply the chosen roll rule and the common-date Wednesday rule;
   - compute weekly log spot and roll-corrected futures returns for the six markets;
   - attach the CFNAI regime and stress-window flags.
2. **Implement the six models** on rolling 52-week windows (long and short hedgers; 1/5/10/90/95/99% levels).
3. **Evaluation engine:** HE for variance, VaR, CVaR and semivariance; the Wilcox–Harrell–Davis bootstrap test; utility with transaction costs.
4. **Replicate Tables 3, 5, 6 and 7** of the paper for 1990 to June 2023 and document any differences.
5. **Extensions:** 2023–2026 (H1), then Bitcoin and natural gas (H2), then the interpretation analyses.
6. Optional AI lens (SOXX-flagged weeks for the S&P 500).
7. Write the final paper and prepare the presentation.

---

## 11. Key references

- Cao, M., & Conlon, T. (2025). Tail risk hedging: The superiority of the naïve hedging strategy. *Journal of Futures Markets*, 45(8), 977–1005.
- Wang, Y., Wu, C., & Yang, L. (2015). Hedging with futures: Does anything beat the naïve hedging strategy? *Management Science*, 61(12), 2870–2889.
- DeMiguel, V., Garlappi, L., & Uppal, R. (2009). Optimal versus naive diversification. *Review of Financial Studies*, 22(5), 1915–1953.
- Harris, R. D. F., & Shen, J. (2006). Hedging and value at risk. *Journal of Futures Markets*, 26(4), 369–390.
- Cao, Z., Harris, R. D. F., & Shen, J. (2010). Hedging and value at risk: A semi-parametric approach. *Journal of Futures Markets*, 30(8), 780–794.
- Cotter, J., & Hanly, J. (2006). Reevaluating hedging performance. *Journal of Futures Markets*, 26(7), 677–702.
- Wilcox, R. R., Erceg-Hurn, D. M., Clark, F., & Carlson, M. (2014). Comparing two independent groups via the lower and upper quantiles. *Journal of Statistical Computation and Simulation*, 84(7), 1543–1551.
- Harrell, F. E., & Davis, C. E. (1982). A new distribution-free quantile estimator. *Biometrika*, 69(3), 635–640.
- Ederington, L. H. (1979). The hedging performance of the new futures markets. *Journal of Finance*, 34(1), 157–170.
