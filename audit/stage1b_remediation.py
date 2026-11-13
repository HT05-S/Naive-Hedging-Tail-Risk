"""Stage 1B: data remediation, futures-contract validation and weekly dataset construction.

Run from the project root:  python audit/stage1b_remediation.py

Reads data/raw/ (never writes there; SHA-256 checked before and after) and the
external verification downloads in data/external/verification_2026-11-11/.
Writes:
  audit/results/wti_missing_data_analysis.csv
  audit/results/wti_april2020_review.csv
  audit/results/natural_gas_source_comparison.csv
  audit/results/natural_gas_stress_events.csv
  audit/results/roll_mapping_validation.csv
  audit/results/weekly_validation_summary.csv
  audit/results/stage1b_run_log.txt
  data/processed/weekly_market_returns.csv
  data/processed/processed_data_log.csv
No hedge ratios, hedged portfolios or hedge-effectiveness statistics are computed.
"""
from __future__ import annotations

import sys
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frm_data import config as C                    # noqa: E402
from frm_data import io                              # noqa: E402
from frm_data.contracts import contract_table, generics, usable_contracts, rank_on  # noqa: E402
from frm_data.validation import calendar_summary, generic_roll_events, held_roll_schedule  # noqa: E402
from frm_data.weekly import WEEKLY_COLUMNS, build_market  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)

RES = io.RESULTS
PROC = io.PROCESSED
EXT = io.EXTERNAL
RES.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)
HASH_BEFORE = io.hash_tree()

CYCLES = {"CL": C.ALL, "NG": C.ALL, "BP": "HMUZ", "SP": "HMUZ", "ES": "HMUZ", "GC": "GJMQVZ", "BTC": C.ALL}
FRED_WTI = io.read_series("fred/DCOILWTICO.csv")
FRED_HH = io.read_series("fred/DHHNGSP.csv")
BBG_HH = io.read_series("bloomberg/NGUSHHUB_Index.csv")
CL = generics("CL")
NG = generics("NG")

# Cao & Conlon (2025) Table 2, p. 985. WTI and Gold columns read directly; GBPUSD and S&P values were
# re-assembled from a PDF text extraction in which those two columns were displaced (order: Mean, Max,
# Min, Median, Std, Skew, Kurt) and should be checked against the printed table.
PAPER_T2 = {
    ("WTI", "spot"): dict(mean=0.001, max=0.462, min=-0.481, median=0.003, std=0.056, skew=-0.410, kurt=9.778),
    ("WTI", "fut"): dict(mean=0.001, max=0.466, min=-0.482, median=0.003, std=0.055, skew=-0.524, kurt=11.043),
    ("GOLD", "spot"): dict(mean=0.001, max=0.137, min=-0.124, median=0.001, std=0.022, skew=-0.266, kurt=4.101),
    ("GOLD", "fut"): dict(mean=0.001, max=0.129, min=-0.131, median=0.001, std=0.022, skew=-0.290, kurt=4.473),
    ("GBPUSD", "spot"): dict(mean=0.000, max=0.055, min=-0.091, median=0.000, std=0.014, skew=-0.823, kurt=4.854),
    ("GBPUSD", "fut"): dict(mean=0.000, max=0.050, min=-0.103, median=0.000, std=0.014, skew=-0.961, kurt=6.134),
    ("SP500", "spot"): dict(mean=0.001, max=0.107, min=-0.165, median=0.003, std=0.023, skew=-0.819, kurt=5.143),
    ("SP500", "fut"): dict(mean=0.001, max=0.111, min=-0.175, median=0.003, std=0.023, skew=-0.822, kurt=5.166),
}
PAPER_RELIABILITY = {"WTI": "read directly", "GOLD": "read directly",
                     "GBPUSD": "re-assembled from displaced text; verify", "SP500": "re-assembled from displaced text; verify"}


def d(x):
    return pd.Timestamp(x).strftime("%Y-%m-%d") if pd.notna(x) else ""


def write(df: pd.DataFrame, path: Path, full_precision: bool = False):
    # processed data keep full float precision; result tables use 10 significant digits
    df.to_csv(path, index=False, float_format=None if full_precision else "%.10g")
    print(f"wrote {path.relative_to(ROOT)} ({len(df)} rows)")


def wednesdays(a, b):
    return pd.date_range(a, b, freq="W-WED")


# ----------------------------------------------------------------------------------------------
# Builds
# ----------------------------------------------------------------------------------------------
def build_all():
    out, logs = {}, []
    for k, m in C.MARKETS.items():
        df, lg = build_market(m)
        out[k] = df
        logs += [dict(market=k, **x) for x in lg]
        print(f"built {k}: {int(df.return_defined.sum())} defined weekly returns")
    return out, logs


# ----------------------------------------------------------------------------------------------
# PART 2: WTI missing data
# ----------------------------------------------------------------------------------------------
def external_verification() -> list[dict]:
    rows = []
    specs = [("WTI", "fred/DCOILWTICO.csv", "FRED_DCOILWTICO_live.csv", "EIA_RWTCd.xls"),
             ("NATGAS", "fred/DHHNGSP.csv", "FRED_DHHNGSP_live.csv", "EIA_RNGWHHDd.xls")]
    for mk, loc, live, eia in specs:
        L = io.read_series(loc)
        V = io.read_series(live, base=EXT)
        X = io.read_eia_xls(EXT / eia)
        j = pd.concat([L.rename("loc"), V.rename("live"), X.rename("eia")], axis=1)
        both = j.dropna(subset=["loc", "live"])
        be = j.dropna(subset=["loc", "eia"])
        rows.append(dict(
            record_type="external_verification", market=mk, item=loc,
            local_rows=len(L), local_valid=int(L.notna().sum()), local_blank=int(L.isna().sum()),
            live_fred_rows=len(V), live_fred_valid=int(V.notna().sum()), live_fred_blank=int(V.isna().sum()),
            eia_rows=len(X), eia_valid=int(X.notna().sum()),
            local_vs_live_identical_values=int(np.isclose(both["loc"], both["live"]).sum()),
            local_vs_live_compared=len(both),
            local_vs_eia_identical_values=int(np.isclose(be["loc"], be["eia"]).sum()),
            local_vs_eia_compared=len(be),
            local_blank_but_live_valid=int((j["loc"].isna() & j["live"].notna()).sum()),
            local_blank_but_eia_valid=int((j["loc"].isna() & j["eia"].notna()).sum()),
            eia_dates_absent_from_local=len(X.index.difference(L.index)),
            local_first=d(L.dropna().index.min()), local_last=d(L.dropna().index.max()),
            live_last=d(V.dropna().index.max()), eia_last=d(X.dropna().index.max()),
            sha256_live=io.sha256(EXT / live), sha256_eia=io.sha256(EXT / eia),
            note="downloaded 2026-11-11 from fred.stlouisfed.org (fredgraph.csv) and eia.gov (hist_xls); "
                 "stored outside data/raw"))
    return rows


