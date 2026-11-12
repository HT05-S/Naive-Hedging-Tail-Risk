# Note: Replication Conventions (Roll Rule, Return Method, Weekly Calendar)

**Date:** 2026-11-12 · **Authors:** Hina Tomar, Kavin Dhanasekaran, Sai Kishore (with Claude) · **Status:** agreed in the team working session of 2026-11-12. Coded the same day: the paper setting is `src/frm_data/paper.py` (run `python scripts/build_paper_dataset.py`), which also writes the Table 2 comparison to `results/tables/table2_replication.csv`.

This note records how Cao & Conlon (2025) appear to have built their weekly returns, and proposes two switches so we can first match the paper and then test our own, more accurate, conventions. It relates to items C1, C2, D3, D5, E1 and E2 in `METHODOLOGY_DECISION_LOG.md`.

## 1. What the paper states

Section 4 (p. 983) is the only description:

- Weekly prices, "specifically every Wednesday", January 1990 to June 2023; 1,728 weekly observations.
- Futures are "those nearest to maturity, with a rollover to the subsequent contract occurring on the first day of the contract month".
- Returns are log differences of prices.

It does not say how returns are computed in a roll week, how holidays are handled, or what happens when a contract expires before its contract month.

## 2. What we infer from the paper's Table 2

We rebuilt the weekly returns several ways from our raw data and compared the summary statistics with Table 2. These are inferences, not statements from the paper.

**Calendar.** There are 1,748 Wednesdays from 1990-01-03 to 2023-06-28. On 20 of them at least one market was closed. Keeping only Wednesdays on which the three non-WTI spot series and all four front futures trade leaves exactly **1,728 dates**, the paper's count. This points to a strict-Wednesday rule with no replacement day. A dropped Wednesday then produces a 14-day return.

**Futures returns are spliced.** In a roll week the paper appears to compare the new contract's price with the old contract's price the week before.

| WTI futures construction | Max | Min | Std | Skew | Excess kurtosis |
|---|---:|---:|---:|---:|---:|
| Paper, Table 2 | 0.466 | −0.482 | 0.055 | −0.524 | 11.04 |
| Hold to expiry, spliced (= `CL1`) | 0.466 | −0.482 | 0.055 | −0.512 | 10.84 |
| Hold to expiry, same contract | 0.466 | −0.636 | 0.055 | −1.268 | 19.32 |
| Roll on 1st of expiry month, spliced | 0.531 | −0.636 | 0.054 | −1.040 | 22.45 |

**Roll rule by market.**

| Market | Effect of "first day of the contract month" | Series that matches the paper |
|---|---|---|
| WTI | Never fires: contracts stop trading about 3 business days before the 25th of the prior month. The rule reduces to holding the nearest contract to expiry. | `CL1` as pulled |
| GBP/USD | Rolls about two weeks before expiry (Mar, Jun, Sep, Dec cycle). | `BP2` from the 1st of the contract month until expiry, `BP1` otherwise. This gives min −0.102, skew −0.966, excess kurtosis 6.13 (paper: −0.103, −0.961, 6.13). `BP1` alone gives −0.120, −1.098, 7.68. |
| S&P 500 | Rolls about two weeks before expiry. | Either rule matches max, min and std. `SP` to 2021-09, then `ES`. |
| Gold | Rolls about four weeks before expiry (Feb, Apr, Jun, Aug, Oct, Dec cycle). | Either rule matches (min −0.130 to −0.132; paper −0.131). |

**Other points.**
- Table 2's "kurtosis" is excess kurtosis.
- WTI and S&P 500 spot extremes match the paper exactly. GBP and gold spot differ slightly because the paper used WM/Reuters and LBMA prices, which we do not have.

## 3. Why the paper's conventions are not the most accurate

**Spliced returns include a gap nobody can trade.** Example, WTI, week of 2020-04-15 to 2020-04-22:

| Method | Prices | Log return |
|---|---|---:|
| Spliced | CLM20 13.78 vs CLK20 19.87 | −0.366 |
| Same contract | CLM20 13.78 vs CLM20 26.04 | −0.636 |

Size of the roll gap (spliced minus same-contract), 1999–2026:

| | WTI | Natural gas | Gold | GBP |
|---|---:|---:|---:|---:|
| Mean absolute gap per roll week | 1.4% | 3.5% | 0.25% | 0.2% |
| Largest | 27% | 69% | 0.8% | 0.8% |
| Share of futures variance from gaps | −2% | +15% | +0.5% | 0% |

Natural gas gaps are systematic (about +4% to +6% in September–November rolls), so spliced returns would bias H2.

**Strict Wednesdays lose data and create 14-day returns.** In our weekly dataset, about 2% of returns use a non-Wednesday day for every market except WTI, where it is 13% (248 of 1,885), because FRED `DCOILWTICO` is missing many Wednesdays. The paper had a complete WTI spot series and did not face this.

The replacement rule (Wednesday, else Tuesday, else Monday; spot and futures from the same day) does not substitute a proxy price. It moves the observation day for both legs, so returns span 5 to 9 days instead of 7. For WTI: 1,665 returns span 7 days, 188 span 6 or 8, and 32 span 5 or 9.

A weekly-average spot series (FRED `WCOILWTICO`) is not suitable: averaging thins the tails and mismatches the Wednesday futures price.

## 4. Plan: two switches

| Switch | Paper setting (validation) | Our setting (main results) |
|---|---|---|
| Weekly calendar | Strict Wednesdays; returns allowed across a dropped week | Wednesday, else Tuesday, else Monday; no return across a missing week |
| Futures returns | Spliced | Same contract |

**Order of work.**
1. Run with both switches on the paper's settings for 1990 to June 2023 and match Table 2, then Tables 3 and 5–7.
2. Flip each switch separately and report what changes.
3. Use our settings for the main results: the extension to 2026, Bitcoin and natural gas.

**Expectations.** The calendar switch affects all six models equally and will most likely leave the rankings unchanged; report it as a robustness check. The return-method switch changes roll-week returns materially for WTI and natural gas and is the more likely of the two to move results.

## 5. Changes needed in the code

- `src/frm_data` currently builds same-contract returns only (D3) and never forms a return across a missing week (C3). The validation run needs a spliced-return option and an option to allow multi-week returns.
- The `strict_wednesday` flag already exists in `data/processed/weekly_market_returns.csv`.
- The spliced series can be built from generics 1 and 2 and the contract calendars already in `data/raw/bloomberg/`.

## 6. Caveats

- Everything in Section 2 is inferred from matching summary statistics. The authors likely used a vendor-built continuous futures series (they cite Refinitiv), but the paper does not confirm this.
- The paper's "1,728 observations" may refer to price dates (giving 1,727 returns) or to returns; our reconstruction gives 1,728 dates.
- The comparison in Section 2 was run with temporary scripts that are not in the repository. The figures should be reproduced with repository code before being quoted in the final paper.
