"""Wednesday sampling and matched-contract weekly log returns.

Observation rule (primary, 'B'): for target Wednesday T the observation date is
the latest day d in {T, T-1, T-2} (calendar days, i.e. Wed, Tue, Mon) on which
every price the two adjacent intervals need is present:
  * spot from the source of the interval ending at T and of the interval starting at T,
  * the contract held over the interval ending at T and the one held over the next interval.
Spot and futures are therefore always taken on the SAME date. Nothing is filled.

Strict rule ('A') is the subset of intervals where both ends are the target Wednesdays.

Return over interval (T-7, T] with held contract c:
  r_spot = ln(S(obs_T) / S(obs_{T-7}))           both from one spot source
  r_fut  = ln(F_c(obs_T) / F_c(obs_{T-7}))       both from the SAME contract c
A log return is computed only if both prices are strictly positive. A return
is never computed across a missing week: if obs_{T-7} does not exist the
interval ending at T is flagged and left undefined.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .contracts import contract_price, held_contracts
from .io import read_series


def apply_exclusions(rel: str, s: pd.Series, exclusions=C.EXCLUSIONS) -> tuple[pd.Series, list[dict]]:
    s = s.copy()
    log = []
    for ex in exclusions:
        if ex.rel != rel:
            continue
        m = (s.index >= pd.Timestamp(ex.start)) & (s.index <= pd.Timestamp(ex.end)) & s.notna()
        for d, v in s[m].items():
            log.append(dict(series=rel, date=d.strftime("%Y-%m-%d"), raw_value=v, reason=ex.reason, evidence=ex.evidence))
        s[m] = np.nan
    return s, log


def load_spot(seg: C.SpotSegment, exclusions=C.EXCLUSIONS) -> tuple[pd.Series, list[dict]]:
    return apply_exclusions(seg.rel, read_series(seg.rel, seg.col), exclusions)


def targets_for(m: C.Market, last: pd.Timestamp = C.LAST_TARGET) -> pd.DatetimeIndex:
    return pd.date_range(m.first_target, last, freq="W-WED")


def segment_for(m: C.Market, T: pd.Timestamp) -> C.SpotSegment:
    for seg in m.spot:
        if (seg.start is None or T >= seg.start) and (seg.end is None or T <= seg.end):
            return seg
    raise ValueError(f"no spot segment for {m.market} {T}")


def _contract_px(row: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    if pd.isna(row.get("root")):
        return pd.DataFrame({"price": np.nan, "generic": "unavailable", "rank": -1}, index=dates)
    return contract_price(row["root"], row["cycle"], int(row["pos_in_root"]), dates)


def build_market(m: C.Market, lookback: int = C.LOOKBACK_DAYS, last: pd.Timestamp = C.LAST_TARGET,
                 price_cutoff: pd.Timestamp | None = None,
                 exclusions: tuple = C.EXCLUSIONS) -> tuple[pd.DataFrame, list[dict]]:
    """Weekly rows for one market. `price_cutoff` truncates all price data (used by the look-ahead test)."""
    T_all = targets_for(m, last)
    excl_log: list[dict] = []
    spots = {}
    for seg in m.spot + ((m.spot_alt,) if m.spot_alt else ()):
        s, lg = load_spot(seg, exclusions)
        if price_cutoff is not None:
            s = s[s.index <= price_cutoff]
        spots[seg.label] = s
        excl_log += lg
    # futures exclusions (e.g. pre-launch rows) are applied to the generics through contract_price -> generics();
    # we apply them here by masking the looked-up prices.
    fut_excl = {}
    for ex in exclusions:
        if "_Curncy" in ex.rel or "_Comdty" in ex.rel or "_Index" in ex.rel:
            name = ex.rel.split("/")[-1].split("_")[0]
            fut_excl.setdefault(name, []).append((pd.Timestamp(ex.start), pd.Timestamp(ex.end)))

    held = held_contracts(m, T_all, m.roll_primary)
    held_next = held.shift(-1)
    held_alt = held_contracts(m, T_all, m.roll_alt)
    held_alt_next = held_alt.shift(-1)

    def px(row, dates):
        out = _contract_px(row, dates)
        if price_cutoff is not None:
            out.loc[out.index > price_cutoff, "price"] = np.nan
        for i, d in enumerate(dates):
            g = out["generic"].iloc[i]
            for a, b in fut_excl.get(g, []):
                if a <= d <= b and pd.notna(out["price"].iloc[i]):
                    excl_log.append(dict(series=f"bloomberg/{g} (as {row.get('ticker')})", date=d.strftime("%Y-%m-%d"),
                                         raw_value=out["price"].iloc[i], reason="futures row excluded",
                                         evidence="see config.EXCLUSIONS"))
                    out.iloc[i, out.columns.get_loc("price")] = np.nan
        return out

    rows = []
    obs_prev = None
    for i, T in enumerate(T_all):
        cands = [T - pd.Timedelta(days=k) for k in range(0, lookback + 1)]
        seg_end = segment_for(m, T_all[i - 1]) if i > 0 else segment_for(m, T)   # source of interval ending T
        seg_start = segment_for(m, T)                                            # source of interval starting T
        need_spot = {seg_end.label, seg_start.label}
        c_end, c_next = held.iloc[i], held_next.iloc[i]
        di = pd.DatetimeIndex(cands)
        f_end = px(c_end, di)
        f_next = px(c_next, di) if i + 1 < len(T_all) else f_end
        chosen = None
        for j, d in enumerate(cands):
            if obs_prev is not None and d <= obs_prev:
                break
            ok = all(pd.notna(spots[l].get(d, np.nan)) for l in need_spot)
            ok = ok and pd.notna(f_end["price"].iloc[j]) and pd.notna(f_next["price"].iloc[j])
            if ok:
                chosen = d
                break
        rec = dict(market=m.market, target_wed=T, obs_date=chosen, prev_obs_date=obs_prev,
                   spot_source=seg_end.label,
                   fut_contract=c_end.get("ticker"), fut_root=c_end.get("root"),
                   fut_contract_month=c_end.get("contract_month"), fut_ltd=c_end.get("LTD"),
                   roll_trigger=c_end.get("roll_trigger"))
        if i > 0:
            prev_c = held.iloc[i - 1].get("ticker")
            rec["roll_at_interval_start"] = bool(prev_c != rec["fut_contract"])
        else:
            rec["roll_at_interval_start"] = False
        rec["reason_obs_missing"] = "" if chosen is not None else _why_missing(cands, obs_prev, spots, need_spot, f_end, f_next)
        rows.append(rec)
        obs_prev = chosen
    df = pd.DataFrame(rows)

    # --- prices and returns at the chosen dates
    out = []
    for i, r in df.iterrows():
        rec = r.to_dict()
        o, p = r["obs_date"], r["prev_obs_date"]
        rec.update(_leg_values(m, spots, held.iloc[i], o, p, px, prefix="fut", src=r["spot_source"]))
        rec.update(_alt_values(m, spots, held_alt.iloc[i], o, p, px))
        out.append(rec)
    df = pd.DataFrame(out)
    df = _flags(m, df)
    return df, excl_log


def _why_missing(cands, obs_prev, spots, need_spot, f_end, f_next) -> str:
    reasons = set()
    for j, d in enumerate(cands):
        if obs_prev is not None and d <= obs_prev:
            break
        for l in need_spot:
            if pd.isna(spots[l].get(d, np.nan)):
                reasons.add(f"spot {l} missing")
        if pd.isna(f_end["price"].iloc[j]):
            reasons.add("held contract price missing")
        if pd.isna(f_next["price"].iloc[j]):
            reasons.add("next held contract price missing")
    return "; ".join(sorted(reasons))


def _leg_values(m, spots, c, o, p, px, prefix, src):
    rec = {}
    S = spots[src]
    for tag, d in (("", o), ("_prev", p)):
        if d is None or pd.isna(d):
            rec[f"spot_price{tag}"] = np.nan
            rec[f"fut_price{tag}"] = np.nan
            rec[f"fut_generic{tag}"] = ""
            continue
        rec[f"spot_price{tag}"] = S.get(d, np.nan)
        f = px(c, pd.DatetimeIndex([d]))
        rec[f"fut_price{tag}"] = f["price"].iloc[0] / m.unit_divisor
        rec[f"fut_generic{tag}"] = f["generic"].iloc[0]
    rec["spot_logret"] = _logret(rec["spot_price"], rec["spot_price_prev"])
    rec["fut_logret"] = _logret(rec["fut_price"], rec["fut_price_prev"])
    if m.spot_alt is not None:
        A = spots[m.spot_alt.label]
        a1 = A.get(o, np.nan) if o is not None and pd.notna(o) else np.nan
        a0 = A.get(p, np.nan) if p is not None and pd.notna(p) else np.nan
        rec.update(spot_alt_source=m.spot_alt.label, spot_alt_price=a1, spot_alt_price_prev=a0,
                   spot_alt_logret=_logret(a1, a0))
    return rec


def _alt_values(m, spots, c, o, p, px):
    rec = dict(alt_roll_rule=m.roll_alt, alt_fut_contract=c.get("ticker"))
    v = {}
    for tag, d in (("", o), ("_prev", p)):
        if d is None or pd.isna(d):
            v[tag] = np.nan
            continue
        v[tag] = px(c, pd.DatetimeIndex([d]))["price"].iloc[0] / m.unit_divisor
    rec["alt_fut_price"], rec["alt_fut_price_prev"] = v[""], v["_prev"]
    rec["alt_fut_logret"] = _logret(v[""], v["_prev"])
    return rec


def _logret(x1, x0):
    if pd.isna(x1) or pd.isna(x0):
        return np.nan
    if x1 <= 0 or x0 <= 0:
        return np.nan          # undefined; flagged in _flags, never replaced
    return float(np.log(x1 / x0))


def _flags(m: C.Market, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    o = pd.to_datetime(df["obs_date"])
    p = pd.to_datetime(df["prev_obs_date"])
    df["holding_days"] = (o - p).dt.days
    df["obs_displaced_days"] = (pd.to_datetime(df["target_wed"]) - o).dt.days
    df["prev_obs_displaced_days"] = (pd.to_datetime(df["target_wed"]) - pd.Timedelta(days=7) - p).dt.days
    nonpos = (df[["spot_price", "spot_price_prev", "fut_price", "fut_price_prev"]] <= 0).any(axis=1)
    df["nonpositive_price"] = nonpos
    df["strict_wednesday"] = (df["obs_displaced_days"] == 0) & (df["prev_obs_displaced_days"] == 0)
    reason = pd.Series("", index=df.index, dtype=object)
    reason[df["obs_date"].isna()] = "no valid observation for this week"
    reason[(reason == "") & df["prev_obs_date"].isna()] = "previous week has no valid observation (no multi-week return)"
    reason[(reason == "") & (df["holding_days"] > C.MAX_HOLDING_DAYS)] = "holding period exceeds 9 days"
    reason[(reason == "") & nonpos] = "nonpositive price: log return undefined"
    reason[(reason == "") & (df["spot_logret"].isna() | df["fut_logret"].isna())] = "return could not be computed"
    df["exclusion_reason"] = reason
    df["return_defined"] = reason == ""
    T = pd.to_datetime(df["target_wed"])
    df["sample_period"] = np.where(T <= C.ORIGINAL_END, "original_1990_2023", "extension_2023_2026")
    if m.market in ("BTC", "NATGAS"):
        df["sample_period"] = "h2_full"
    df["in_primary_sample"] = df["return_defined"]
    return df


WEEKLY_COLUMNS = [
    "market", "sample_period", "target_wed", "obs_date", "prev_obs_date", "holding_days",
    "obs_displaced_days", "prev_obs_displaced_days", "strict_wednesday",
    "spot_source", "spot_price_prev", "spot_price", "spot_logret",
    "fut_root", "fut_contract", "fut_contract_month", "fut_ltd", "roll_trigger", "roll_at_interval_start",
    "fut_generic_prev", "fut_generic", "fut_price_prev", "fut_price", "fut_logret",
    "alt_roll_rule", "alt_fut_contract", "alt_fut_price_prev", "alt_fut_price", "alt_fut_logret",
    "spot_alt_source", "spot_alt_price_prev", "spot_alt_price", "spot_alt_logret",
    "nonpositive_price", "reason_obs_missing", "exclusion_reason", "return_defined", "in_primary_sample",
]