def wti_missing(primary: pd.DataFrame) -> pd.DataFrame:
    rows = external_verification()
    w = FRED_WTI
    cl1 = CL["G1"]
    blank = w[w.isna()].index
    # blank by year
    W_all = wednesdays(C.FIRST_TARGET, C.LAST_TARGET)
    for y in range(1990, 2027):
        b = blank[blank.year == y]
        wy = W_all[W_all.year == y]
        miss_w = wy[~wy.isin(w.dropna().index)]
        rows.append(dict(record_type="blank_by_year", market="WTI", item=str(y),
                         fred_rows=int((w.index.year == y).sum()), fred_blank_rows=len(b),
                         blank_rows_cl1_traded=int(cl1.reindex(b).notna().sum()),
                         blank_rows_cl1_not_traded=int(cl1.reindex(b).isna().sum()),
                         wednesdays=len(wy), missing_wednesdays=len(miss_w),
                         missing_wednesdays_cl1_traded=int(cl1.reindex(miss_w).notna().sum()),
                         missing_wednesdays_cl1_not_traded=int(cl1.reindex(miss_w).isna().sum())))
    # blank-run lengths (1990 onwards)
    bb = w.loc["1990":].isna().astype(int)
    grp = (bb.diff() != 0).cumsum()
    runs = bb.groupby(grp).agg(["sum", "size"])
    runs = runs[runs["sum"] > 0]["size"].value_counts().sort_index()
    for L_, n in runs.items():
        rows.append(dict(record_type="blank_run_length", market="WTI", item=f"{L_} consecutive rows", count=int(n)))
    # weekday of blanks
    for wd, n in pd.Series(blank[blank.year >= 1990].day_of_week).value_counts().sort_index().items():
        rows.append(dict(record_type="blank_weekday", market="WTI", item="Mon Tue Wed Thu Fri".split()[wd], count=int(n)))

    # approaches A / B(1-day) / B(2-day) / C
    variants = {"A_strict_wednesday": None, "B_lookback_1_day": 1, "B_lookback_2_days (primary)": 2}
    m = C.MARKETS["WTI"]
    built = {"B_lookback_2_days (primary)": primary}
    lb0, _ = build_market(m, lookback=0)
    lb1, _ = build_market(m, lookback=1)
    built["A_strict_wednesday"] = lb0
    built["B_lookback_1_day"] = lb1
    # consistency: strict rows of the primary build equal the lookback-0 build
    strict_ok = set(primary.loc[primary.return_defined & primary.strict_wednesday, "target_wed"]) == \
        set(lb0.loc[lb0.return_defined, "target_wed"])
    for name, df in built.items():
        for period, mask in (("original_1990_2023", df.target_wed <= C.ORIGINAL_END),
                             ("extension_2023_2026", df.target_wed > C.ORIGINAL_END),
                             ("full", df.target_wed >= C.FIRST_TARGET)):
            x = df[mask]
            dfn = x[x.return_defined]
            hd = dfn.holding_days.value_counts().to_dict()
            rows.append(dict(
                record_type="approach_comparison", market="WTI", item=name, period=period,
                target_weeks=len(x), possible_returns=len(x) - (1 if period != "extension_2023_2026" else 0),
                retained_returns=len(dfn), excluded_returns=len(x) - len(dfn) - (1 if period != "extension_2023_2026" else 0),
                weeks_without_observation=int(x.obs_date.isna().sum()),
                displaced_observation_dates=int((x.obs_displaced_days > 0).sum()),
                returns_with_displaced_end=int((dfn.obs_displaced_days > 0).sum()),
                returns_with_displaced_start=int((dfn.prev_obs_displaced_days > 0).sum()),
                holding_5d=hd.get(5, 0), holding_6d=hd.get(6, 0), holding_7d=hd.get(7, 0),
                holding_8d=hd.get(8, 0), holding_9d=hd.get(9, 0),
                spot_std=dfn.spot_logret.std(), fut_std=dfn.fut_logret.std(),
                spot_min=dfn.spot_logret.min(), spot_max=dfn.spot_logret.max(),
                corr_spot_fut=dfn.spot_logret.corr(dfn.fut_logret),
                strict_subset_check=("primary strict rows == lookback-0 build" if strict_ok else "MISMATCH")
                if name.startswith("A") else ""))
    rows.append(dict(record_type="approach_comparison", market="WTI", item="C_independent_source_recovery",
                     period="full", retained_returns=0,
                     note="No compatible independent source: EIA (the original publisher) is blank on every FRED-blank "
                          "date; USCRWTIC equals CL1 on 86% of days (futures-based, Stage 1 A05); CL1 is a futures "
                          "price. Recovering spot from any of these would replace spot with futures and remove basis."))
    # per missing Wednesday detail
    miss = W_all[~W_all.isin(w.dropna().index)]
    p = primary.set_index("target_wed")
    for T in miss:
        r = p.loc[T] if T in p.index else None
        rows.append(dict(
            record_type="missing_wednesday", market="WTI", item=d(T),
            period="original_1990_2023" if T <= C.ORIGINAL_END else "extension_2023_2026",
            cl1_on_wednesday=CL["G1"].get(T, np.nan), fred_tue=w.get(T - pd.Timedelta(days=1), np.nan),
            fred_mon=w.get(T - pd.Timedelta(days=2), np.nan),
            primary_obs_date=d(r["obs_date"]) if r is not None else "",
            primary_outcome=("observed on " + d(r["obs_date"])) if r is not None and pd.notna(r["obs_date"])
            else ("no observation: " + (r["reason_obs_missing"] if r is not None else "")),
            likely_cause="exchange holiday or closure (CL1 also missing)" if pd.isna(CL["G1"].get(T, np.nan))
            else "EIA did not publish a spot price although NYMEX traded"))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------
