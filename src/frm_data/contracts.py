"""Contract calendars, generic-to-contract mapping and held-contract selection.

Generic mapping hypothesis (validated in roll_mapping_validation.csv):
on date d, Bloomberg generic k of a root is the k-th usable contract of the
generic cycle whose last tradeable date (LTD) is on or after d. Bloomberg
therefore rolls the generic on the first trading day after the LTD.

We have no individual-contract price files, so a contract's price on date d is
only available when its rank on d is 1, 2 or 3.
"""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
import pandas as pd

from .config import ALL, FutLeg, Market
from .io import read_calendar, read_series

PHANTOM_GAP_DAYS = 31       # FND more than a month after LTD is impossible for a live contract
MAX_CM_LTD_GAP_DAYS = 75    # contract month must be near the LTD


def _decode_year(digits: str, month: int, ltd: pd.Timestamp) -> int:
    """Choose the calendar year implied by a 1- or 2-digit ticker year that is closest to the LTD."""
    n = len(digits)
    base = int(digits)
    cands = [c * (10 ** n) + base for c in range(ltd.year // (10 ** n) - 1, ltd.year // (10 ** n) + 2)]
    return min(cands, key=lambda y: abs((pd.Timestamp(year=y, month=month, day=15) - ltd).days))


@lru_cache(maxsize=None)
def contract_table(root: str, cycle: str = ALL) -> pd.DataFrame:
    """All calendar rows with contract month, phantom flag and usability flag."""
    cal = read_calendar(root)
    rows = []
    for _, r in cal.iterrows():
        m = re.match(rf"^{root}([FGHJKMNQUVXZ])(\d{{1,2}}) ", r["ticker"])
        if not m:
            raise ValueError(f"unparseable ticker {r['ticker']}")
        code, digits = m.group(1), m.group(2)
        month = ALL.index(code) + 1
        year = _decode_year(digits, month, r["LTD"])
        cm = pd.Timestamp(year=year, month=month, day=1)
        phantom = (r["FND"] - r["LTD"]).days > PHANTOM_GAP_DAYS
        inconsistent = abs((cm - r["LTD"]).days) > MAX_CM_LTD_GAP_DAYS
        rows.append(dict(root=root, ticker=r["ticker"], code=code, contract_month=cm,
                         LTD=r["LTD"], FND=r["FND"], phantom=phantom,
                         cm_ltd_inconsistent=inconsistent, in_cycle=code in cycle))
    t = pd.DataFrame(rows)
    t["usable"] = t.in_cycle & ~t.phantom & ~t.cm_ltd_inconsistent
    t = t.sort_values(["LTD", "contract_month"]).reset_index(drop=True)
    u = t[t.usable]
    if u.LTD.duplicated().any():
        raise ValueError(f"{root}: two usable contracts share an LTD")
    if not u.contract_month.is_monotonic_increasing:
        raise ValueError(f"{root}: usable contracts not ordered by contract month")
    return t


@lru_cache(maxsize=None)
def usable_contracts(root: str, cycle: str) -> pd.DataFrame:
    return contract_table(root, cycle).query("usable").reset_index(drop=True)


@lru_cache(maxsize=None)
def generics(root: str) -> pd.DataFrame:
    """Daily frame with columns G1, G2, G3 (NaN where blank)."""
    suffix = "Comdty" if root in ("CL", "NG", "GC") else ("Index" if root in ("SP", "ES") else "Curncy")
    cols = {}
    for k in (1, 2, 3):
        rel = f"bloomberg/{root}{k}_{suffix}.csv"
        try:
            cols[f"G{k}"] = read_series(rel, "PX_LAST")
        except FileNotFoundError:
            continue
    return pd.DataFrame(cols)


def rank_on(ltds: np.ndarray, pos: int, dates: pd.DatetimeIndex) -> np.ndarray:
    """Generic rank of the contract at position `pos` (in LTD-sorted usable list) on each date."""
    first_live = np.searchsorted(ltds, dates.values.astype("datetime64[ns]"), side="left")
    return pos - first_live + 1


def roll_trigger(c: pd.Series, rule: str) -> pd.Timestamp:
    if rule == "cm_start":
        return c["contract_month"]
    if rule == "ltd":
        return c["LTD"]
    if rule == "ltd_month_start":
        return c["LTD"].replace(day=1)
    raise ValueError(rule)


@lru_cache(maxsize=None)
def candidate_list(market: Market) -> pd.DataFrame:
    """Contracts the hedger may hold for a market, in LTD order, across legs."""
    parts = []
    for leg in market.legs:
        u = usable_contracts(leg.root, leg.cycle).copy()
        u["pos_in_root"] = np.arange(len(u))
        if leg.cm_min is not None:
            u = u[u.contract_month >= leg.cm_min]
        if leg.cm_max is not None:
            u = u[u.contract_month <= leg.cm_max]
        u["cycle"] = leg.cycle
        parts.append(u)
    c = pd.concat(parts).sort_values("LTD").reset_index(drop=True)
    return c


def held_contracts(market: Market, targets: pd.DatetimeIndex, rule: str) -> pd.DataFrame:
    """For each target Wednesday T: the contract held over the interval ending T.

    Held contract = first candidate (LTD order) with T < R_c. The decision uses
    only the published contract calendar, never prices, so it has no look-ahead.
    """
    cand = candidate_list(market)
    trig = np.array([roll_trigger(r, rule) for _, r in cand.iterrows()], dtype="datetime64[ns]")
    # roll triggers must be increasing for 'first with T < R_c' to equal 'nearest eligible'
    if not np.all(np.diff(trig) > np.timedelta64(0, "ns")):
        raise ValueError(f"{market.market}/{rule}: roll triggers not strictly increasing")
    idx = np.searchsorted(trig, targets.values.astype("datetime64[ns]"), side="right")
    if (idx >= len(cand)).any():
        raise ValueError(f"{market.market}: contract calendar ends before the last target date")
    out = cand.iloc[idx].reset_index(drop=True)
    out.index = targets
    out["roll_trigger"] = pd.to_datetime(trig[idx])
    return out


def contract_price(root: str, cycle: str, pos_in_root: int, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Price of one specific contract on given dates, read from the generic of matching rank."""
    u = usable_contracts(root, cycle)
    g = generics(root)
    ltds = u.LTD.values.astype("datetime64[ns]")
    rk = rank_on(ltds, int(pos_in_root), dates)
    px = np.full(len(dates), np.nan)
    gk = np.full(len(dates), "", dtype=object)
    for k in (1, 2, 3):
        col = f"G{k}"
        if col not in g:
            continue
        sel = rk == k
        if sel.any():
            vals = g[col].reindex(dates[sel])
            px[sel] = vals.to_numpy()
            gk[sel] = f"{root}{k}"
    beyond = (rk > 3) | (rk < 1)
    gk[beyond] = "unavailable"
    return pd.DataFrame({"price": px, "generic": gk, "rank": rk}, index=dates)
