"""Load weekly spot and futures returns for either data setting.

  "paper"  strict Wednesdays, spliced futures, the paper's roll rule (four markets)
  "ours"   Wednesday-else-Tuesday-else-Monday, same-contract futures returns (six markets)
  "ours_xbt"  as "ours", Bitcoin only, with the XBTUSD spot rate in place of the CME reference rate
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results"

ORIGINAL_END = pd.Timestamp("2023-06-28")       # last Wednesday of the paper's sample
LABELS = {"WTI": "WTI", "GBPUSD": "GBP/USD", "SP500": "S&P 500", "GOLD": "Gold",
          "BTC": "Bitcoin", "NATGAS": "Natural gas"}


def load(setting: str) -> dict[str, pd.DataFrame]:
    """Return {market: frame indexed by observation date with columns s (spot) and f (futures)}."""
    if setting == "paper":
        d = pd.read_csv(PROCESSED / "weekly_paper_convention.csv", parse_dates=["target_wed", "obs_date"])
    elif setting in ("ours", "ours_xbt"):
        d = pd.read_csv(PROCESSED / "weekly_market_returns.csv", parse_dates=["target_wed", "obs_date"],
                        low_memory=False)
        d = d[d["return_defined"]]
        if setting == "ours_xbt":
            d = d[d["market"] == "BTC"].assign(spot_logret=lambda x: x["spot_alt_logret"])
    else:
        raise ValueError(setting)
    out = {}
    for mkt, g in d.groupby("market", sort=False):
        g = g.set_index("obs_date").sort_index()
        out[mkt] = pd.DataFrame({"s": g["spot_logret"], "f": g["fut_logret"], "target_wed": g["target_wed"]}).dropna()
    return out


def cfnai() -> pd.Series:
    """Monthly Chicago Fed National Activity Index, indexed by month start."""
    c = pd.read_csv(RAW / "fred" / "CFNAI.csv", parse_dates=["date"]).set_index("date")["CFNAI"]
    return pd.to_numeric(c, errors="coerce").dropna()