# PART 3: April 2020
# ----------------------------------------------------------------------------------------------
def april2020(primary: pd.DataFrame) -> pd.DataFrame:
    u = usable_contracts("CL", C.ALL)
    ltds = u.LTD.values.astype("datetime64[ns]")
    days = CL.loc["2020-03-02":"2020-05-29"].index
    usc = io.read_series("bloomberg/USCRWTIC_Index.csv")
    rows = []
    m = C.MARKETS["WTI"]
    from frm_data.contracts import held_contracts
    tg = wednesdays("2020-03-04", "2020-06-03")
    hp = held_contracts(m, tg, "ltd")
    ha = held_contracts(m, tg, "ltd_month_start")
    hc = held_contracts(m, tg, "cm_start")
    for dt in days:
        first_live = int(np.searchsorted(ltds, np.datetime64(dt), side="left"))
        ids = [u.ticker.iloc[first_live + k].replace(" Comdty", "") for k in range(3)]
        T = tg[tg >= dt][0]
        rec = dict(record_type="daily", date=d(dt), weekday=dt.day_name()[:3],
                   is_target_wednesday=bool(dt.day_of_week == 2),
                   fred_spot=FRED_WTI.get(dt, np.nan), uscrwtic=usc.get(dt, np.nan),
                   CL1=CL.G1.get(dt, np.nan), CL1_contract=ids[0], CL1_LTD=d(u.LTD.iloc[first_live]),
                   CL2=CL.G2.get(dt, np.nan), CL2_contract=ids[1],
                   CL3=CL.G3.get(dt, np.nan), CL3_contract=ids[2],
                   interval_target=d(T),
                   held_primary_ltd_rule=hp.loc[T, "ticker"].replace(" Comdty", ""),
                   held_alt_ltd_month_start_rule=ha.loc[T, "ticker"].replace(" Comdty", ""),
                   paper_literal_cm_start_rule=hc.loc[T, "ticker"].replace(" Comdty", ""),
                   paper_literal_rule_feasible=bool(T < hc.loc[T, "LTD"]),
                   all_prices_positive=bool(all(v > 0 for v in [FRED_WTI.get(dt, 1), CL.G1.get(dt, 1), CL.G2.get(dt, 1), CL.G3.get(dt, 1)] if pd.notna(v))))
        notes = []
        if dt == pd.Timestamp("2020-04-20"):
            notes.append("CLK20 settles -37.63 on its penultimate trading day; FRED spot -36.98; Monday, not a sampled date")
        if dt == pd.Timestamp("2020-04-21"):
            notes.append("CLK20 last trading day (calendar LTD); final settlement +10.01")
        if dt == pd.Timestamp("2020-04-22"):
            notes.append("first day after CLK20 expiry: CL1 is now CLM20 (13.78 = CL2 identity continues from 11.57 on 04-21)")
        if dt == pd.Timestamp("2020-03-20"):
            notes.append("CLJ20 last trading day")
        if dt == pd.Timestamp("2020-05-19"):
            notes.append("CLM20 last trading day")
        if pd.notna(FRED_WTI.get(dt, np.nan)) and pd.notna(CL.G1.get(dt, np.nan)) and CL.G1.get(dt) > 0 and FRED_WTI.get(dt) > 0:
            rec["fred_over_CL1"] = FRED_WTI.get(dt) / CL.G1.get(dt)
        rec["notes"] = "; ".join(notes)
        rows.append(rec)
    # weekly rows
    p = primary[(primary.target_wed >= "2020-03-04") & (primary.target_wed <= "2020-05-27")]
    for _, r in p.iterrows():
        o, q = r.obs_date, r.prev_obs_date
        splice = np.log(CL.G1.get(o) / CL.G1.get(q)) if CL.G1.get(o) > 0 and CL.G1.get(q) > 0 else np.nan
        rec = dict(record_type="weekly", date=d(r.target_wed), weekday="Wed", is_target_wednesday=True,
                   interval_target=d(r.target_wed), obs_date=d(o), prev_obs_date=d(q),
                   fred_spot_prev=r.spot_price_prev, fred_spot=r.spot_price, spot_logret=r.spot_logret,
                   held_primary_ltd_rule=r.fut_contract.replace(" Comdty", ""), primary_generic_prev=r.fut_generic_prev,
                   primary_generic=r.fut_generic, primary_fut_prev=r.fut_price_prev, primary_fut=r.fut_price,
                   primary_fut_logret=r.fut_logret, primary_contract_LTD=d(r.fut_ltd),
                   held_alt_ltd_month_start_rule=r.alt_fut_contract.replace(" Comdty", ""), alt_fut_logret=r.alt_fut_logret,
                   generic_splice_CL1_logret=splice,
                   all_prices_positive=bool(not r.nonpositive_price), spot_return_defined=pd.notna(r.spot_logret),
                   fut_return_defined=pd.notna(r.fut_logret), exclusion=r.exclusion_reason or "none")
        notes = []
        if r.target_wed == pd.Timestamp("2020-04-22"):
            k0, k1, m1, m2 = CL.G1.get("2020-04-15"), CL.G1.get("2020-04-21"), CL.G2.get("2020-04-21"), CL.G1.get("2020-04-22")
            split = np.log(k1 / k0) + np.log(m2 / m1)
            rec["expiry_split_roll_logret"] = split
            notes.append(f"expiry-based split roll: hold CLK20 04-15 -> 04-21 (LTD, {k0} -> {k1}) then CLM20 04-21 -> 04-22 "
                         f"({m1} -> {m2}); log return {split:.4f}. No rule that uses Wednesday or LTD settlements touches "
                         f"the -37.63 print. The matched-contract CLM20 return is {r.fut_logret:.4f}; the CL1 generic "
                         f"splice (CLK20 on 04-15 to CLM20 on 04-22) is {splice:.4f} and is a price difference between "
                         f"two contracts, not a position return")
        if r.target_wed == pd.Timestamp("2020-03-25"):
            notes.append("roll week: CLJ20 expired 03-20; held CLK20 is CL2 on 03-18 and CL1 on 03-25")
        rec["notes"] = "; ".join(notes)
        rows.append(rec)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------
