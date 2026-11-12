"""Estimate rolling 52-week hedge ratios for every market in both data settings.

    python scripts/run_hedges.py

Writes results/hedge_ratios/<setting>_<market>.csv. Takes a few minutes (the copula model
simulates 10,000 draws per window). Results are reproducible: the random seed is fixed.
Markets already done are skipped unless --force is given.
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hedging import data, models  # noqa: E402

OUT = data.RESULTS / "hedge_ratios"


def run(job):
    setting, market = job
    if (OUT / f"{setting}_{market}.csv").exists() and "--force" not in sys.argv:
        return f"{setting:8s} {market:7s} already done (use --force to redo)"
    d = data.load(setting)[market]
    t = time.time()
    b = models.estimate(d["s"].to_numpy(), d["f"].to_numpy())
    b.index = d.index[b.index]                       # date of the last observation in each window
    b.index.name = "window_end"
    b.columns = ["|".join(map(str, c)) for c in b.columns]
    b.to_csv(OUT / f"{setting}_{market}.csv", float_format="%.4f")
    return f"{setting:5s} {market:7s} {len(b):5d} windows in {time.time() - t:5.0f} s"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(st, m) for st in ("paper", "ours", "ours_xbt") for m in data.load(st)]
    with Pool(min(len(jobs), 8)) as pool:
        for msg in pool.imap_unordered(run, jobs):
            print(msg, flush=True)
