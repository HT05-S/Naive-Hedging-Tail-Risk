# Is the Naïve Hedge Still Hard to Beat?

Tail-risk hedging with futures, 1990–2026, with evidence from Bitcoin and natural gas.

FRE 6123 Financial Risk Management, NYU Tandon, Fall 2026. Group project: final submission.
Team: Hina Tomar, Kavin Dhanasekaran, Sai Kishore.

We replicate Cao & Conlon (2025), "Tail Risk Hedging: The Superiority of the Naïve Hedging Strategy"
(*Journal of Futures Markets*, 45(8), 977–1005), and extend it.

- **H1:** for WTI, GBP/USD, the S&P 500 and gold, no estimated hedge-ratio model significantly and consistently
  beats the 1:1 naïve hedge in reducing tail risk, in the paper's sample (1990 to June 2023) or through 2026.
- **H2:** the same holds for Bitcoin and natural gas.

## What is in this submission

| Item | Where |
|---|---|
| **Written report** | `FRE6123_Final_Report_Tomar_Dhanasekaran_Kishore.pdf` (LaTeX source in `report/`) |
| **Presentation slides** | `PRESENTATION_SLIDES.md` (link to the deck in Google Slides) |
| **Data** | `data/raw/` (Bloomberg and FRED files as downloaded), `data/external/` (public files used to verify them), `data/processed/` (weekly returns built by the code) |
| **Code** | `src/` (data and hedging code), `scripts/` (the steps that produce every result), `audit/` (data audit and the first data step), `tests/` |
| **Results** | `results/hedge_ratios/`, `results/tables/`, `results/figures/` |
| **Worked example in Excel** | `results/WTI_12_scenarios_worked.xlsx`: how the 12 scenario numbers for WTI are calculated, step by step |

## Data sources

| Market | Spot price | Futures |
|---|---|---|
| WTI crude oil | FRED `DCOILWTICO` (EIA Cushing spot) | Bloomberg `CL1`–`CL3` |
| GBP/USD | Bloomberg `GBPUSD Curncy` | Bloomberg `BP1`–`BP3` |
| S&P 500 | Bloomberg `SPX Index` | Bloomberg `SP1`–`SP2` to September 2021, then `ES1`–`ES3` |
| Gold | Bloomberg `XAU Curncy` | Bloomberg `GC1`–`GC3` |
| Bitcoin | Bloomberg `BRR Index` (CME CF reference rate); `XBTUSD Curncy` as a check | Bloomberg `BTC1`–`BTC3` |
| Natural gas | Bloomberg `NGUSHHUB Index` to March 2007, FRED `DHHNGSP` after | Bloomberg `NG1`–`NG3` |

Also used: Bloomberg contract calendars (last trading days) for every futures family, FRED `CFNAI` for economic
regimes, and Bloomberg `SOXX US Equity` for the AI-concentration check. Bloomberg data were pulled on the NYU
terminals on November 9, 2026. `data/raw/manifest.csv` lists every series with its dates and row count, and the
report's reference list gives the full citations.

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

A conda or mamba environment with the same packages works too.

## Check that everything works

```bash
python -m pytest -q tests
```

All 52 tests should pass. They check the weekly datasets against the raw files, confirm the raw files are
unchanged, and test the six models and the evaluation measures.

## Reproduce the results

Run these in order from the top folder. Each step reads the output of the one before.

```bash
python audit/stage1b_remediation.py     # weekly dataset, same-contract setting
python scripts/build_paper_dataset.py   # weekly dataset, paper setting (spliced returns), and the Table 2 check
python scripts/run_hedges.py            # rolling 52-week hedge ratios for the six models (about 3 minutes)
python scripts/make_tables.py           # hedging effectiveness, tests and all result tables (about 3 minutes)
python scripts/make_figures.py          # the two figures in the report
python scripts/make_report.py --latex   # the report as a PDF (needs LaTeX with latexmk)
```

The paper setting (strict Wednesdays, spliced futures returns) is used to replicate the four original markets.
The same-contract setting is used for the extension to 2026, for Bitcoin and natural gas, and as a robustness
check. `audit/REPLICATION_CONVENTIONS_NOTE.md` explains both.

## Folders

| Folder | Contents |
|---|---|
| `data/raw/` | Bloomberg and FRED files as downloaded. Never edited; a test checks their checksums. |
| `data/external/` | Public re-downloads used to verify the raw data |
| `data/processed/` | Weekly spot and futures returns for the six markets, in both settings |
| `src/frm_data/` | Data code: contracts, rolls and weekly returns |
| `src/hedging/` | The six hedge-ratio models, the evaluation measures and the report tables |
| `scripts/` | The steps listed above |
| `results/` | Hedge ratios, result tables, figures and the Excel worked example |
| `audit/` | Raw-data audit, data remediation report and conventions note |
| `tests/` | Automated checks |
| `report/` | LaTeX source of the report |

## Supporting documents

- [Replication conventions note](audit/REPLICATION_CONVENTIONS_NOTE.md): how the paper built its returns, and our two settings
- [Raw data audit](audit/RAW_DATA_AUDIT.md) and [data remediation report](audit/DATA_REMEDIATION_REPORT.md)