# PART 4: natural gas
# ----------------------------------------------------------------------------------------------
NG_PERIODS = [("1997-01_2006-12", "1997-01-01", "2006-12-31"), ("1999-01_2006-12", "1999-01-01", "2006-12-31"),
              ("2007-01_2019-12", "2007-01-01", "2019-12-31"), ("2020-01_2021-04", "2020-01-01", "2021-04-30"),
              ("2021-05_2026-11", "2021-05-01", "2026-11-09")]


def ng_variants():
    base = C.MARKETS["NATGAS"]
    fred = replace(base, market="NATGAS_A_FRED", spot=(C.SpotSegment("FRED:DHHNGSP", "fred/DHHNGSP.csv", "DHHNGSP"),),
                   first_target=pd.Timestamp("1997-01-08"))
    bbg = replace(base, market="NATGAS_B_BBG", spot=(C.SpotSegment("BBG:NGUSHHUB", "bloomberg/NGUSHHUB_Index.csv", "PX_LAST"),))
    out = {}
    out["A_FRED_spot"], _ = build_market(fred)
    out["B_BBG_spot_as_delivered"], _ = build_market(bbg, exclusions=())
    out["B_BBG_spot_with_exclusions"], _ = build_market(bbg)
    return out


def ng_source(primary: pd.DataFrame, variants: dict) -> pd.DataFrame:
    rows = [r for r in external_verification() if r["market"] == "NATGAS"]
    ng1 = NG.G1.dropna()
    for name, a, b in NG_PERIODS:
        W = wednesdays(a, min(pd.Timestamp(b), C.LAST_TARGET))
        for lab, s in (("FRED:DHHNGSP", FRED_HH), ("BBG:NGUSHHUB", BBG_HH)):
            x = s.loc[a:b]
            other = BBG_HH if lab.startswith("FRED") else FRED_HH
            j = pd.concat([x.rename("x"), other.loc[a:b].rename("o")], axis=1, sort=True).dropna()
            ld = np.log(j.x / j.o) if len(j) else pd.Series(dtype=float)
            rows.append(dict(record_type="coverage_by_period", item=lab, period=name,
                             rows=len(x), valid=int(x.notna().sum()), blank_rows=int(x.isna().sum()),
                             ng1_trading_days=int(ng1.loc[a:b].shape[0]),
                             ng1_days_without_spot=int((~ng1.loc[a:b].index.isin(x.dropna().index)).sum()),
                             wednesdays=len(W), missing_wednesdays=int((~W.isin(x.dropna().index)).sum()),
                             aligned_wednesdays_with_NG1=int((W.isin(x.dropna().index) & W.isin(ng1.index)).sum()),
                             days_both_sources=len(j),
                             median_abs_log_diff_vs_other=float(ld.abs().median()) if len(j) else np.nan,
                             p95_abs_log_diff_vs_other=float(ld.abs().quantile(.95)) if len(j) else np.nan,
                             max_abs_log_diff_vs_other=float(ld.abs().max()) if len(j) else np.nan,
                             exact_equal_share=float(np.isclose(j.x, j.o, atol=0.0051).mean()) if len(j) else np.nan))
    # monthly and yearly date-alignment diagnostics
    rows += ng_alignment()
    # option comparison
    opts = {"C_composite (primary)": primary, **variants}
    for name, df in opts.items():
        for pname, a, b in [("full", "1990-01-01", "2026-12-31")] + NG_PERIODS[1:]:
            x = df[(df.target_wed >= a) & (df.target_wed <= b)]
            y = x[x.return_defined]
            bc = y.spot_logret - y.fut_logret
            rows.append(dict(record_type="option_comparison", item=name, period=pname,
                             target_weeks=len(x), defined_returns=len(y),
                             first_return=d(y.target_wed.min()) if len(y) else "", last_return=d(y.target_wed.max()) if len(y) else "",
                             weeks_without_observation=int(x.obs_date.isna().sum()),
                             displaced=int((y.obs_displaced_days > 0).sum()),
                             spot_std=y.spot_logret.std(), fut_std=y.fut_logret.std(),
                             corr_spot_fut=y.spot_logret.corr(y.fut_logret),
                             basis_change_std=bc.std(), spot_min=y.spot_logret.min(), spot_max=y.spot_logret.max(),
                             spot_min_week=d(y.loc[y.spot_logret.idxmin(), "target_wed"]) if len(y) else "",
                             spot_max_week=d(y.loc[y.spot_logret.idxmax(), "target_wed"]) if len(y) else "",
                             sources=" ".join(sorted(y.spot_source.unique())) if len(y) else ""))
    # spot-source transition check (composite)
    t = primary[(primary.target_wed >= "2007-03-14") & (primary.target_wed <= "2007-04-25")]
    for _, r in t.iterrows():
        rows.append(dict(record_type="source_transition", item=d(r.target_wed), period="2007-03/04",
                         sources=r.spot_source, note=f"obs {d(r.obs_date)} prev {d(r.prev_obs_date)} "
                                                     f"spot {r.spot_price_prev}->{r.spot_price} r={r.spot_logret:.4f}; "
                                                     f"BBG {BBG_HH.get(r.obs_date, np.nan)} FRED {FRED_HH.get(r.obs_date, np.nan)} on obs date"))
    return pd.DataFrame(rows)


