"""Tables for the written report, built from results/tables/*.csv."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data
from .models import MODEL_LABELS, MODELS

COLS = [(s, m, a) for s in ("down", "up") for m in ("VaR", "CVaR") for a in (0.10, 0.05, 0.01)]
COL_LABELS = ["VaR 10%", "VaR 5%", "VaR 1%", "CVaR 10%", "CVaR 5%", "CVaR 1%",
              "VaR 90%", "VaR 95%", "VaR 99%", "CVaR 90%", "CVaR 95%", "CVaR 99%"]
H1 = ["WTI", "GBPUSD", "SP500", "GOLD"]
H2 = ["BTC", "NATGAS"]

# Cao & Conlon (2025), Table 5, 52-week window: naive and OLS tail-risk effectiveness in COLS order
PAPER_NAIVE = {
    "WTI": [0.872, 0.831, 0.667, 0.767, 0.719, 0.658, 0.865, 0.807, 0.653, 0.758, 0.706, 0.614],
    "GBPUSD": [0.713, 0.694, 0.726, 0.708, 0.706, 0.724, 0.695, 0.663, 0.566, 0.685, 0.664, 0.670],
    "SP500": [0.893, 0.880, 0.858, 0.879, 0.871, 0.878, 0.881, 0.880, 0.888, 0.896, 0.891, 0.897],
    "GOLD": [0.696, 0.696, 0.673, 0.693, 0.691, 0.704, 0.737, 0.726, 0.680, 0.730, 0.718, 0.700],
}
PAPER_OLS = {
    "WTI": [0.861, 0.822, 0.661, 0.757, 0.712, 0.657, 0.857, 0.798, 0.648, 0.744, 0.695, 0.624],
    "GBPUSD": [0.704, 0.682, 0.717, 0.699, 0.698, 0.727, 0.697, 0.677, 0.581, 0.651, 0.624, 0.583],
    "SP500": [0.894, 0.889, 0.864, 0.881, 0.875, 0.880, 0.881, 0.884, 0.886, 0.883, 0.881, 0.887],
    "GOLD": [0.702, 0.697, 0.711, 0.704, 0.706, 0.730, 0.728, 0.706, 0.669, 0.700, 0.688, 0.680],
}
PAPER_NAIVE_WINS = {"WTI": 9, "GBPUSD": 7, "SP500": 4, "GOLD": 6}          # of 12, out-of-sample
PAPER_NAIVE_WINS_IS = {"WTI": 1, "GBPUSD": 3, "SP500": 3, "GOLD": 3}       # of 12, in-sample
PAPER_OLS_VAR_HE = {"WTI": 0.930, "GBPUSD": 0.900, "SP500": 0.986, "GOLD": 0.916}


class Results:
    def __init__(self):
        t = data.RESULTS / "tables"
        self.he = pd.read_csv(t / "effectiveness_long.csv")
        self.ratios = pd.read_csv(t / "hedge_ratio_stats.csv")
        self.stress = pd.read_csv(t / "stress_events.csv")
        self.ai = pd.read_csv(t / "ai_stress_weeks.csv")
        self.table2 = pd.read_csv(t / "table2_replication.csv")

    def cell(self, setting, market, sample, mode="oos", subset="all"):
        h = self.he
        return h[(h.setting == setting) & (h.market == market) & (h["sample"] == sample) & (h["mode"] == mode)
                 & (h.subset == subset)]

    def grid(self, setting, market, sample, mode="oos", subset="all", val="he") -> pd.DataFrame:
        """Models (rows) by the 12 scenarios (columns)."""
        x = self.cell(setting, market, sample, mode, subset)
        t = x.pivot_table(index="model", columns=["side", "measure", "alpha"], values=val, dropna=False)
        return t.reindex(list(MODELS))[COLS]

    def n(self, *a, **k) -> int:
        return int(self.cell(*a, **k)["n"].iloc[0])

    def wins(self, *a, **k) -> pd.Series:
        """Number of scenarios (of 12) in which each model has the highest effectiveness."""
        return self.grid(*a, **k).idxmax().value_counts().reindex(list(MODELS)).fillna(0).astype(int)

    def scorecard_row(self, setting, market, sample, subset="all") -> dict:
        w = self.wins(setting, market, sample, subset=subset)
        p = self.grid(setting, market, sample, subset=subset, val="p_wilcox").drop("naive").to_numpy()
        q = self.grid(setting, market, sample, subset=subset, val="p_paired").drop("naive").to_numpy()
        return dict(market=market, n=self.n(setting, market, sample, subset=subset), **w.to_dict(),
                    ind05=int((p < 0.05).sum()), ind10=int((p < 0.10).sum()), ind_half=float((p > 0.5).mean()),
                    ind_half_n=int((p > 0.5).sum()),
                    pair05=int((q < 0.05).sum()), pair95=int((q > 0.95).sum()), min_p=float(p.min()))


def fmt(v, d=3):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{d}f}"


def label(model):
    return MODEL_LABELS[model]
