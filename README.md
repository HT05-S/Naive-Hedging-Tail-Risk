# Naive Hedging and Tail Risk

FRE 6123 Financial Risk Management group project (NYU Tandon, Fall 2026).
Team: Hina Tomar, Kavin Dhanasekaran, Sai Kishore.

We replicate Cao & Conlon (2025), "Tail Risk Hedging: The Superiority of the Naïve Hedging Strategy"
(*Journal of Futures Markets*), and extend it.

- **H1:** for WTI, GBP/USD, the S&P 500 and gold, no estimated hedge-ratio model consistently beats
  the 1:1 naïve hedge in reducing tail risk, in the paper's sample (1990 to June 2023) or through 2026.
- **H2:** the same holds for Bitcoin and natural gas.

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

All tests should pass. They check the weekly dataset against the raw files and confirm the raw files are unchanged.

## Reproduce the results

Run these in order from the repo root. Each step reads the output of the one before.

```bash
python audit/stage1b_remediation.py     # weekly dataset, our setting (same-contract returns)
python scripts/build_paper_dataset.py   # weekly dataset, paper setting (spliced returns), and Table 2 check
python scripts/run_hedges.py            # rolling 52-week hedge ratios for the six models (about 3 minutes)
python scripts/make_tables.py           # hedging effectiveness, tests and all result tables (about 3 minutes)
python scripts/make_figures.py          # figures for the report
python scripts/make_report.py           # the written report (Word), at the top level
python scripts/make_report.py --latex   # the same report as a PDF typeset with LaTeX
```

The two data settings are explained in `audit/REPLICATION_CONVENTIONS_NOTE.md`. The paper setting is used to
replicate and extend the four original markets (H1). Our setting is used for Bitcoin and natural gas (H2) and
as a robustness run for H1.

## Repo layout

| Folder | Contents | Rule |
|---|---|---|
| `data/raw/` | Bloomberg and FRED files as downloaded | Never edit |
| `data/external/` | Public re-downloads used to verify the raw data | Never edit |
| `data/processed/` | Weekly spot and futures returns for the six markets | Built by code only |
| `src/frm_data/` | Data code: contracts, rolls, weekly returns in both settings | |
| `src/hedging/` | The six hedge-ratio models, evaluation measures and result tables | |
| `scripts/` | The steps that reproduce every result | |
| `results/` | Hedge ratios, tables and figures | Built by code only |
| `audit/` | Data audit reports, decision log and conventions note | |
| `tests/` | Automated checks | |
| `docs/` | The paper, course guidelines, proposals and project context | |

The written report is at the top level of the repository: `FRE6123_Final_Report_Tomar_Dhanasekaran_Kishore.pdf`
(and the same report as `.docx`). Its LaTeX source is in `report/`.

## How we work

1. Pull `main`, then create a branch for your task (`git switch -c your-task`).
2. Commit small changes and run the tests before you push.
3. Open a pull request. A teammate reviews it before it is merged. Nobody pushes to `main` directly.
4. Record every methodology choice in `audit/METHODOLOGY_DECISION_LOG.md`.

## Who owns what

| Member | Area |
|---|---|
| Hina Tomar | Data and rolled futures series; naïve, OLS and historical-simulation hedges; extension to 2026 |
| Kavin Dhanasekaran | Cornish–Fisher, Clayton copula and semivariance hedges; hedge-ratio stability; in-sample versus out-of-sample |
| Sai Kishore | Evaluation (effectiveness, Wilcox test, utility); basis-risk and CFNAI regimes; Bitcoin and natural gas |

## Key documents

- [The paper](docs/paper/Cao_Conlon_2025_Tail_Risk_Hedging_JFM.pdf)
- [Revised proposal](docs/proposal/FRE6123_Revised_Proposal_Tomar_Dhanasekaran_Kishore.docx)
- [Course guidelines and rubric](docs/course/Group_Project_Description_and_Rubric.docx)
- [Project context](docs/FRE6123_Project_Context.md): background for teammates and their AI assistants
- [Methodology decision log](audit/METHODOLOGY_DECISION_LOG.md)
- [Replication conventions note](audit/REPLICATION_CONVENTIONS_NOTE.md): how the paper built its returns, and our two switches
- [Raw data audit](audit/RAW_DATA_AUDIT.md) and [data remediation report](audit/DATA_REMEDIATION_REPORT.md)