def ng_alignment() -> list[dict]:
    hh, bh, ng1 = FRED_HH.dropna(), BBG_HH.dropna(), NG.G1.dropna()
    d0 = pd.DataFrame({"bb": bh}).join(pd.DataFrame({"f0": hh, "fm1": hh.shift(1), "fp1": hh.shift(-1)}), how="inner")
    for c in ("f0", "fm1", "fp1"):
        d0["eq_" + c] = np.isclose(d0.bb, d0[c], atol=0.0051)
        d0["cl_" + c] = (d0.bb - d0[c]).abs()
    d0["closer_to_prev_than_same"] = d0.cl_fm1 < d0.cl_f0
    lr = lambda s: np.log(s).diff()
    chg = pd.DataFrame({"bb": lr(bh), "fred": lr(hh)}).join(pd.DataFrame({"n0": lr(ng1), "nm1": lr(ng1).shift(1)}), how="left")
    rows = []
    bdays = pd.bdate_range("1999-01-01", "2026-11-09")
    for freq, label in (("M", "alignment_by_month"), ("Y", "alignment_by_year")):
        per = bdays.to_period(freq)
        for p_ in per.unique():
            days = bdays[per == p_]
            if label == "alignment_by_month" and not ("2019-01" <= str(p_) <= "2021-12"):
                continue
            trd = days[days.isin(ng1.index)]
            mons = trd[trd.day_of_week == 0]
            nontrd = days[~days.isin(ng1.index)]
            x = d0[d0.index.isin(days)]
            c = chg[chg.index.isin(days)]
            vals = bh[bh.index.isin(days)]
            rows.append(dict(record_type=label, item=str(p_), days_both_sources=len(x),
                             share_bbg_equals_fred_same_day=x.eq_f0.mean() if len(x) else np.nan,
                             share_bbg_equals_fred_prev_day=x.eq_fm1.mean() if len(x) else np.nan,
                             share_bbg_equals_fred_next_day=x.eq_fp1.mean() if len(x) else np.nan,
                             share_bbg_closer_to_fred_prev_day=x.closer_to_prev_than_same.mean() if len(x) else np.nan,
                             ng1_trading_mondays=len(mons), mondays_missing_in_bbg=int((~mons.isin(bh.index)).sum()),
                             mondays_missing_in_fred=int((~mons.isin(hh.index)).sum()),
                             bbg_prints_on_nymex_closed_weekdays=int(nontrd.isin(bh.index).sum()),
                             fred_prints_on_nymex_closed_weekdays=int(nontrd.isin(hh.index).sum()),
                             bbg_share_values_with_4_decimals=float(np.mean([abs(round(v, 2) - v) > 1e-9 for v in vals])) if len(vals) else np.nan,
                             corr_bbg_change_with_NG1_same_day=c.bb.corr(c.n0), corr_bbg_change_with_NG1_prev_day=c.bb.corr(c.nm1),
                             corr_fred_change_with_NG1_same_day=c.fred.corr(c.n0), corr_fred_change_with_NG1_prev_day=c.fred.corr(c.nm1)))
    # window-level summary
    for name, a, b in (("pre-window 2019", "2019-01-01", "2019-12-31"), ("flow-dated window", "2020-01-01", "2021-03-12"),
                       ("post-window 2021-03-15..2021-12", "2021-03-15", "2021-12-31")):
        c = chg.loc[a:b]
        x = d0.loc[a:b]
        days = bdays[(bdays >= a) & (bdays <= b)]
        trd = days[days.isin(ng1.index)]
        mons = trd[trd.day_of_week == 0]
        nontrd = days[~days.isin(ng1.index)]
        rows.append(dict(record_type="alignment_window_summary", item=name, days_both_sources=len(x),
                         share_bbg_equals_fred_same_day=x.eq_f0.mean(), share_bbg_equals_fred_prev_day=x.eq_fm1.mean(),
                         share_bbg_closer_to_fred_prev_day=x.closer_to_prev_than_same.mean(),
                         ng1_trading_mondays=len(mons), mondays_missing_in_bbg=int((~mons.isin(bh.index)).sum()),
                         mondays_missing_in_fred=int((~mons.isin(hh.index)).sum()),
                         bbg_prints_on_nymex_closed_weekdays=int(nontrd.isin(bh.index).sum()),
                         bbg_prints_on_nymex_closed_dates=" ".join(d(z) for z in nontrd[nontrd.isin(bh.index)]),
                         fred_prints_on_nymex_closed_weekdays=int(nontrd.isin(hh.index).sum()),
                         corr_bbg_change_with_NG1_same_day=c.bb.corr(c.n0), corr_bbg_change_with_NG1_prev_day=c.bb.corr(c.nm1),
                         corr_fred_change_with_NG1_same_day=c.fred.corr(c.n0), corr_fred_change_with_NG1_prev_day=c.fred.corr(c.nm1)))
    return rows


NG_EVENTS = [
    ("Winter 2000-01 price spike", "2000-11-29", "2001-01-17"),
    ("Feb 2003 cold snap spike", "2003-02-12", "2003-03-12"),
    ("Hurricanes Katrina and Rita 2005", "2005-08-24", "2005-10-26"),
    ("Polar vortex 2014", "2014-01-15", "2014-03-12"),
    ("Bomb cyclone Jan 2018", "2017-12-27", "2018-01-24"),
    ("COVID 2020 (inside Bloomberg flow-dated window)", "2020-03-04", "2020-04-29"),
    ("Winter Storm Uri Feb 2021", "2021-02-03", "2021-03-10"),
    ("Aug 2022 price peak", "2022-08-10", "2022-09-14"),
    ("Jan 2024 cold spike", "2024-01-03", "2024-01-31"),
    ("Sep 2025 Bloomberg bad print", "2025-09-17", "2025-10-08"),
    ("Jan-Feb 2026 cold spike and NGG26 expiry", "2026-01-14", "2026-02-11"),
]


