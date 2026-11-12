"""Weekly returns built the way Cao & Conlon (2025) appear to have built them.

This is the 'paper setting' described in audit/REPLICATION_CONVENTIONS_NOTE.md:

  Calendar   Strict Wednesdays. A Wednesday is kept only if every futures market
             and the GBP/USD, S&P 500 and gold spot markets traded. A dropped
             Wednesday is not replaced, so the return across it spans 14 days.
  Roll rule  Hold the nearest contract; roll on the first day of the contract
             month, or after the last trading day if that comes first. WTI
             contracts stop trading before their contract month, so for WTI the
             rule reduces to holding the nearest contract to expiry (CL1).
  Returns    Spliced. A return is the log change in the price of whatever
             contract is held on each date, so a roll week compares the new
             contract with the old one.

One departure, forced by our data: FRED's WTI spot series has no price on some
Wednesdays. On those weeks WTI spot AND futures are both read on the nearest
earlier day (Tuesday, then Monday), so the two legs always share a date.

The main-results setting (same-contract returns; Wednesday, else Tuesday, else
Monday) is built by frm_data.weekly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .contracts import candidate_list, contract_price
from .weekly import load_spot

PAPER_MARKETS = ("WTI", "GBPUSD", "SP500", "GOLD")
PAPER_FILE = "weekly_paper_convention.csv"


def _front(root: str) -> pd.Series:
    from .contracts import generics
    return generics(root)["G1"].dropna()


def paper_calendar(last: pd.Timestamp = C.LAST_TARGET) -> pd.DatetimeIndex:
    """Wednesdays on which CL1, BP1, SP1/ES1, GC1 and the GBP, S&P 500 and gold spot series all have a price."""
    wed = pd.date_range(C.FIRST_TARGET, last, freq="W-WED")
    ok = np.ones(len(wed), dtype=bool)
    for name in ("GBPUSD", "SP500", "GOLD"):
        s, _ = load_spot(C.MARKETS[name].spot[0])
        ok &= wed.isin(s.dropna().index)
    for root in ("CL", "BP", "GC"):
        ok &= wed.isin(_front(root).index)
    ok &= wed.isin(_front("SP").index.union(_front("ES").index))
    return wed[ok]


def held_on(m: C.Market, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Contract held ON each date: the first one that has neither expired nor reached its contract month."""
    cand = candidate_list(m)
    trig = cand["LTD"] + pd.Timedelta(days=1)                 # still held on its last trading day
    if m.roll_primary == "cm_start":
        trig = np.minimum(trig, cand["contract_month"])
    trig = pd.DatetimeIndex(trig).values
    if not np.all(np.diff(trig) > np.timedelta64(0, "ns")):
        raise ValueError(f"{m.market}: roll dates not increasing")
    idx = np.searchsorted(trig, dates.values, side="right")   # first contract with date < trigger
    if (idx >= len(cand)).any():
        raise ValueError(f"{m.market}: contract calendar ends before the last date")
    out = cand.iloc[idx].reset_index(drop=True)
    out.index = dates
    return out


def spliced_price(m: C.Market, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Price (in spot units) and ticker of the contract held on each date."""
    h = held_on(m, dates)
    px = pd.Series(np.nan, index=dates)
    for (root, cycle, pos), g in h.groupby(["root", "cycle", "pos_in_root"], sort=False):
        px.loc[g.index] = contract_price(root, cycle, int(pos), g.index)["price"].to_numpy()
    return pd.DataFrame({"fut_price": px / m.unit_divisor, "fut_contract": h["ticker"].to_numpy()}, index=dates)


def build_paper_market(name: str, last: pd.Timestamp = C.LAST_TARGET, lookback: int = C.LOOKBACK_DAYS) -> pd.DataFrame:
    m = C.MARKETS[name]
    spot, _ = load_spot(m.spot[0])
    spot = spot.dropna()
    rows = []
    for T in paper_calendar(last):
        for k in range(lookback + 1):                        # k > 0 is only ever needed for WTI spot
            d = T - pd.Timedelta(days=k)
            f = spliced_price(m, pd.DatetimeIndex([d])).iloc[0]
            if d in spot.index and pd.notna(f["fut_price"]) and f["fut_price"] > 0 and spot[d] > 0:
                rows.append(dict(market=name, target_wed=T, obs_date=d, spot_price=spot[d],
                                 fut_price=f["fut_price"], fut_contract=f["fut_contract"]))
                break
    df = pd.DataFrame(rows)
    df["spot_logret"] = np.log(df["spot_price"]).diff()
    df["fut_logret"] = np.log(df["fut_price"]).diff()
    df["holding_days"] = df["obs_date"].diff().dt.days
    df["roll"] = df["fut_contract"] != df["fut_contract"].shift(1)
    df.loc[df.index[0], "roll"] = False
    df["sample_period"] = np.where(df["target_wed"] <= C.ORIGINAL_END, "original_1990_2023", "extension_2023_2026")
    return df.iloc[1:].reset_index(drop=True)                 # first row has no return


def build_paper_dataset(last: pd.Timestamp = C.LAST_TARGET) -> pd.DataFrame:
    return pd.concat([build_paper_market(n, last) for n in PAPER_MARKETS], ignore_index=True)
