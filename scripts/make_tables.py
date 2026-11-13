"""Evaluate every hedge and write the result tables.

    python scripts/make_tables.py

Needs results/hedge_ratios/ (from scripts/run_hedges.py). Writes results/tables/*.csv.
"""
from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hedging import analysis, data  # noqa: E402

OUT = data.RESULTS / "tables"
MAIN_SETTING = {"WTI": "paper", "GBPUSD": "paper", "SP500": "paper", "GOLD": "paper", "BTC": "ours", "NATGAS": "ours"}


def job(args):
    return analysis.evaluate_market(*args)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(st, m) for st in ("paper", "ours", "ours_xbt") for m in data.load(st)]
    with Pool(min(len(jobs), 8)) as pool:
        he = pd.concat(pool.map(job, jobs), ignore_index=True)
    he.to_csv(OUT / "effectiveness_long.csv", index=False, float_format="%.6g")
    pd.concat([analysis.hedge_ratio_stats(st, m, None if m in ("BTC", "NATGAS") else data.ORIGINAL_END)
               for st, m in jobs], ignore_index=True).to_csv(OUT / "hedge_ratio_stats.csv", index=False, float_format="%.4f")
    analysis.stress_table(MAIN_SETTING).to_csv(OUT / "stress_events.csv", index=False, float_format="%.4f")
    analysis.ai_stress_table("ours").to_csv(OUT / "ai_stress_weeks.csv", index=False, float_format="%.4f")
    analysis.bias_noise_table([(MAIN_SETTING[m], m, None if m in ("BTC", "NATGAS") else data.ORIGINAL_END)
                               for m in MAIN_SETTING]).to_csv(OUT / "bias_noise.csv", index=False, float_format="%.6f")
    analysis.natgas_without_uri().to_csv(OUT / "natgas_without_uri.csv", index=False, float_format="%.6f")
    print("rows:", len(he), "->", OUT)