def ng_stress(primary, variants) -> pd.DataFrame:
    rows = []
    opts = {"C_primary": primary, "A_FRED": variants["A_FRED_spot"], "B_BBG_raw": variants["B_BBG_spot_as_delivered"]}
    idx = {k: v.set_index("target_wed") for k, v in opts.items()}
    for ev, a, b in NG_EVENTS:
        for T in wednesdays(a, b):
            rec = dict(record_type="weekly", event=ev, target_wed=d(T))
            for k, v in idx.items():
                if T not in v.index:
                    rec[f"{k}_status"] = "outside option sample"
                    continue
                r = v.loc[T]
                rec[f"{k}_obs"] = d(r.obs_date)
                rec[f"{k}_spot_prev"] = r.spot_price_prev
                rec[f"{k}_spot"] = r.spot_price
                rec[f"{k}_spot_logret"] = r.spot_logret
                rec[f"{k}_fut_logret"] = r.fut_logret
                rec[f"{k}_basis_change"] = r.spot_logret - r.fut_logret if r.return_defined else np.nan
                rec[f"{k}_status"] = "defined" if r.return_defined else r.exclusion_reason
            rec["fut_contract"] = idx["C_primary"].loc[T, "fut_contract"] if T in idx["C_primary"].index else ""
            rows.append(rec)
    # daily detail for Uri, Sep 2025 and Jan 2026
    u = usable_contracts("NG", C.ALL)
    ltds = u.LTD.values.astype("datetime64[ns]")
    for ev, a, b in (("Winter Storm Uri Feb 2021", "2021-02-08", "2021-02-26"),
                     ("Sep 2025 Bloomberg bad print", "2025-09-22", "2025-10-03"),
                     ("Jan-Feb 2026 cold spike and NGG26 expiry", "2026-01-20", "2026-02-04"),
                     ("Hurricanes Katrina and Rita 2005", "2005-09-19", "2005-10-12")):
        days = pd.bdate_range(a, b)
        for dt in days:
            fl = int(np.searchsorted(ltds, np.datetime64(dt), side="left"))
            rows.append(dict(record_type="daily", event=ev, target_wed="", date=d(dt), weekday=dt.day_name()[:3],
                             fred=FRED_HH.get(dt, np.nan), bbg=BBG_HH.get(dt, np.nan),
                             NG1=NG.G1.get(dt, np.nan), NG1_contract=u.ticker.iloc[fl].replace(" Comdty", ""),
                             NG2=NG.G2.get(dt, np.nan), NG2_contract=u.ticker.iloc[fl + 1].replace(" Comdty", ""),
                             NG1_LTD=d(u.LTD.iloc[fl])))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------
# PART 5: roll mapping validation
# ----------------------------------------------------------------------------------------------
def roll_validation(frames: dict) -> pd.DataFrame:
    parts = []
    summ = []
    for root, cyc in CYCLES.items():
        summ.append(calendar_summary(root, cyc))
        e = generic_roll_events(root, cyc)
        parts.append(e)
        vc = e.mapping_verdict.value_counts()
        testable = len(e) - int(vc.filter(like="not testable").sum())
        summ.append(dict(record_type="generic_roll_summary", root=root, contract=f"{len(e)} expiries in data span",
                         confirmed=int(vc.get("confirmed", 0)), contradicted=int(vc.get("contradicted", 0)),
                         conflicting=int(vc.get("conflicting", 0)),
                         not_decisive=int(vc.filter(like="not decisive").sum()),
                         not_testable=int(vc.filter(like="not testable").sum()), testable=testable,
                         g1_traded_on_every_ltd=bool(e.g1_traded_on_ltd.all())))
    for k, df in frames.items():
        sched = held_roll_schedule(df)
        parts.append(sched)
        x = df[df.return_defined]
        summ.append(dict(record_type="held_roll_summary", market=k, contract=f"{len(sched)} rolls",
                         rolls=len(sched), roll_intervals_defined=int(sched.interval_return_defined.sum()),
                         min_days_roll_to_old_LTD=sched.days_from_roll_to_old_LTD.min(),
                         median_days_roll_to_old_LTD=sched.days_from_roll_to_old_LTD.median(),
                         held_on_or_after_FND=int(sched.old_held_on_or_after_FND.sum()),
                         held_on_or_after_LTD=int(sched.old_held_on_or_after_LTD.sum()),
                         generic_usage_start=" ".join(f"{a}:{b}" for a, b in x.fut_generic_prev.value_counts().items()),
                         generic_usage_end=" ".join(f"{a}:{b}" for a, b in x.fut_generic.value_counts().items()),
                         intervals_contract_unavailable=int(((df.fut_generic == "unavailable") | (df.fut_generic_prev == "unavailable")).sum()),
                         alt_rule=C.MARKETS[k].roll_alt,
                         corr_primary_vs_alt_fut=x.fut_logret.corr(x.alt_fut_logret),
                         intervals_alt_contract_differs=int((x.fut_contract != x.alt_fut_contract).sum()),
                         max_abs_primary_minus_alt=(x.fut_logret - x.alt_fut_logret).abs().max()))
    # held into notice period: every interval (not only rolls) where the held contract is observed on/after FND
    for k, df in frames.items():
        root_fnd = {}
        for leg in C.MARKETS[k].legs:
            t = contract_table(leg.root).set_index("ticker")
            root_fnd.update(t.FND.to_dict())
        x = df[df.return_defined].copy()
        x["fnd"] = x.fut_contract.map(root_fnd)
        n = int((pd.to_datetime(x.obs_date) >= x.fnd).sum())
        summ.append(dict(record_type="notice_period_check", market=k, contract="all intervals",
                         intervals_obs_on_or_after_FND=n,
                         note="CL/NG: FND is after LTD, so the LTD rule never reaches it. GC: FND is the last business "
                              "day before the contract month, so the paper's first-of-month rule can sample the old "
                              "contract on its FND. SP/ES/BTC are cash settled; BP FND follows LTD."))
    # S&P: SP vs ES held-contract overlap (same rule, ES product)
    es = replace(C.MARKETS["SP500"], market="SP500_ES_only", legs=(C.FutLeg("ES", "HMUZ", cm_min=pd.Timestamp("1997-12-01")),),
                 first_target=pd.Timestamp("1997-09-10"))
    esdf, _ = build_market(es)
    sp = frames["SP500"].set_index("target_wed")
    e2 = esdf.set_index("target_wed")
    j = sp.join(e2[["fut_logret", "fut_contract", "return_defined"]].add_suffix("_es"), how="inner")
    j = j[j.return_defined & j.return_defined_es & (j.index <= "2021-08-25")]
    diff = j.fut_logret - j.fut_logret_es
    summ.append(dict(record_type="sp_es_overlap", market="SP500", contract="SP-held vs ES-held weekly returns",
                     n_weeks=len(j), first=d(j.index.min()), last=d(j.index.max()),
                     corr=j.fut_logret.corr(j.fut_logret_es), mean_abs_diff=diff.abs().mean(),
                     p99_abs_diff=diff.abs().quantile(.99), max_abs_diff=diff.abs().max(),
                     max_abs_diff_week=d(diff.abs().idxmax()),
                     same_contract_month_share=float((j.fut_contract.str[2:5] == j.fut_contract_es.str[2:5]).mean())))
    # manual checks of key roll periods
    checks = [("WTI", "2020-03-11", "2020-05-06", "WTI April 2020"), ("NATGAS", "2021-01-20", "2021-03-10", "NG Feb 2021 (Uri)"),
              ("NATGAS", "2025-12-17", "2026-02-11", "NG Jan 2026"), ("SP500", "2021-08-04", "2021-09-29", "SP to ES transition")]
    for mk, a, b, lab in checks:
        x = frames[mk]
        x = x[(x.target_wed >= a) & (x.target_wed <= b)]
        for _, r in x.iterrows():
            g1 = generics(r.fut_root).G1
            spl = np.log(g1.get(r.obs_date) / g1.get(r.prev_obs_date)) if pd.notna(r.obs_date) and pd.notna(r.prev_obs_date) and g1.get(r.obs_date, -1) > 0 and g1.get(r.prev_obs_date, -1) > 0 else np.nan
            summ.append(dict(record_type="manual_roll_check", market=mk, contract=r.fut_contract, check=lab,
                             target_wed=d(r.target_wed), obs_date=d(r.obs_date), prev_obs_date=d(r.prev_obs_date),
                             roll_at_interval_start=bool(r.roll_at_interval_start), generic_prev=r.fut_generic_prev,
                             generic_end=r.fut_generic, fut_price_prev=r.fut_price_prev, fut_price=r.fut_price,
                             matched_fut_logret=r.fut_logret, generic1_splice_logret=spl,
                             splice_minus_matched=(spl - r.fut_logret) if pd.notna(spl) and pd.notna(r.fut_logret) else np.nan,
                             spot_logret=r.spot_logret, alt_contract=r.alt_fut_contract, alt_fut_logret=r.alt_fut_logret))
    return pd.concat([pd.DataFrame(summ)] + parts, ignore_index=True)


