"""Validation of the generic-to-contract mapping and of held-contract rolls."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import generics, usable_contracts, contract_table



def _log(x: pd.Series) -> pd.Series:
    return np.log(x.where(x > 0))


def generic_roll_events(root: str, cycle: str) -> pd.DataFrame:
    """One row per contract expiry: does Bloomberg roll the generics on the first trading day after the LTD?

    Identity test. If the roll happens between d0 (last day <= LTD) and d1 (next day):
        G1(d1) is the same contract as G2(d0).
    Error if the hypothesis is right   e_roll = |ln G1(d1)/G2(d0)|   (a one-day move of one contract)
    Error if no roll happened          e_none = |ln G1(d1)/G1(d0)|   (a one-day move of one contract)
    Only one of the two compares a contract with itself; the other also contains the
    calendar spread at d0. (G3 is not used: third generics are thin and often stale.) z = (e_none - e_roll) / sigma, sigma = robust daily
    volatility of G1 over the prior 60 days. z >= 2 confirms, z <= -2 contradicts; otherwise the
    spreads were too small relative to volatility to tell, which also means a one-day misidentification
    would change returns by little.
    """
    u = usable_contracts(root, cycle)
    g = generics(root)
    g1 = g["G1"].dropna()
    days = g1.index
    lg = _log(g)
    r1 = lg["G1"].reindex(days).diff()
    sp = (lg["G2"] - lg["G1"]).reindex(days) if "G2" in lg else pd.Series(np.nan, index=days)
    out = []
    for _, c in u.iterrows():
        L = c["LTD"]
        if L < days[0] or L >= days[-1]:
            continue
        i0 = days.searchsorted(L, side="right") - 1
        i1 = i0 + 1
        d0, d1 = days[i0], days[i1]
        a = lambda col, d: lg[col].get(d, np.nan) if col in lg else np.nan
        e_roll = abs(a("G1", d1) - a("G2", d0))
        e_none = abs(a("G1", d1) - a("G1", d0))
        hist = r1.iloc[max(0, i0 - 65): max(1, i0 - 5)].dropna()
        sigma = 1.4826 * np.median(np.abs(hist)) if len(hist) > 10 else np.nan
        z = (e_none - e_roll) / sigma if sigma and sigma > 0 else np.nan
        spread0 = a("G2", d0) - a("G1", d0)
        # second test: one-day jump of the spread s = ln G2 - ln G1 at d1 relative to its quiet-period median
        ds = sp.diff().abs()
        base = ds.iloc[max(0, i0 - 80): max(1, i0 - 20)].median()
        jump = ds.iloc[i1] / base if base and base > 0 else np.nan
        win = ds.iloc[max(0, i0 - 10): i1 + 4]
        jump_is_window_max = bool(pd.notna(jump) and ds.iloc[i1] >= win.max())
        t1 = "confirm" if pd.notna(z) and z >= 2 else ("contradict" if pd.notna(z) and z <= -2 else "weak")
        t2 = "confirm" if pd.notna(jump) and jump >= 8 and jump_is_window_max else "weak"
        if t1 == "contradict":
            v = "contradicted" if t2 != "confirm" else "conflicting"
        elif "confirm" in (t1, t2):
            v = "confirmed"
        elif pd.isna(z) and pd.isna(jump):
            v = "not testable (missing or nonpositive price)"
        else:
            v = "not decisive (spread too small relative to daily volatility)"
        out.append(dict(record_type="generic_roll_event", root=root, contract=c["ticker"], LTD=L.date(),
                        last_day_on_or_before_ltd=d0.date(), first_day_after_ltd=d1.date(),
                        g1_traded_on_ltd=bool(d0 == L), ln_G2_over_G1_at_d0=spread0,
                        err_if_roll_after_ltd=e_roll, err_if_no_roll=e_none, daily_sigma=sigma,
                        z_score=z, identity_test=t1, spread_jump_ratio=jump,
                        spread_jump_is_window_max=jump_is_window_max, spread_jump_test=t2, mapping_verdict=v))
    return pd.DataFrame(out)


def calendar_summary(root: str, cycle: str) -> dict:
    t = contract_table(root, cycle)
    return dict(record_type="calendar_summary", root=root, contract=f"cycle {cycle}",
                n_calendar_rows=len(t), n_usable=int(t.usable.sum()), n_out_of_cycle=int((~t.in_cycle).sum()),
                n_phantom=int(t.phantom.sum()),
                phantom_tickers=" ".join(t[t.phantom].ticker.str.replace(" Index", "").str.replace(" Comdty", "")
                                         .str.replace(" Curncy", "")),
                ltd_min=t[t.usable].LTD.min().date(), ltd_max=t[t.usable].LTD.max().date())


def held_roll_schedule(df: pd.DataFrame) -> pd.DataFrame:
    """One row per change of held contract in the weekly data."""
    d = df.reset_index(drop=True)
    out = []
    for i in range(1, len(d)):
        r, p = d.iloc[i], d.iloc[i - 1]
        if r["fut_contract"] == p["fut_contract"]:
            continue
        old = p["fut_contract"]
        root = p["fut_root"]
        tab = contract_table(root).set_index("ticker")
        old_ltd = tab.loc[old, "LTD"]
        old_fnd = tab.loc[old, "FND"]
        last_obs_old = pd.to_datetime(p["obs_date"])
        out.append(dict(
            record_type="held_contract_roll", market=r["market"], contract=r["fut_contract"],
            previous_contract=old, roll_executed_at_obs=(r["prev_obs_date"].date() if pd.notna(r["prev_obs_date"]) else ""),
            first_interval_target=pd.Timestamp(r["target_wed"]).date(),
            old_contract_trigger=pd.Timestamp(p["roll_trigger"]).date() if pd.notna(p["roll_trigger"]) else "",
            old_contract_LTD=old_ltd.date(), old_contract_FND=old_fnd.date(),
            days_from_roll_to_old_LTD=(old_ltd - last_obs_old).days if pd.notna(last_obs_old) else np.nan,
            old_held_on_or_after_FND=bool(pd.notna(last_obs_old) and last_obs_old >= old_fnd),
            old_held_on_or_after_LTD=bool(pd.notna(last_obs_old) and last_obs_old >= old_ltd),
            new_generic_at_start=r["fut_generic_prev"], new_generic_at_end=r["fut_generic"],
            new_price_at_start=r["fut_price_prev"], old_price_at_roll=p["fut_price"],
            calendar_spread_at_roll=(np.log(r["fut_price_prev"] / p["fut_price"])
                                     if pd.notna(r["fut_price_prev"]) and pd.notna(p["fut_price"])
                                     and r["fut_price_prev"] > 0 and p["fut_price"] > 0 else np.nan),
            interval_return_defined=bool(r["return_defined"]), exclusion_reason=r["exclusion_reason"]))
    return pd.DataFrame(out)
