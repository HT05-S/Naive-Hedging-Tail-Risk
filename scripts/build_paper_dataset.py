"""Build the paper-setting weekly dataset and compare it with Cao & Conlon (2025), Table 2.

    python scripts/build_paper_dataset.py

Writes data/processed/weekly_paper_convention.csv and results/tables/table2_replication.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frm_data import config as C, io            # noqa: E402
from frm_data.paper import PAPER_FILE, build_paper_dataset, paper_calendar  # noqa: E402

# Table 2 of the paper: max, min, std, skewness, excess kurtosis, 5% VaR, 5% CVaR
PAPER_TABLE2 = {
    ("WTI", "spot"): (0.462, -0.481, 0.056, -0.410, 9.778, -0.082, -0.129),
    ("WTI", "futures"): (0.466, -0.482, 0.055, -0.524, 11.043, -0.079, -0.126),
    ("GBPUSD", "spot"): (0.055, -0.091, 0.014, -0.823, 4.854, -0.021, -0.033),
    ("GBPUSD", "futures"): (0.050, -0.103, 0.014, -0.961, 6.134, -0.021, -0.033),
    ("SP500", "spot"): (0.107, -0.165, 0.023, -0.819, 5.143, -0.037, -0.056),
    ("SP500", "futures"): (0.111, -0.175, 0.023, -0.822, 5.166, -0.037, -0.057),
    ("GOLD", "spot"): (0.137, -0.124, 0.022, -0.266, 4.101, -0.032, -0.050),
    ("GOLD", "futures"): (0.129, -0.131, 0.022, -0.290, 4.473, -0.032, -0.051),
}
STATS = ["max", "min", "std", "skew", "excess_kurtosis", "var_5pct", "cvar_5pct"]


def summary(r: pd.Series) -> tuple:
    q = r.quantile(0.05)
    return (r.max(), r.min(), r.std(), stats.skew(r), stats.kurtosis(r), q, r[r <= q].mean())


if __name__ == "__main__":
    df = build_paper_dataset()
    df.to_csv(io.PROCESSED / PAPER_FILE, index=False, float_format="%.10g")
    print(f"Wednesdays kept to June 2023: {len(paper_calendar(C.ORIGINAL_END))} (paper: 1,728 observations)")
    orig = df[df["sample_period"] == "original_1990_2023"]
    rows = []
    for (market, leg), ref in PAPER_TABLE2.items():
        g = orig[orig["market"] == market]
        ours = summary(g["spot_logret" if leg == "spot" else "fut_logret"])
        for name, a, b in zip(STATS, ours, ref):
            rows.append(dict(market=market, series=leg, statistic=name, ours=a, paper=b, n=len(g)))
    out = pd.DataFrame(rows)
    (ROOT / "results" / "tables").mkdir(parents=True, exist_ok=True)
    out.to_csv(ROOT / "results" / "tables" / "table2_replication.csv", index=False, float_format="%.4f")
    print(out.pivot_table(index=["market", "series"], columns="statistic", values="ours", sort=False)[STATS].round(3))