# ----------------------------------------------------------------------------------------------
# PART 7: weekly validation summary
# ----------------------------------------------------------------------------------------------
def moments(x: pd.Series) -> dict:
    x = x.dropna()
    return dict(mean=x.mean(), median=x.median(), std=x.std(), skew=x.skew(), excess_kurt=x.kurt(), min=x.min(), max=x.max())


def weekly_summary(frames) -> pd.DataFrame:
    rows = []
    for k, df in frames.items():
        periods = [("full", df.target_wed >= df.target_wed.min())]
        if k in ("WTI", "GBPUSD", "SP500", "GOLD"):
            periods = [("original_1990_2023", df.target_wed <= C.ORIGINAL_END),
                       ("extension_2023_2026", df.target_wed > C.ORIGINAL_END)] + periods
        if k == "NATGAS":
            periods += [("bloomberg_spot_segment_1999_2007", df.spot_source == "BBG:NGUSHHUB"),
                        ("fred_spot_segment_2007_2026", df.spot_source == "FRED:DHHNGSP")]
        for pname, mask in periods:
            x = df[mask]
            y = x[x.return_defined]
            bc = y.spot_logret - y.fut_logret
            bl = np.log(y.spot_price / y.fut_price)
            sm, fm = moments(y.spot_logret), moments(y.fut_logret)
            hd = y.holding_days.value_counts().to_dict()
            rec = dict(market=k, period=pname, first_target=d(x.target_wed.min()), last_target=d(x.target_wed.max()),
                       first_return=d(y.target_wed.min()), last_return=d(y.target_wed.max()),
                       target_weeks=len(x), weekly_returns=len(y), strict_wednesday_returns=int(y.strict_wednesday.sum()),
                       returns_with_displaced_date=int((~y.strict_wednesday).sum()),
                       weeks_without_observation=int(x.obs_date.isna().sum()),
                       excluded_or_flagged=int((~x.return_defined).sum()) - (1 if pname in ("full", "original_1990_2023") else 0),
                       nonpositive_price_weeks=int(x.nonpositive_price.sum()),
                       holding_5_6d=hd.get(5, 0) + hd.get(6, 0), holding_7d=hd.get(7, 0), holding_8_9d=hd.get(8, 0) + hd.get(9, 0),
                       roll_intervals=int(y.roll_at_interval_start.sum()),
                       spot_sources=" ".join(sorted(y.spot_source.unique())))
            rec.update({f"spot_{a}": b for a, b in sm.items()})
            rec.update({f"fut_{a}": b for a, b in fm.items()})
            if len(y):
                rec.update(spot_min_week=d(y.loc[y.spot_logret.idxmin(), "target_wed"]),
                           spot_max_week=d(y.loc[y.spot_logret.idxmax(), "target_wed"]),
                           fut_min_week=d(y.loc[y.fut_logret.idxmin(), "target_wed"]),
                           fut_max_week=d(y.loc[y.fut_logret.idxmax(), "target_wed"]))
            rec.update(corr_spot_fut=y.spot_logret.corr(y.fut_logret),
                       basis_change_mean=bc.mean(), basis_change_std=bc.std(), basis_change_min=bc.min(), basis_change_max=bc.max(),
                       basis_change_abs_gt_10pct=int((bc.abs() > 0.10).sum()),
                       basis_level_mean=bl.mean(), basis_level_std=bl.std(),
                       corr_spot_alt_roll_fut=y.spot_logret.corr(y.alt_fut_logret),
                       alt_roll_rule=C.MARKETS[k].roll_alt)
            if "spot_alt_logret" in y and y.spot_alt_logret.notna().any():
                rec.update(spot_alt_source=y.spot_alt_source.dropna().iloc[0],
                           corr_spot_alt_fut=y.spot_alt_logret.corr(y.fut_logret),
                           corr_spot_vs_spot_alt=y.spot_logret.corr(y.spot_alt_logret),
                           spot_alt_std=y.spot_alt_logret.std())
            # generic-splice diagnostic (G1 at both ends regardless of contract identity)
            spl = []
            for _, r in y.iterrows():
                g1 = generics(r.fut_root).G1
                a, b = g1.get(r.obs_date, np.nan), g1.get(r.prev_obs_date, np.nan)
                spl.append(np.log(a / b) if a > 0 and b > 0 else np.nan)
            spl = pd.Series(spl, index=y.index, dtype=float) / 1.0
            sp_m = moments(spl)
            rec.update({f"diag_generic_splice_fut_{a}": b for a, b in sp_m.items()})
            rec["diag_generic_splice_corr_with_spot"] = y.spot_logret.corr(spl)
            if pname == "original_1990_2023" and (k, "spot") in PAPER_T2:
                for leg in ("spot", "fut"):
                    for a, b in PAPER_T2[(k, leg)].items():
                        rec[f"paper_T2_{leg}_{a}"] = b
                rec["paper_T2_reading"] = PAPER_RELIABILITY[k]
                rec["paper_T2_kurtosis_note"] = "paper reports 'kurtosis'; text says excess kurtosis; compare with both"
            rows.append(rec)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------
