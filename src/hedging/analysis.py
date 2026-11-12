"""Turn hedge ratios into hedged returns and the result tables used in the report."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data
from . import evaluate as ev
from .models import MODELS, SCENARIOS

WINDOW = 52
NG_FRED_ONLY_START = pd.Timestamp("2008-04-09")   # one year after the Henry Hub source switch to FRED
STRESS_EVENTS = {                      # name: (first week, last week, markets)
    "COVID crash, Feb-Apr 2020": ("2020-02-19", "2020-04-29", ("WTI", "GBPUSD", "SP500", "GOLD", "BTC", "NATGAS")),
    "Winter Storm Uri, Feb 2021": ("2021-02-10", "2021-03-03", ("NATGAS", "WTI")),
    "FTX collapse, Nov 2022": ("2022-11-02", "2022-11-30", ("BTC",)),
    "Yen carry unwind, Aug 2024": ("2024-07-31", "2024-08-14", ("WTI", "GBPUSD", "SP500", "GOLD", "BTC", "NATGAS")),
    "Tariff sell-off, Apr 2025": ("2025-04-02", "2025-04-23", ("WTI", "GBPUSD", "SP500", "GOLD", "BTC", "NATGAS")),
}


def load_ratios(setting: str, market: str) -> pd.DataFrame:
    b = pd.read_csv(data.RESULTS / "hedge_ratios" / f"{setting}_{market}.csv", index_col=0, parse_dates=True)
    cols = [c.split("|") for c in b.columns]
    b.columns = pd.MultiIndex.from_tuples([(m, s, me, float(a)) for m, s, me, a in cols],
                                          names=["model", "side", "measure", "alpha"])
    return b


def aligned(setting: str, market: str, mode: str = "oos"):
    """Evaluation frame d (s, f, target_wed) and hedge ratios B on the same dates.

    'oos': week t uses the ratio estimated on the 52 weeks ending t-1.
    'is' : week t uses the ratio estimated on the 52 weeks ending t (same sample).
    """
    d = data.load(setting)[market]
    b = load_ratios(setting, market)
    B = (b.shift(1) if mode == "oos" else b).iloc[1:]
    d = d.loc[B.index]
    return d, B


def subsets(d: pd.DataFrame, market: str = "") -> dict[str, np.ndarray]:
    """Boolean masks over the evaluation weeks: samples, CFNAI regimes and basis-volatility halves."""
    tw = d["target_wed"]
    orig = (tw <= data.ORIGINAL_END).to_numpy()
    c = data.cfnai()
    month = tw.dt.to_period("M").dt.to_timestamp()
    cf = c.reindex(c.index.union(month.unique())).ffill().reindex(month).to_numpy()   # latest months carried forward
    full = np.ones(len(d), dtype=bool)
    out = {"full": full}
    if orig.any() and not orig.all():
        out.update({"original": orig, "post": ~orig})
    for name, m in list(out.items()):
        if name == "post":
            continue
        out[f"{name}|cfnai_below"] = m & (cf < 0)
        out[f"{name}|cfnai_above"] = m & (cf >= 0)
    if market == "NATGAS":      # FRED spot at both ends of every estimation window and every evaluated week
        out["full|fred_only"] = (tw >= NG_FRED_ONLY_START).to_numpy()
    return out


def basis_vol(setting: str, market: str) -> pd.Series:
    """Volatility of the weekly basis change (s - f) over the 52 weeks before each evaluation week."""
    d = data.load(setting)[market]
    return (d["s"] - d["f"]).rolling(WINDOW).std().shift(1)


def evaluate_market(setting: str, market: str, n_boot: int = 2000) -> pd.DataFrame:
    rows = []
    for mode in ("oos", "is"):
        d, B = aligned(setting, market, mode)
        s, f = d["s"].to_numpy(), d["f"].to_numpy()
        masks = subsets(d, market)
        bv = basis_vol(setting, market).reindex(d.index).to_numpy()
        for name in [k for k in masks if "|" not in k and k != "post"]:
            med = np.nanmedian(bv[masks[name]])
            masks[f"{name}|basis_low"] = masks[name] & (bv <= med)
            masks[f"{name}|basis_high"] = masks[name] & (bv > med)
        Y = {col: s - B[col].to_numpy() * f for col in B.columns}
        for key, m in masks.items():
            if m.sum() < 60:
                continue
            sample, _, subset = key.partition("|")
            subset = subset or "all"
            sm = s[m]
            cache = {}
            for model in MODELS:
                for side, meas, a in SCENARIOS:
                    y = Y[(model, side, meas, a)][m]
                    b = B[(model, side, meas, a)].to_numpy()[m]
                    rec = dict(setting=setting, market=market, sample=sample, subset=subset, mode=mode, model=model,
                               side=side, measure=meas, alpha=a, n=int(m.sum()),
                               he=ev.effectiveness(y, sm, side, meas, a),
                               he_sv=ev.effectiveness(y, sm, side, "SV", a),
                               he_var=ev.variance_effectiveness(y, sm),
                               b_mean=b.mean(), b_sd=b.std(ddof=1),
                               utility=ev.utility(y, b), p_wilcox=np.nan)
                    if mode == "oos" and subset in ("all", "fred_only") and model != "naive":
                        ck = (model, side, a) if model in ("ols", "sv") else (model, side, meas, a)
                        if ck not in cache:
                            cache[ck] = ev.wilcox_pvalue(y, Y[("naive", side, meas, a)][m], side, a, n_boot)
                        rec["p_wilcox"] = cache[ck]
                    rows.append(rec)
    return pd.DataFrame(rows)


def hedge_ratio_stats(setting: str, market: str, sample_end=data.ORIGINAL_END) -> pd.DataFrame:
    d, B = aligned(setting, market, "oos")
    B = B[(d["target_wed"] <= sample_end).to_numpy()] if sample_end is not None else B
    rows = []
    for side in ("down", "up"):
        for meas in ("VaR", "CVaR"):
            for model in MODELS:
                b = B[(model, side, meas, 0.05)]
                q = b.quantile([0.01, 0.05, 0.5, 0.95, 0.99])
                rows.append(dict(setting=setting, market=market, side=side, measure=meas, model=model, mean=b.mean(),
                                 sd=b.std(), p01=q[0.01], p05=q[0.05], p50=q[0.5], p95=q[0.95], p99=q[0.99],
                                 mean_abs_change=b.diff().abs().mean()))
    return pd.DataFrame(rows)


def stress_table(setting_for: dict[str, str]) -> pd.DataFrame:
    """Worst weekly loss and variance-type effectiveness inside each stress window (5% CVaR, downside ratios)."""
    rows = []
    for event, (a, z, markets) in STRESS_EVENTS.items():
        for market in markets:
            d, B = aligned(setting_for[market], market, "oos")
            m = ((d["target_wed"] >= a) & (d["target_wed"] <= z)).to_numpy()
            if m.sum() == 0:
                continue
            s, f = d["s"].to_numpy()[m], d["f"].to_numpy()[m]
            rec = dict(event=event, market=market, weeks=int(m.sum()), unhedged_worst_week=s.min(),
                       unhedged_best_week=s.max())
            for model in MODELS:
                y = s - B[(model, "down", "CVaR", 0.05)].to_numpy()[m] * f
                rec[f"{model}_worst_week"] = y.min()
                rec[f"{model}_he"] = 1 - (y ** 2).sum() / (s ** 2).sum()
            rows.append(rec)
    return pd.DataFrame(rows)