def main():
    frames, excl_log = build_all()
    weekly = pd.concat([frames[k].reindex(columns=WEEKLY_COLUMNS) for k in frames], ignore_index=True)
    for c in ("target_wed", "obs_date", "prev_obs_date", "fut_contract_month", "fut_ltd", "roll_trigger"):
        weekly[c] = pd.to_datetime(weekly[c]).dt.strftime("%Y-%m-%d")
    write(weekly, PROC / "weekly_market_returns.csv", full_precision=True)

    # complete exclusion log straight from the rule list, whether or not a weekly interval touched the date
    used = {(x["series"].split(" ")[0], x["date"]) for x in excl_log}
    rows = []
    for ex in C.EXCLUSIONS:
        s_ = io.read_series(ex.rel, "PX_LAST" if "bloomberg" in ex.rel else None)
        sel = s_[(s_.index >= ex.start) & (s_.index <= ex.end)].dropna()
        for dt, v in sel.items():
            rows.append(dict(record_type="observation_excluded", series=ex.rel, date=d(dt), raw_value=v,
                             reason=ex.reason, evidence=ex.evidence,
                             would_otherwise_have_been_looked_up=(ex.rel, d(dt)) in used
                             or (f"bloomberg/{ex.rel.split('/')[-1].split('_')[0]}", d(dt)) in used))
    log = pd.DataFrame(rows)
    flagged = weekly[weekly.exclusion_reason != ""][["market", "target_wed", "exclusion_reason", "reason_obs_missing"]].copy()
    flagged.insert(0, "record_type", "weekly_interval_not_defined")
    subs = pd.DataFrame([
        dict(record_type="source_substitution", market="GOLD", reason="LBMA PM (GOLDLNPM) file is empty; Bloomberg XAU spot used"),
        dict(record_type="source_substitution", market="GBPUSD", reason="paper used WM/Reuters via Eikon; Bloomberg GBPUSD used"),
        dict(record_type="source_substitution", market="WTI", reason="FRED/EIA DCOILWTICO used as spot; USCRWTIC rejected (futures-based)"),
        dict(record_type="source_substitution", market="NATGAS", reason="composite Henry Hub: Bloomberg NGUSHHUB for intervals starting before 2007-04-01, FRED/EIA DHHNGSP after"),
        dict(record_type="source_substitution", market="SP500", reason="SP (big) contracts through SPU21; ES (E-mini) from ESZ21"),
        dict(record_type="unit_normalisation", market="GBPUSD", reason="BP futures divided by 100 (US cents to USD)"),
    ])
    write(pd.concat([log, flagged, subs], ignore_index=True), PROC / "processed_data_log.csv", full_precision=True)

    write(wti_missing(frames["WTI"]), RES / "wti_missing_data_analysis.csv")
    write(april2020(frames["WTI"]), RES / "wti_april2020_review.csv")
    var = ng_variants()
    write(ng_source(frames["NATGAS"], var), RES / "natural_gas_source_comparison.csv")
    write(ng_stress(frames["NATGAS"], var), RES / "natural_gas_stress_events.csv")
    write(roll_validation(frames), RES / "roll_mapping_validation.csv")
    write(weekly_summary(frames), RES / "weekly_validation_summary.csv")

    after = io.hash_tree()
    same = after == HASH_BEFORE
    with open(RES / "stage1b_run_log.txt", "w") as f:
        f.write(f"python={sys.version.split()[0]} pandas={pd.__version__} numpy={np.__version__}\n")
        f.write(f"raw_files_hashed={len(HASH_BEFORE)} raw_files_unchanged_after_run={same}\n")
        for k, df in frames.items():
            f.write(f"{k}: target_weeks={len(df)} defined_returns={int(df.return_defined.sum())}\n")
    print("raw files unchanged:", same)
    if not same:
        raise SystemExit("RAW DATA CHANGED - investigate immediately")


if __name__ == "__main__":
    main()
