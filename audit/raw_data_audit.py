"""
FRE 6123 - Stage 1: Raw Data Integrity Audit (read-only).

Reads every file under data/raw/, never writes there, and produces:
    audit/results/raw_data_inventory.csv
    audit/results/data_quality_summary.csv
    audit/results/manifest_comparison.csv
    audit/results/anomaly_register.csv
    audit/results/supporting/*.csv          (evidence tables)
    audit/results/run_log.txt               (environment + read-only hash check)

Scope guard: this script does NOT build weekly returns, does NOT map generics to
contracts and does NOT apply roll rules. Daily log changes are computed only as a
screening diagnostic for anomalies.

Run from the project root:
    audit/.venv/Scripts/python.exe -I audit/raw_data_audit.py
"""
from __future__ import annotations

import hashlib
import platform
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "audit" / "results"
SUP = OUT / "supporting"
OUT.mkdir(parents=True, exist_ok=True)
SUP.mkdir(parents=True, exist_ok=True)

AUDIT_END = pd.Timestamp("2026-11-09")       # pull date in manifest
FIRST_WED = pd.Timestamp("1990-01-03")
LAST_WED = pd.Timestamp("2026-11-04")
PAPER_END = pd.Timestamp("2023-06-28")
Z_THRESHOLD = 10.0                           # robust z-score screen

# --------------------------------------------------------------------------
# Series metadata (what each file is supposed to be)
# --------------------------------------------------------------------------
# key: (relative path, value column, source, identifier, market, role, category)
SERIES = {
    "DCOILWTICO": ("fred/DCOILWTICO.csv", "DCOILWTICO", "FRED (EIA)", "DCOILWTICO", "WTI", "spot (context: primary)", "price series"),
    "USCRWTIC":   ("bloomberg/USCRWTIC_Index.csv", "PX_LAST", "Bloomberg", "USCRWTIC Index", "WTI", "spot (candidate)", "price series"),
    "CL1":        ("bloomberg/CL1_Comdty.csv", "PX_LAST", "Bloomberg", "CL1 Comdty", "WTI", "futures generic 1", "price series"),
    "CL2":        ("bloomberg/CL2_Comdty.csv", "PX_LAST", "Bloomberg", "CL2 Comdty", "WTI", "futures generic 2", "price series"),
    "CL3":        ("bloomberg/CL3_Comdty.csv", "PX_LAST", "Bloomberg", "CL3 Comdty", "WTI", "futures generic 3", "price series"),
    "GBPUSD":     ("bloomberg/GBPUSD_Curncy.csv", "PX_LAST", "Bloomberg", "GBPUSD Curncy", "GBPUSD", "spot (primary)", "price series"),
    "BP1":        ("bloomberg/BP1_Curncy.csv", "PX_LAST", "Bloomberg", "BP1 Curncy", "GBPUSD", "futures generic 1", "price series"),
    "BP2":        ("bloomberg/BP2_Curncy.csv", "PX_LAST", "Bloomberg", "BP2 Curncy", "GBPUSD", "futures generic 2", "price series"),
    "BP3":        ("bloomberg/BP3_Curncy.csv", "PX_LAST", "Bloomberg", "BP3 Curncy", "GBPUSD", "futures generic 3", "price series"),
    "SPX":        ("bloomberg/SPX_Index.csv", "PX_LAST", "Bloomberg", "SPX Index", "SP500", "spot (primary, price index)", "price series"),
    "SP1":        ("bloomberg/SP1_Index.csv", "PX_LAST", "Bloomberg", "SP1 Index", "SP500", "futures generic 1 (big SP)", "price series"),
    "SP2":        ("bloomberg/SP2_Index.csv", "PX_LAST", "Bloomberg", "SP2 Index", "SP500", "futures generic 2 (big SP)", "price series"),
    "ES1":        ("bloomberg/ES1_Index.csv", "PX_LAST", "Bloomberg", "ES1 Index", "SP500", "futures generic 1 (E-mini)", "price series"),
    "ES2":        ("bloomberg/ES2_Index.csv", "PX_LAST", "Bloomberg", "ES2 Index", "SP500", "futures generic 2 (E-mini)", "price series"),
    "ES3":        ("bloomberg/ES3_Index.csv", "PX_LAST", "Bloomberg", "ES3 Index", "SP500", "futures generic 3 (E-mini)", "price series"),
    "XAU":        ("bloomberg/XAU_Curncy.csv", "PX_LAST", "Bloomberg", "XAU Curncy", "GOLD", "spot (substitute for LBMA PM)", "price series"),
    "GOLDLNPM":   ("bloomberg/GOLDLNPM_Index.csv", "PX_LAST", "Bloomberg", "GOLDLNPM Index", "GOLD", "spot (paper's LBMA PM)", "price series"),
    "GC1":        ("bloomberg/GC1_Comdty.csv", "PX_LAST", "Bloomberg", "GC1 Comdty", "GOLD", "futures generic 1", "price series"),
    "GC2":        ("bloomberg/GC2_Comdty.csv", "PX_LAST", "Bloomberg", "GC2 Comdty", "GOLD", "futures generic 2", "price series"),
    "GC3":        ("bloomberg/GC3_Comdty.csv", "PX_LAST", "Bloomberg", "GC3 Comdty", "GOLD", "futures generic 3", "price series"),
    "BRR":        ("bloomberg/BRR_Index.csv", "PX_LAST", "Bloomberg", "BRR Index", "BTC", "spot (primary, CME CF BRR)", "price series"),
    "XBTUSD":     ("bloomberg/XBTUSD_Curncy.csv", "PX_LAST", "Bloomberg", "XBTUSD Curncy", "BTC", "spot (backup)", "price series"),
    "BTC1":       ("bloomberg/BTC1_Curncy.csv", "PX_LAST", "Bloomberg", "BTC1 Curncy", "BTC", "futures generic 1", "price series"),
    "BTC2":       ("bloomberg/BTC2_Curncy.csv", "PX_LAST", "Bloomberg", "BTC2 Curncy", "BTC", "futures generic 2", "price series"),
    "BTC3":       ("bloomberg/BTC3_Curncy.csv", "PX_LAST", "Bloomberg", "BTC3 Curncy", "BTC", "futures generic 3", "price series"),
    "NGUSHHUB":   ("bloomberg/NGUSHHUB_Index.csv", "PX_LAST", "Bloomberg", "NGUSHHUB Index", "NATGAS", "spot (context: primary)", "price series"),
    "DHHNGSP":    ("fred/DHHNGSP.csv", "DHHNGSP", "FRED (EIA)", "DHHNGSP", "NATGAS", "spot (cross-check)", "price series"),
    "NG1":        ("bloomberg/NG1_Comdty.csv", "PX_LAST", "Bloomberg", "NG1 Comdty", "NATGAS", "futures generic 1", "price series"),
    "NG2":        ("bloomberg/NG2_Comdty.csv", "PX_LAST", "Bloomberg", "NG2 Comdty", "NATGAS", "futures generic 2", "price series"),
    "NG3":        ("bloomberg/NG3_Comdty.csv", "PX_LAST", "Bloomberg", "NG3 Comdty", "NATGAS", "futures generic 3", "price series"),
    "SOXX_PX":    ("bloomberg/SOXX_US_Equity.csv", "PX_LAST", "Bloomberg", "SOXX US Equity", "AI_LENS", "reference (optional marker)", "reference data"),
    "SOXX_TR":    ("bloomberg/SOXX_US_Equity.csv", "TOT_RETURN_INDEX_GROSS_DVDS", "Bloomberg", "SOXX US Equity", "AI_LENS", "reference (optional marker)", "reference data"),
    "CFNAI":      ("fred/CFNAI.csv", "CFNAI", "FRED (Chicago Fed)", "CFNAI", "MACRO", "regime indicator (monthly)", "macroeconomic series"),
    "USREC":      ("fred/USREC.csv", "USREC", "FRED (NBER-based)", "USREC", "MACRO", "recession indicator (monthly)", "macroeconomic series"),
}
CALENDARS = {
    "CL": ("bloomberg/CL_contracts.csv", "FGHJKMNQUVXZ"),
    "BP": ("bloomberg/BP_contracts.csv", "HMUZ"),
    "SP": ("bloomberg/SP_contracts.csv", "HMUZ"),
    "ES": ("bloomberg/ES_contracts.csv", "HMUZ"),
    "GC": ("bloomberg/GC_contracts.csv", "GJMQVZ"),
    "BTC": ("bloomberg/BTC_contracts.csv", "FGHJKMNQUVXZ"),
    "NG": ("bloomberg/NG_contracts.csv", "FGHJKMNQUVXZ"),
}
GENERIC_ROOT = {k: k.rstrip("123") for k in ["CL1", "CL2", "CL3", "BP1", "BP2", "BP3", "SP1", "SP2",
                                             "ES1", "ES2", "ES3", "GC1", "GC2", "GC3", "BTC1", "BTC2",
                                             "BTC3", "NG1", "NG2", "NG3"]}
# Series used to corroborate a daily move (independent source or other leg)
CORROBORATE = {
    "DCOILWTICO": ["CL1", "USCRWTIC"], "USCRWTIC": ["DCOILWTICO", "CL1"], "CL1": ["DCOILWTICO", "CL2"],
    "CL2": ["CL3", "CL1"], "CL3": ["CL2"],
    "GBPUSD": ["BP1"], "BP1": ["GBPUSD"], "BP2": ["GBPUSD"], "BP3": ["GBPUSD"],
    "SPX": ["ES1", "SP1"], "SP1": ["SPX"], "SP2": ["SPX"], "ES1": ["SPX"], "ES2": ["SPX"], "ES3": ["SPX"],
    "XAU": ["GC1"], "GC1": ["XAU"], "GC2": ["XAU"], "GC3": ["XAU"],
    "BRR": ["XBTUSD", "BTC1"], "XBTUSD": ["BRR"], "BTC1": ["BRR"], "BTC2": ["BRR"], "BTC3": ["BRR"],
    "NGUSHHUB": ["DHHNGSP", "NG1"], "DHHNGSP": ["NGUSHHUB", "NG1"], "NG1": ["NGUSHHUB", "NG2"],
    "NG2": ["NG3", "NG1"], "NG3": ["NG2"],
    "SOXX_PX": ["SOXX_TR"], "SOXX_TR": ["SOXX_PX"],
}
MONTHS = "FGHJKMNQUVXZ"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_tree() -> dict[str, str]:
    return {str(p.relative_to(RAW)).replace("\\", "/"): sha256(p)
            for p in sorted(RAW.rglob("*")) if p.is_file()}


def read_raw(rel: str) -> pd.DataFrame:
    """Read as strings so that nothing is silently coerced."""
    return pd.read_csv(RAW / rel, dtype=str, keep_default_na=False)


RAW_CACHE: dict[str, pd.DataFrame] = {}


def raw_frame(rel: str) -> pd.DataFrame:
    if rel not in RAW_CACHE:
        RAW_CACHE[rel] = read_raw(rel)
    return RAW_CACHE[rel]


def series(key: str, valid_only: bool = True) -> pd.Series:
    rel, col = SERIES[key][0], SERIES[key][1]
    d = raw_frame(rel)
    idx = pd.to_datetime(d["date"], errors="coerce") if "date" in d else pd.DatetimeIndex([])
    v = pd.to_numeric(d[col].replace({"": np.nan, ".": np.nan}), errors="coerce") if col in d else pd.Series(dtype=float)
    s = pd.Series(v.values, index=pd.DatetimeIndex(idx), name=key, dtype=float)
    return s.dropna() if valid_only else s


def logret(s: pd.Series) -> pd.Series:
    s = s[s > 0]
    return np.log(s).diff().dropna()


def robust_z(r: pd.Series, window: int = 250) -> pd.Series:
    mad = r.rolling(window, min_periods=60).apply(
        lambda x: np.median(np.abs(x - np.median(x))), raw=True).shift(1) * 1.4826
    return r / mad


def wednesdays(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(max(start, FIRST_WED), min(end, LAST_WED), freq="W-WED")


def load_calendar(root: str) -> pd.DataFrame:
    rel, _ = CALENDARS[root]
    c = read_raw(rel)
    c["LTD"] = pd.to_datetime(c["LAST_TRADEABLE_DT"], errors="coerce")
    c["FND"] = pd.to_datetime(c["FUT_NOTICE_FIRST"], errors="coerce")
    m = c["ticker"].str.extract(rf"^{root}([FGHJKMNQUVXZ])(\d{{1,2}}) ")
    c["mcode"], c["yy"] = m[0], m[1]
    return c


def fmt(x, nd=4):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    if isinstance(x, (pd.Timestamp, datetime)):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


# --------------------------------------------------------------------------
# 0. Read-only guard: hash before
# --------------------------------------------------------------------------
HASH_BEFORE = hash_tree()


# --------------------------------------------------------------------------
# 1. Inventory
# --------------------------------------------------------------------------
def classify_file(rel: str) -> tuple[str, str, str]:
    name = Path(rel).name
    if name == "manifest.csv":
        return "reference data (pull manifest)", "Bloomberg pull script", "manifest"
    if name.endswith("_contracts.csv"):
        root = name.split("_")[0]
        return "contract calendar", "Bloomberg", f"{root} futures chain (LAST_TRADEABLE_DT, FUT_NOTICE_FIRST)"
    for k, meta in SERIES.items():
        if meta[0] == rel:
            return meta[6], meta[2], meta[3]
    return "unknown", "unknown", "unknown"


def inventory() -> pd.DataFrame:
    rows = []
    for p in sorted(RAW.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(RAW)).replace("\\", "/")
        cat, src, ident = classify_file(rel)
        d = read_raw(rel)
        base = dict(relative_path=f"data/raw/{rel}", source=src, identifier=ident, category=cat,
                    file_type=p.suffix.lstrip(".").upper(), size_bytes=p.stat().st_size,
                    sha256=HASH_BEFORE[rel], columns="|".join(d.columns), total_rows=len(d))
        if cat == "contract calendar":
            ltd = pd.to_datetime(d["LAST_TRADEABLE_DT"], errors="coerce")
            fnd = pd.to_datetime(d["FUT_NOTICE_FIRST"], errors="coerce")
            rows.append({**base, "value_column": "LAST_TRADEABLE_DT",
                         "dtypes": "ticker:str|LAST_TRADEABLE_DT:date|FUT_NOTICE_FIRST:date",
                         "earliest_valid": fmt(ltd.min()), "latest_valid": fmt(ltd.max()),
                         "valid_observations": int(ltd.notna().sum()),
                         "missing_or_blank": int((d["LAST_TRADEABLE_DT"] == "").sum() + (d["FUT_NOTICE_FIRST"] == "").sum()),
                         "non_numeric_or_unparseable": int(ltd.isna().sum() - (d["LAST_TRADEABLE_DT"] == "").sum() + fnd.isna().sum() - (d["FUT_NOTICE_FIRST"] == "").sum()),
                         "duplicate_keys": int(d["ticker"].duplicated().sum()),
                         "unsorted_keys": int((ltd.diff().dt.days < 0).sum()),
                         "nonpositive_values": "", "weekend_dates": int((ltd.dt.day_of_week >= 5).sum()),
                         "inferred_frequency": "one row per contract"})
            continue
        if cat.startswith("reference data (pull"):
            rows.append({**base, "value_column": "", "dtypes": "all str",
                         "earliest_valid": "", "latest_valid": "", "valid_observations": len(d),
                         "missing_or_blank": int((d == "").sum().sum()), "non_numeric_or_unparseable": "",
                         "duplicate_keys": int(d.duplicated(["ticker", "field"]).sum()), "unsorted_keys": "",
                         "nonpositive_values": "", "weekend_dates": "", "inferred_frequency": "one row per pulled series"})
            continue
        dt = pd.to_datetime(d["date"], errors="coerce") if "date" in d else pd.Series(dtype="datetime64[ns]")
        for col in [c for c in d.columns if c != "date"]:
            raw = d[col]
            blank = raw.isin(["", "."])
            v = pd.to_numeric(raw.where(~blank), errors="coerce")
            nonnum = int((~blank & v.isna()).sum())
            ok = v.notna() & dt.notna()
            vd = dt[ok]
            gaps = vd.diff().dt.days.dropna()
            if len(vd) < 2:
                freq = "empty" if len(vd) == 0 else "single"
            elif gaps.median() >= 28:
                freq = "monthly (first of month)"
            elif (vd.dt.day_of_week >= 5).mean() > 0.2:
                freq = "daily incl. weekends"
            elif (vd.dt.day_of_week >= 5).any():
                freq = "daily, partly incl. weekends"
            else:
                freq = "daily business days"
            nonpos = "" if cat == "macroeconomic series" else int((v[ok] <= 0).sum())
            rows.append({**base, "value_column": col, "dtypes": "date:date|" + f"{col}:float",
                         "earliest_valid": fmt(vd.min()) if len(vd) else "",
                         "latest_valid": fmt(vd.max()) if len(vd) else "",
                         "valid_observations": int(ok.sum()), "missing_or_blank": int(blank.sum()),
                         "non_numeric_or_unparseable": nonnum + int(dt.isna().sum()),
                         "duplicate_keys": int(dt.duplicated().sum()),
                         "unsorted_keys": int((dt.diff().dt.days <= 0).sum()),
                         "nonpositive_values": nonpos,
                         "weekend_dates": int((dt.dt.day_of_week >= 5).sum()),
                         "inferred_frequency": freq})
    cols = ["relative_path", "source", "identifier", "value_column", "category", "file_type", "size_bytes",
            "sha256", "columns", "dtypes", "inferred_frequency", "earliest_valid", "latest_valid",
            "total_rows", "valid_observations", "missing_or_blank", "non_numeric_or_unparseable",
            "duplicate_keys", "unsorted_keys", "nonpositive_values", "weekend_dates"]
    return pd.DataFrame(rows)[cols]


# --------------------------------------------------------------------------
# 2. Wednesday coverage, gaps, stale runs, outliers
# --------------------------------------------------------------------------
def calendar_ltds(root: str) -> pd.DatetimeIndex:
    c = load_calendar(root)
    return pd.DatetimeIndex(c["LTD"].dropna().sort_values().unique())


def roll_adjacent(dates: pd.DatetimeIndex, index: pd.DatetimeIndex, ltds: pd.DatetimeIndex) -> np.ndarray:
    """True if date is the LTD itself or one of the first two trading days after an LTD."""
    flags = np.zeros(len(dates), dtype=bool)
    pos = {d: i for i, d in enumerate(index)}
    marks = set()
    for l in ltds:
        i = index.searchsorted(l, side="left")
        for k in range(i, min(i + 3, len(index))):
            if index[k] - l <= pd.Timedelta(days=7):
                marks.add(index[k])
    for j, d in enumerate(dates):
        flags[j] = d in marks
    return flags


POS_SERIES: dict[str, pd.Series] = {}


def outlier_screen() -> pd.DataFrame:
    rows = []
    rets = {k: logret(series(k)) for k in SERIES if SERIES[k][6] != "macroeconomic series" and len(series(k))}
    POS_SERIES.clear()
    POS_SERIES.update({k: series(k)[series(k) > 0] for k in rets})
    for k, r in rets.items():
        s = series(k)
        z = robust_z(r)
        top = set(r.abs().sort_values(ascending=False).head(3).index)
        cand = sorted(set(z[z.abs() > Z_THRESHOLD].index) | top)
        if not cand:
            continue
        cand = pd.DatetimeIndex(cand)
        radj = roll_adjacent(cand, s.index, calendar_ltds(GENERIC_ROOT[k])) if k in GENERIC_ROOT else np.zeros(len(cand), bool)
        for d, ra in zip(cand, radj):
            x = r[d]
            i = r.index.get_loc(d)
            nxt = r.iloc[i + 1] if i + 1 < len(r) else np.nan
            prev_date = s.index[s.index.get_loc(d) - 1]
            corr_txt, corr_ok = [], False
            # Same-interval comparison: the other series' log change from its last
            # price on/before prev_date to its price on date d (if it has one).
            for o in CORROBORATE.get(k, []):
                os_ = POS_SERIES.get(o)
                if os_ is None or d not in os_.index:
                    corr_txt.append(f"{o}:no-price-on-date")
                    continue
                base = os_.loc[:prev_date]
                if not len(base):
                    continue
                mv = float(np.log(os_[d] / base.iloc[-1]))
                corr_txt.append(f"{o}:{mv:+.3f}")
                if np.sign(mv) == np.sign(x) and abs(mv) >= 0.5 * abs(x):
                    corr_ok = True
            if ra:
                cls = "roll/expiry-adjacent generic discontinuity (expected; needs roll correction)"
            elif corr_ok:
                cls = "corroborated by another series (likely genuine move)"
            elif not np.isnan(nxt) and np.sign(nxt) == -np.sign(x) and abs(nxt) >= 0.7 * abs(x):
                cls = "uncorroborated spike-and-reversal (suspect print)"
            else:
                cls = "uncorroborated (needs review)"
            rows.append(dict(series=k, identifier=SERIES[k][3], market=SERIES[k][4], date=fmt(d),
                             prev_date=fmt(prev_date), prev_price=s[prev_date], price=s[d],
                             log_change=round(x, 4), robust_z=round(z.get(d, np.nan), 1),
                             next_day_log_change=round(nxt, 4) if not np.isnan(nxt) else "",
                             roll_adjacent=bool(ra), corroborating_moves=" ".join(corr_txt),
                             auto_classification=cls))
    return pd.DataFrame(rows)


def quality_summary(outl: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, wcov = [], []
    for k, meta in SERIES.items():
        s_all = series(k, valid_only=False)
        s = s_all.dropna()
        if meta[6] == "macroeconomic series":
            if len(s) == 0:
                continue
            months = pd.date_range(s.index.min(), s.index.max(), freq="MS")
            s90 = s.loc["1990":]
            rows.append(dict(key=k, identifier=meta[3], market=meta[4], role=meta[5], first_valid=fmt(s.index.min()),
                             last_valid=fmt(s.index.max()), valid_obs=len(s), blank_obs=int(s_all.isna().sum()),
                             nonpositive_prices="n/a", duplicate_dates=int(s_all.index.duplicated().sum()),
                             unsorted_dates=int((s_all.index.to_series().diff().dt.days <= 0).sum()),
                             wednesdays_in_span="n/a", wednesdays_missing="n/a", wednesdays_missing_share="n/a",
                             wednesdays_missing_to_jun2023="n/a",
                             max_gap_days=f"{int(len(months.difference(s.index)))} missing months",
                             max_gap_end="", stale_days="n/a", max_stale_run="", max_stale_run_start="",
                             outliers_z_gt10="", outliers_roll_adjacent="", outliers_corroborated="",
                             outliers_suspect="", largest_abs_log_change="", largest_abs_log_change_date="",
                             notes=(f"min since 1990 {s90.min():.2f} ({fmt(s90.idxmin())}); max {s90.max():.2f} ({fmt(s90.idxmax())}); share<0 {(s90 < 0).mean():.3f}"
                                    if k == "CFNAI" else
                                    "recession months since 1990: " + ", ".join(
                                        f"{fmt(a)}..{fmt(b)}" for a, b in _episodes(s90)))))
            continue
        if len(s) == 0:
            rows.append(dict(key=k, identifier=meta[3], market=meta[4], role=meta[5], valid_obs=0,
                             notes="EMPTY FILE: header only, no observations"))
            continue
        w = wednesdays(s.index.min(), s.index.max())
        miss = w.difference(s.index)
        w23 = w[w <= PAPER_END]
        gaps = s.index.to_series().diff().dt.days
        same = s.diff() == 0
        grp = (~same).cumsum()
        runs = same.groupby(grp).sum()
        run_len = int(runs.max()) if len(runs) else 0
        run_start = s.index[grp == runs.idxmax()][0] if run_len else None
        r = logret(s)
        o = outl[outl.series == k] if len(outl) else outl
        o10 = o[o.robust_z.abs() > Z_THRESHOLD] if len(o) else o
        rows.append(dict(key=k, identifier=meta[3], market=meta[4], role=meta[5],
                         first_valid=fmt(s.index.min()), last_valid=fmt(s.index.max()), valid_obs=len(s),
                         blank_obs=int(s_all.isna().sum()), nonpositive_prices=int((s <= 0).sum()),
                         duplicate_dates=int(s_all.index.duplicated().sum()),
                         unsorted_dates=int((s_all.index.to_series().diff().dt.days <= 0).sum()),
                         wednesdays_in_span=len(w), wednesdays_missing=len(miss),
                         wednesdays_missing_share=round(len(miss) / max(len(w), 1), 4),
                         wednesdays_missing_to_jun2023=len(w23.difference(s.index)) if len(w23) else "",
                         max_gap_days=int(gaps.max()) if len(gaps.dropna()) else "",
                         max_gap_end=fmt(gaps.idxmax()) if len(gaps.dropna()) else "",
                         stale_days=int(same.sum()), max_stale_run=run_len + 1 if run_len else 1,
                         max_stale_run_start=fmt(run_start) if run_start is not None else "",
                         outliers_z_gt10=len(o10),
                         outliers_roll_adjacent=int(o10.roll_adjacent.sum()) if len(o10) else 0,
                         outliers_corroborated=int(o10.auto_classification.str.startswith("corroborated").sum()) if len(o10) else 0,
                         outliers_suspect=int(o10.auto_classification.str.contains("suspect|needs review").sum()) if len(o10) else 0,
                         largest_abs_log_change=round(r.abs().max(), 4) if len(r) else "",
                         largest_abs_log_change_date=fmt(r.abs().idxmax()) if len(r) else "",
                         notes=""))
        wcov.append(dict(key=k, identifier=meta[3], first_wednesday=fmt(w.min()) if len(w) else "",
                         last_wednesday=fmt(w.max()) if len(w) else "", wednesdays_in_span=len(w),
                         missing=len(miss), missing_share=round(len(miss) / max(len(w), 1), 4),
                         missing_dates=";".join(fmt(d) for d in miss)))
    return pd.DataFrame(rows), pd.DataFrame(wcov)


def _episodes(s: pd.Series):
    on = s == 1
    starts = s.index[on & ~on.shift(1, fill_value=False)]
    ends = s.index[on & ~on.shift(-1, fill_value=False)]
    return list(zip(starts, ends))


# --------------------------------------------------------------------------
# 3. Cross-source comparison (levels, same-date pairs)
# --------------------------------------------------------------------------
PAIRS = [
    ("WTI", "DCOILWTICO", "CL1", 1.0, "FRED spot vs front futures"),
    ("WTI", "USCRWTIC", "CL1", 1.0, "Bloomberg 'spot' vs front futures"),
    ("WTI", "USCRWTIC", "DCOILWTICO", 1.0, "Bloomberg vs FRED spot"),
    ("GBPUSD", "BP1", "GBPUSD", 1.0, "futures (raw quote) vs spot"),
    ("GBPUSD", "BP1", "GBPUSD", 0.01, "futures /100 vs spot"),
    ("SP500", "SP1", "SPX", 1.0, "big SP vs index"),
    ("SP500", "ES1", "SPX", 1.0, "E-mini vs index"),
    ("SP500", "SP1", "ES1", 1.0, "big SP vs E-mini"),
    ("SP500", "SP2", "ES2", 1.0, "big SP2 vs E-mini 2"),
    ("GOLD", "GC1", "XAU", 1.0, "COMEX front vs XAU spot"),
    ("BTC", "BTC1", "BRR", 1.0, "CME front vs BRR"),
    ("BTC", "XBTUSD", "BRR", 1.0, "XBTUSD vs BRR"),
    ("NATGAS", "NG1", "NGUSHHUB", 1.0, "NYMEX front vs Bloomberg Henry Hub"),
    ("NATGAS", "DHHNGSP", "NGUSHHUB", 1.0, "FRED vs Bloomberg Henry Hub"),
]


def cross_source() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, yearly = [], []
    for mkt, a, b, sc, desc in PAIRS:
        j = pd.concat([series(a) * sc, series(b)], axis=1, join="inner").dropna()
        j = j[(j.iloc[:, 0] > 0) & (j.iloc[:, 1] > 0)]
        ratio = j.iloc[:, 0] / j.iloc[:, 1]
        lr = np.log(ratio)
        eq = (j.iloc[:, 0].round(6) == j.iloc[:, 1].round(6))
        pre, post = ratio.loc[:"2023-12-31"], ratio.loc["2024-01-01":]
        rows.append(dict(market=mkt, series_a=a, series_b=b, scale_applied_to_a=sc, description=desc,
                         overlap_days=len(j), first_overlap=fmt(j.index.min()), last_overlap=fmt(j.index.max()),
                         median_ratio=round(ratio.median(), 4), p01_ratio=round(ratio.quantile(.01), 4),
                         p99_ratio=round(ratio.quantile(.99), 4),
                         median_ratio_to_2023=round(pre.median(), 4) if len(pre) else "",
                         median_ratio_2024_on=round(post.median(), 4) if len(post) else "",
                         share_exactly_equal=round(eq.mean(), 4),
                         max_abs_log_diff=round(lr.abs().max(), 4), date_of_max=fmt(lr.abs().idxmax())))
        for y, v in ratio.groupby(ratio.index.year).median().items():
            yearly.append(dict(pair=f"{a}{'/100' if sc == 0.01 else ''} vs {b}", year=y, median_ratio=round(v, 4),
                               share_exactly_equal=round(eq[eq.index.year == y].mean(), 4)))
    return pd.DataFrame(rows), pd.DataFrame(yearly)


# --------------------------------------------------------------------------
# 4. Contract calendars and generic roll-cycle test
# --------------------------------------------------------------------------
def calendar_checks() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, roll = [], []
    gen = {"CL": ("CL1", "CL2"), "BP": ("BP1", "BP2"), "SP": ("SP1", "SP2"), "ES": ("ES1", "ES2"),
           "GC": ("GC1", "GC2"), "BTC": ("BTC1", "BTC2"), "NG": ("NG1", "NG2")}
    for root, (rel, cycle) in CALENDARS.items():
        c = load_calendar(root)
        shared = c.groupby("LTD").size()
        max_shared = int(shared.max())
        shared_date = shared.idxmax() if max_shared > 1 else None
        listed = c["mcode"].value_counts().reindex(list(MONTHS)).fillna(0).astype(int)
        off_cycle = c[~c["mcode"].isin(list(cycle))]
        off_years = sorted(set(c.loc[off_cycle.index, "LTD"].dt.year)) if len(off_cycle) else []
        cyc = c[c["mcode"].isin(list(cycle))]
        cy_years = cyc.groupby(cyc["LTD"].dt.year).size()
        per_year = len(cycle)
        span = range(max(1990, cyc["LTD"].dt.year.min() + 1), min(2026, cyc["LTD"].dt.year.max()) + 1)
        short_years = [y for y in span if cy_years.get(y, 0) < per_year]
        notes = []
        if max_shared > 1:
            notes.append(f"{max_shared} contracts share LTD {fmt(shared_date)}: "
                         + ",".join(c.loc[c.LTD == shared_date, "ticker"].str.split().str[0]))
        single = c["yy"].str.len().eq(1).sum()
        rows.append(dict(root=root, file=f"data/raw/{rel}", contracts=len(c),
                         unparseable_tickers=int(c["mcode"].isna().sum()),
                         duplicate_tickers=int(c["ticker"].duplicated().sum()),
                         max_contracts_sharing_one_LTD=max_shared,
                         single_digit_year_tickers=int(single),
                         first_LTD=fmt(c["LTD"].min()), last_LTD=fmt(c["LTD"].max()),
                         months_listed=" ".join(f"{m}:{n}" for m, n in listed.items() if n),
                         generic_cycle_assumed=cycle,
                         off_cycle_contracts=len(off_cycle),
                         off_cycle_years=(f"{off_years[0]}-{off_years[-1]}" if off_years else ""),
                         cycle_years_with_fewer_than_expected=" ".join(map(str, short_years)),
                         median_FND_minus_LTD_days=float((c["FND"] - c["LTD"]).dt.days.median()),
                         notes="; ".join(notes)))
        # Roll-cycle test: does log(G2/G1) jump within 3 trading days after each LTD?
        g1, g2 = gen[root]
        sp = np.log(series(g2) / series(g1)).dropna()
        d = sp.diff().abs()
        med = d.median()
        # Primary spec: jump > 8x median on the first trading day after LTD.
        # Robustness spec: jump > 5x median within the first 3 trading days (looser,
        # picks up month-end first-notice noise, so off-cycle shares are higher).
        for label, sub in [("cycle months", cyc), ("off-cycle months", off_cycle)]:
            hits_a = hits_b = n = 0
            for l in sub["LTD"].dropna():
                if l < sp.index.min() or l >= sp.index.max():
                    continue
                after = d.index[d.index > l][:3]
                if len(after) == 0:
                    continue
                n += 1
                hits_a += int(d.loc[after[0]] > 8 * med)
                hits_b += int(d.loc[after].max() > 5 * med)
            roll.append(dict(root=root, generic_pair=f"{g1}/{g2}", month_group=label,
                             months=cycle if label == "cycle months" else "".join(sorted(set(MONTHS) - set(cycle))),
                             LTD_events_tested=n,
                             share_jump_next_day_8x=round(hits_a / n, 3) if n else "",
                             share_jump_within_3d_5x=round(hits_b / n, 3) if n else "",
                             median_daily_abs_spread_change=float(med),
                             interpretation=""))
    roll = pd.DataFrame(roll)
    for root in roll.root.unique():
        sub = roll[roll.root == root]
        c_ = sub[sub.month_group == "cycle months"].share_jump_next_day_8x.iloc[0]
        o_ = sub[sub.month_group == "off-cycle months"]
        if len(o_) and o_.LTD_events_tested.iloc[0]:
            o_v = o_.share_jump_next_day_8x.iloc[0]
            txt = ("generics follow the assumed cycle (strong separation on primary spec)" if c_ - o_v > 0.5
                   else "weak separation; inconclusive")
        else:
            txt = "all listed months are in the cycle; test only shows roll signal strength"
        roll.loc[roll.root == root, "interpretation"] = txt
    return pd.DataFrame(rows), roll


# --------------------------------------------------------------------------
# 5. Manifest comparison
# --------------------------------------------------------------------------
def manifest_comparison(inv: pd.DataFrame) -> pd.DataFrame:
    man = read_raw("manifest.csv")
    rows, matched = [], set()
    for _, m in man.iterrows():
        t, f = m["ticker"], m["field"]
        if t.endswith("_contracts"):
            rel = f"bloomberg/{t}.csv"
            col = "LAST_TRADEABLE_DT"
        elif t in ("CFNAI", "USREC", "DHHNGSP", "DCOILWTICO"):
            rel, col = f"fred/{t}.csv", t
        else:
            rel, col = f"bloomberg/{t.replace(' ', '_')}.csv", f
        path = f"data/raw/{rel}"
        exists = (RAW / rel).exists()
        r = inv[(inv.relative_path == path) & (inv.value_column == col)] if exists else inv.iloc[0:0]
        matched.add(path)
        if len(r):
            r = r.iloc[0]
            a_first, a_last = r.earliest_valid, r.latest_valid
            a_rows, a_valid = int(r.total_rows), int(r.valid_observations)
        else:
            a_first = a_last = ""
            a_rows = a_valid = 0
        m_rows = int(m["rows"]) if m["rows"] != "" else None
        issues = []
        if not exists:
            issues.append("file missing")
        if m["first_date"] != a_first:
            issues.append(f"first_date manifest={m['first_date'] or 'blank'} actual={a_first or 'none'}")
        if m["last_date"] != a_last:
            issues.append(f"last_date manifest={m['last_date'] or 'blank'} actual={a_last or 'none'}")
        if m_rows is not None and m_rows != a_rows:
            issues.append(f"rows manifest={m_rows} actual_total={a_rows}")
        if a_rows != a_valid:
            issues.append(f"manifest rows count blanks: total={a_rows}, valid={a_valid}")
        completeness = ""
        if exists and a_valid == 0:
            completeness = "EMPTY"
        elif "expected" in m["notes"]:
            completeness = "INCOMPLETE vs expected start (per manifest note)"
        elif t in ("SP1 Index", "SP2 Index"):
            completeness = "ends 2021-09-17 (contract delisted; genuine)"
        elif a_last and pd.Timestamp(a_last) < pd.Timestamp("2026-11-06") and t not in ("CFNAI", "USREC"):
            completeness = f"ends {a_last}, before Bloomberg pull end"
        rows.append(dict(manifest_ticker=t, manifest_field=f, expected_file=path, file_exists=exists,
                         manifest_first=m["first_date"], actual_first=a_first,
                         manifest_last=m["last_date"], actual_last=a_last,
                         manifest_rows=m_rows, actual_total_rows=a_rows, actual_valid_obs=a_valid,
                         metadata_match=("yes" if not [i for i in issues if not i.startswith("manifest rows count blanks")] else "no"),
                         discrepancies="; ".join(issues), completeness=completeness,
                         manifest_notes=m["notes"]))
    # Files on disk not in manifest
    for p in sorted(inv.relative_path.unique()):
        if p not in matched and not p.endswith("manifest.csv"):
            rows.append(dict(manifest_ticker="(not in manifest)", expected_file=p, file_exists=True,
                             metadata_match="n/a", discrepancies="unexpected file: present on disk, absent from manifest"))
    # Files claimed by the project context but absent
    for p in ["data/raw/eia/RWTCd.xls", "data/raw/eia/RNGWHHDd.xls", "data/raw/eia/RWTC.csv", "data/raw/eia/RNGWHHD.csv"]:
        if not (ROOT / p).exists():
            rows.append(dict(manifest_ticker="(context doc section 5)", expected_file=p, file_exists=False,
                             metadata_match="n/a",
                             discrepancies="claimed by FRE6123_Project_Context.md but absent from data/raw (not in manifest either)"))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 6. Anomaly register (curated; every number recomputed from the raw files)
# --------------------------------------------------------------------------
def anomaly_register(qs: pd.DataFrame, xs: pd.DataFrame, cal: pd.DataFrame, roll: pd.DataFrame) -> pd.DataFrame:
    S = {k: series(k) for k in SERIES}
    S_all = {k: series(k, valid_only=False) for k in ["DCOILWTICO", "DHHNGSP"]}
    q = qs.set_index("key")
    x = xs.set_index(["series_a", "series_b", "scale_applied_to_a"])
    A = []

    def add(market, series_, start, end, category, finding, evidence, classification, why, risk, action, verify, severity):
        A.append(dict(id=f"A{len(A) + 1:02d}", market=market, series=series_, date_start=start, date_end=end,
                      category=category, finding=finding, evidence=evidence, classification=classification,
                      severity=severity, why_it_matters=why, risk_if_ignored=risk,
                      recommended_action=action, verification=verify))

    def v(k, d):
        d = pd.Timestamp(d)
        return S[k].get(d, np.nan)

    # --- WTI ---------------------------------------------------------------
    add("WTI", "DCOILWTICO; CL1; USCRWTIC", "2020-04-20", "2020-04-21", "nonpositive price",
        "Negative WTI prints on 2020-04-20 in three series (not one, as the context doc states).",
        f"DCOILWTICO {v('DCOILWTICO','2020-04-20'):.2f}; CL1 {v('CL1','2020-04-20'):.2f}; USCRWTIC {v('USCRWTIC','2020-04-20'):.2f}. "
        f"Wednesday 2020-04-22 is positive in all (FRED {v('DCOILWTICO','2020-04-22'):.2f}, CL1 {v('CL1','2020-04-22'):.2f}).",
        "potentially genuine market event (corroborated by 3 series; May-2020 contract expiry and storage squeeze)",
        "Log returns are undefined for prices <= 0; the hedged-return distribution around this week drives the WTI 1% tail.",
        "A fallback day rule that reaches back to Mon/Tue, or any daily-frequency step, would crash or silently drop the week; "
        "holding the expiring May contract into expiry would create an artificial futures loss.",
        "Keep the print in raw data; never take logs of nonpositive prices; make Stage-2 sampling assert price>0; "
        "ensure the roll rule has left CLK20 before 2020-04-20.",
        "Unit test: every price entering a log is >0; print the weekly rows 2020-04-08..2020-05-06 for review.", "high")
    a = q.loc["DCOILWTICO"]
    add("WTI", "DCOILWTICO", "1986-01-02", "2026-11-03", "missing-data cluster",
        "FRED WTI spot is blank on many trading days, concentrated in 1994-2006.",
        f"{int(a.blank_obs)} blank rows; {int(a.wednesdays_missing)} of {int(a.wednesdays_in_span)} Wednesdays missing "
        f"({a.wednesdays_missing_share:.1%}); {int(a.wednesdays_missing_to_jun2023)} missing to Jun-2023; "
        f"CL1 traded on {len(S_all['DCOILWTICO'][S_all['DCOILWTICO'].isna()].index.intersection(S['CL1'].index))} of the blank days. "
        "Context doc reports 99.0% weekly spot coverage (19 missing weeks).",
        "unresolved (cannot tell from the file whether the gaps exist at FRED/EIA or arose in the pull; live re-download blocked in this environment)",
        "Every missing spot Wednesday removes a hedged-return observation or forces a substitute day; 1994-2006 is ~1/3 of the replication sample.",
        "Silent loss of ~8% of weeks, or a substitute-day rule applied far more often than assumed, which changes the sample relative to the paper (1,728 weeks).",
        "Re-download DCOILWTICO from FRED and RWTC from EIA and diff against this file before Stage 2; if gaps are real, apply a documented common-date fallback and report how many weeks use it.",
        "Diff report: count of dates where fresh download has a value and this file is blank (target 0).", "high")
    add("WTI", "DCOILWTICO vs CL1", "2024-01-01", "2026-11-03", "abrupt change / basis regime",
        "FRED spot sits persistently above CL1 from 2024 onward, peaking ~6% in Oct-2026; before 2024 the ratio is ~1.000 even in the steep 2022 backwardation.",
        f"median FRED/CL1 to 2023 = {x.loc[('DCOILWTICO','CL1',1.0)].median_ratio_to_2023}; 2024-on = {x.loc[('DCOILWTICO','CL1',1.0)].median_ratio_2024_on}; "
        f"2026-10-21 FRED {v('DCOILWTICO','2026-10-21'):.2f} vs CL1 {v('CL1','2026-10-21'):.2f}.",
        "unresolved (possible change in EIA/LSEG spot assessment method, or a genuine physical premium; not determinable from raw files)",
        "The H1 extension (2023-2026) depends on spot-futures basis; a level shift that varies over time adds basis noise, which favours estimated (OLS) hedges over naive.",
        "A source artifact could be misread as evidence that the naive hedge stops working after 2023.",
        "Check EIA notes for RWTC methodology changes; in Stage 2 report WTI results for 2023-2026 with FRED spot and, as sensitivity, with CL1-implied spot.",
        "Weekly basis volatility by year before/after 2024; result tables under both spot definitions.", "medium")
    add("WTI", "DCOILWTICO vs CL1", "2020-03-25", "2020-03-30", "large spot-futures divergence",
        "FRED spot printed 15-30% below CL1 for several days at end-March 2020, including Wednesday 2020-03-25.",
        f"2020-03-25 FRED {v('DCOILWTICO','2020-03-25'):.2f} vs CL1 {v('CL1','2020-03-25'):.2f}; "
        f"2020-03-30 FRED {v('DCOILWTICO','2020-03-30'):.2f} vs CL1 {v('CL1','2020-03-30'):.2f}; converges 2020-03-31.",
        "potentially genuine market event (physical Cushing dislocation during COVID storage crisis), but unconfirmed",
        "A single week of extreme basis sits in the March-2020 stress window and can dominate tail estimates for a 52-week window.",
        "If it is a reporting artifact, it inflates WTI basis risk and penalises the naive hedge in 2020-21.",
        "Keep; flag the week; run a sensitivity with the week excluded. The daily screen shows the whole 2020-03-19..2020-03-31 "
        "window has FRED moves not matched by CL1 (see supporting/daily_outlier_screen.csv).",
        "Compare HE with/without the flagged week in Stage 2/3.", "medium")
    a = x.loc[("USCRWTIC", "CL1", 1.0)]
    add("WTI", "USCRWTIC", "2017-01-23", "2026-11-06", "possible ticker substitution",
        "Bloomberg 'WTI Cushing spot' equals CL1 exactly on most days and starts only in 2017.",
        f"share exactly equal to CL1 = {a.share_exactly_equal:.1%}; median ratio {a.median_ratio}; differs mainly around CL1 roll dates.",
        "verified fact (exact equality); interpretation: series is front-month futures-based, not an independent physical spot",
        "Using it as spot would make spot and futures nearly the same series.",
        "Basis risk would be ~0 by construction, so every hedge looks near-perfect and the naive hedge wins trivially.",
        "Do not use USCRWTIC as the spot leg; keep it as a cross-check only.",
        "Reported equality share in cross_source_comparison.csv.", "medium")
    add("WTI", "DCOILWTICO", "2026-11-03", "2026-11-04", "coverage end",
        "FRED ends on Tuesday 2026-11-03; the last Wednesday with a FRED WTI price is 2026-10-28.",
        f"last valid {q.loc['DCOILWTICO'].last_valid}; context doc says last common Wednesday is 2026-11-04 (true only under a fallback-day rule).",
        "verified fact", "Defines the end of the WTI sample.", "Off-by-one week in sample end or a silent fallback.",
        "Decide sample end explicitly (2026-10-28 strict Wednesday, or 2026-11-04 with fallback).", "Assert last sample date in Stage 2.", "low")

    # --- GBPUSD ------------------------------------------------------------
    a, b = x.loc[("BP1", "GBPUSD", 1.0)], x.loc[("BP1", "GBPUSD", 0.01)]
    add("GBPUSD", "BP1-BP3", "1990-01-02", "2026-11-09", "quote units",
        "CME pound futures are quoted in US cents per pound; spot is in dollars.",
        f"median BP1/GBPUSD = {a.median_ratio} (p1 {a.p01_ratio}, p99 {a.p99_ratio}); after /100 median = {b.median_ratio}. "
        "Deviation from 1 has the sign implied by interest-rate parity (futures below spot when UK rates > US rates, e.g. 1990; above in 2000, 2006 and 2016-2025 when US rates were at or above UK rates; checked by eye).",
        "verified (unit convention); deviation pattern is a reasonable interpretation (carry)",
        "Log returns are unit-free, so the /100 matters for levels, basis, and any ratio-based check, not for returns.",
        "Basis computed in levels would be ~99 dollars, corrupting basis-risk splits.",
        "Divide BP1-3 by 100 in Stage 2 processing (never in raw files).", "Median processed ratio in [0.98, 1.02].", "medium")
    add("GBPUSD", "BP3; BP calendar", "1990-01-02", "2026-11-09", "calendar gaps / cycle",
        "BP3 has multi-week gaps (39 days to 1996-07-26, 30 days to 1990-04-18); the BP calendar lists serial months only from 2017, and generics skip them.",
        "roll test: " + "; ".join(f"{r.month_group} {r.share_jump_next_day_8x} (3d/5x: {r.share_jump_within_3d_5x})" for r in roll[roll.root == 'BP'].itertuples()),
        "potentially genuine (illiquid third contract); serial-month skipping verified statistically",
        "BP3 is needed only for contract mapping; mapping with serial months included would mis-identify contracts after 2017.",
        "Wrong contract identified at rolls => spurious futures returns.",
        "Filter BP calendar to H/M/U/Z before mapping; do not use BP3 levels in analysis.", "Stage 2 mapping test: implied roll dates match spread jumps.", "low")

    # --- S&P 500 -----------------------------------------------------------
    j = pd.concat([S["SP1"], S["ES1"]], axis=1, join="inner")
    eq = (j.iloc[:, 0] == j.iloc[:, 1])
    add("SP500", "SP1/SP2 vs ES1/ES2", "1997-09-09", "2021-09-17", "possible ticker substitution / settlement linkage",
        "Big-SP generics equal E-mini generics to the cent on many days, rising to ~98% in 2021Q2-Q3.",
        f"share SP1==ES1: 1997-2020 {eq.loc[:'2020'].mean():.1%}; 2021 {eq.loc['2021'].mean():.1%}. "
        f"Expiry handling differs: 2021-06-18 SP1 {v('SP1','2021-06-18')} = ES2 {v('ES2','2021-06-18')} while ES1 {v('ES1','2021-06-18')} (final settlement of expiring contract). "
        "SP calendar LTD is Thursday (2021-06-17), ES LTD Friday.",
        "verified equality; interpretation: CME settled SP off ES as SP liquidity disappeared (not a data error)",
        "The SP-to-ES switch point barely changes price levels, but the two generics roll on different days.",
        "A transition week computed as ln(ES1_t) - ln(SP1_t-1) mixes contracts and can create a spurious return.",
        "Switch SP->ES at a quarterly roll, computing the transition-week return within one contract family.",
        "Stage 2: transition-week futures return vs SPX return difference < 0.5%.", "medium")
    c = cal.set_index("root").loc["SP"]
    add("SP500", "SP_contracts.csv", "2021-09-17", "2021-09-17", "calendar metadata error",
        "The SP chain contains contracts that never traded to maturity: all carry LAST_TRADEABLE_DT = 2021-09-17 (delisting date) and several have single-digit-year tickers.",
        c.notes,
        "verified metadata issue (Bloomberg records delisting date as LTD)",
        "A mapping rule based on 'k-th unexpired contract by LTD' sees 12 contracts tied on one date in mid-2021.",
        "Generic-to-contract mapping becomes ambiguous for SP in Jun-Sep 2021.",
        "Exclude SP contracts with LTD 2021-09-17 from mapping; end SP usage at or before the SPU21 expiry.",
        "Mapping unit test over 2021-06..2021-09.", "medium")
    add("SP500", "ES3", "1997-12-18", "2007-09-30", "missing-data cluster",
        "ES3 is very sparse before late 2007.",
        f"ES3 Wednesdays missing {q.loc['ES3'].wednesdays_missing} ({q.loc['ES3'].wednesdays_missing_share:.1%}); max gap {q.loc['ES3'].max_gap_days} days ending {q.loc['ES3'].max_gap_end}.",
        "potentially genuine (third quarterly E-mini barely traded)", "ES3 is only needed to cover early-roll windows.",
        "Early-roll logic that needs ES3 would fail or use stale prices before 2007.",
        "Do not rely on ES3 before 2008; for the S&P a 'first day of contract month' roll needs only generic 2.",
        "Stage 2 check that no return uses an ES3 price before 2008.", "low")
    add("SP500", "SPX", "1990-01-02", "2026-11-09", "definition",
        "SPX is the price index (no dividends) while futures prices embed expected dividends.",
        f"median ES1/SPX {x.loc[('ES1','SPX',1.0)].median_ratio}; yearly medians 0.997-1.006 track rates minus dividend yield.",
        "verified definition; consistent with paper ('S&P 500 Composite')", "Carry creates a small predictable basis drift.",
        "Minor; a total-return spot would change the mean hedged return only.", "Keep SPX; document.", "n/a", "low")

    # --- Gold --------------------------------------------------------------
    add("GOLD", "GOLDLNPM", "", "", "missing series",
        "The LBMA Gold PM file used by the paper has a header and no observations.",
        "GOLDLNPM_Index.csv: 0 data rows (manifest rows=0).",
        "verified data gap", "The paper's spot is the London PM fix; XAU is a different fixing time and source.",
        "Undisclosed substitution of the paper's spot series; small timing basis differences vs COMEX settlement.",
        "Use XAU Curncy and state the deviation; if possible pull LBMA PM from another source for a 1990-2023 robustness check.",
        "Correlation of weekly XAU vs LBMA returns if obtained.", "medium")
    r = roll[roll.root == "GC"]
    add("GOLD", "GC1-GC3; GC calendar", "1990-01-02", "2026-11-09", "contract cycle",
        "The GC calendar lists all 12 months, but generics roll only through active months (G,J,M,Q,V,Z).",
        "roll test share of LTDs followed by G2/G1 spread jump: " + "; ".join(f"{t.month_group} {t.share_jump_next_day_8x} (3d/5x: {t.share_jump_within_3d_5x})" for t in r.itertuples()),
        "verified statistically (consistent with context doc claim)",
        "Mapping generics to contracts with all months included would mis-identify the held contract half the time.",
        "Spurious roll returns and wrong 'first day of contract month' roll dates.",
        "Filter GC calendar to active months before mapping.", "Stage 2 mapping test: implied rolls align with spread jumps.", "medium")
    add("GOLD", "GC1-3; XAU", "2026-01-30", "2026-01-30", "large move",
        "Gold fell ~9-11% in one day (XAU -9.0%, GC1 -11.4%).",
        f"GC1 {v('GC1','2026-01-29')} -> {v('GC1','2026-01-30')}; XAU {v('XAU','2026-01-29')} -> {v('XAU','2026-01-30')}.",
        "potentially genuine market event (corroborated by independent spot and all three generics)",
        "Largest daily gold move in the sample; inside the 2023-2026 extension window.",
        "Treating it as an outlier and removing it would understate gold tail risk.",
        "Keep; mention in the extension discussion.", "n/a", "low")
    add("GOLD", "XAU vs GC1", "1990-01-02", "2026-11-09", "close-time mismatch",
        "XAU (Bloomberg composite) and COMEX settlement are sampled at different times; on volatile days spot sits above the front future.",
        f"p1/p99 GC1/XAU {x.loc[('GC1','XAU',1.0)].p01_ratio}/{x.loc[('GC1','XAU',1.0)].p99_ratio}; 2026-01-28 XAU {v('XAU','2026-01-28')} vs GC1 {v('GC1','2026-01-28')}.",
        "reasonable interpretation (timing, not error)", "Timing differences show up as basis noise.",
        "Slightly understates hedge effectiveness for all models; affects naive and OLS similarly.", "Accept and disclose.", "n/a", "low")

    # --- Bitcoin -----------------------------------------------------------
    add("BTC", "BTC1-BTC3", "2017-12-15", "2017-12-15", "coverage start",
        "Futures generics have a price on Friday 2017-12-15, before CME bitcoin futures began trading (trade date 2017-12-18). The calendar's earliest contract is BTCF18.",
        f"BTC1 2017-12-15 {v('BTC1','2017-12-15')} vs BRR {v('BRR','2017-12-15')} (+{v('BTC1','2017-12-15')/v('BRR','2017-12-15')-1:.1%}).",
        "unresolved (pre-launch indicative or misdated print)", "Affects at most the first weekly return.",
        "A spurious first futures return in a 9-year sample.",
        "Start the BTC futures sample on the first Wednesday on/after 2017-12-18 (2017-12-20).", "Assert first futures date >= 2017-12-18.", "low")
    b_ = S["BRR"]
    wk = b_[b_.index.day_of_week >= 5].groupby(b_[b_.index.day_of_week >= 5].index.year).size()
    add("BTC", "BRR", "2022-01-01", "2025-12-31", "abrupt change in coverage",
        "BRR includes weekend values through 2022, almost none in 2023-2025, and some again in 2026.",
        "weekend rows per year: " + ", ".join(f"{y}:{n}" for y, n in wk.items()),
        "unresolved (likely pull/calendar artifact; BRR is published daily)",
        "No effect on Wednesday sampling (0 missing Wednesdays).", "Only matters if daily data are used.",
        "Ignore for weekly work; document.", "n/a", "low")
    a = x.loc[("BTC1", "BRR", 1.0)]
    add("BTC", "BRR vs XBTUSD; BTC1", "2018-01-17", "2018-01-17", "large uncorroborated move on a Wednesday",
        "BRR fell ~25% on Wednesday 2018-01-17 and recovered the next day, while XBTUSD and BTC1 moved little over the same interval.",
        f"BRR {v('BRR','2018-01-16')} -> {v('BRR','2018-01-17')} -> {v('BRR','2018-01-18')}; "
        f"XBTUSD {v('XBTUSD','2018-01-16')} -> {v('XBTUSD','2018-01-17')}; BTC1 {v('BTC1','2018-01-16')} -> {v('BTC1','2018-01-17')}.",
        "potentially genuine (BRR's 4pm-London fixing caught the intraday crash low of 17-Jan-2018; other series close hours later) but unresolved",
        "A single Wednesday spot print ~15% below futures sits in the first 52-week Bitcoin estimation window.",
        "Inflates estimated BTC basis risk and tail dependence in the first windows; makes Dec-2018+ hedge ratios depend on one timing artifact.",
        "Keep BRR as primary (it is the CME settlement reference) but run the BTC analysis with XBTUSD spot as sensitivity.",
        "Stage 2: list weekly BRR-vs-BTC1 basis outliers; compare hedge ratios under both spot series.", "medium")
    add("BTC", "BTC1 vs BRR", "2017-12-18", "2026-11-09", "close-time mismatch / basis noise",
        "Daily BTC1/BRR ratio has wide tails, e.g. 2019-06-26/27 when bitcoin crashed intraday.",
        f"p1/p99 {a.p01_ratio}/{a.p99_ratio}; 2019-06-26 BTC1 {v('BTC1','2019-06-26')} vs BRR {v('BRR','2019-06-26')}; 2019-06-27 BTC1 {v('BTC1','2019-06-27')} vs BRR {v('BRR','2019-06-27')}.",
        "reasonable interpretation: BRR fixes at 4pm London, CME settles ~4pm New York, so crashes between the two show up as basis",
        "This is a central H2 mechanism: measured basis risk partly reflects timing, not economics.",
        "Attributing timing basis to 'unstable spot-futures relation' over-states the H2 story.",
        "Keep; in Stage 2 compare weekly spot-futures correlation using BRR vs XBTUSD as a timing sensitivity.",
        "Correlation table with both spot series.", "medium")

    # --- Natural gas -------------------------------------------------------
    add("NATGAS", "NGUSHHUB", "2025-09-29", "2025-09-29", "bad print",
        "Bloomberg Henry Hub spot printed 0.2571 for one day.",
        f"NGUSHHUB {v('NGUSHHUB','2025-09-26')} -> {v('NGUSHHUB','2025-09-29')} -> {v('NGUSHHUB','2025-09-30')}; same day FRED {v('DHHNGSP','2025-09-29')}, NG1 {v('NG1','2025-09-29')}.",
        "verified data error (likely decimal shift; contradicted by FRED and futures)",
        "A Monday, so it does not enter strict Wednesday sampling, but would enter any daily statistic or fallback.",
        "A fake -240% / +250% log move in daily diagnostics or in a fallback week.",
        "Treat as missing in Stage-2 processing via an explicit, documented exclusion list (raw file untouched).",
        "Exclusion list applied; processed series has no |daily log change| > 1 without corroboration.", "medium")
    add("NATGAS", "NGUSHHUB vs DHHNGSP", "2021-02-15", "2021-02-18", "missing-data cluster in stress window",
        "Bloomberg Henry Hub has no prints during the peak of Winter Storm Uri, including Wednesday 2021-02-17; FRED has them.",
        f"FRED 02-16 {v('DHHNGSP','2021-02-16')}, 02-17 {v('DHHNGSP','2021-02-17')}, 02-18 {v('DHHNGSP','2021-02-18')}; NGUSHHUB last before = {v('NGUSHHUB','2021-02-12')} (02-12), next = {v('NGUSHHUB','2021-02-19')} (02-19).",
        "verified coverage gap (the spike itself is a genuine market event)",
        "Uri is one of the proposal's named stress windows; the peak is exactly a Wednesday.",
        "A fallback rule would use 02-12 (6.51) and the stress-window analysis would miss the 23.86 spike, understating spot tail risk and basis risk.",
        "Decision needed: (a) patch missing Bloomberg days with FRED values (median FRED/Bloomberg ratio ~1.000) under a documented rule, or (b) keep Bloomberg only and report Uri with FRED as a side analysis.",
        "Weekly Uri-window table under both options.", "high")
    add("NATGAS", "NGUSHHUB; DHHNGSP", "2024-01-12", "2026-01-28", "large spot spikes",
        "Henry Hub spot spikes in Jan-2024 and Jan-2026 while futures move little.",
        f"2024-01-12 Bloomberg {v('NGUSHHUB','2024-01-12')}, FRED {v('DHHNGSP','2024-01-12')}, NG1 {v('NG1','2024-01-12')}; "
        f"2026-01-23 Bloomberg {v('NGUSHHUB','2026-01-23')}, FRED {v('DHHNGSP','2026-01-23')}, NG1 {v('NG1','2026-01-23')}; "
        f"2026-01-26 Bloomberg {v('NGUSHHUB','2026-01-26')} vs FRED {v('DHHNGSP','2026-01-26')} (sources differ ~24%).",
        "potentially genuine market events (corroborated by two independent spot sources); size differs by source",
        "These are exactly the spot-only tail events that make a futures hedge (of any ratio) fail; they will dominate NG CVaR.",
        "Removing them would bias H2 towards the naive hedge; using one source without disclosure makes the NG tail source-dependent.",
        "Keep; report H2 NG tail results with the primary spot and, as sensitivity, the other source for affected weeks.",
        "Sensitivity table of NG 1%/99% CVaR HE under both spot sources.", "high")
    add("NATGAS", "NG1", "2026-01-28", "2026-01-29", "roll discontinuity",
        "NG1 has a one-day log change of -0.64 (price -47%) when the squeezed Feb-2026 contract expires and the generic rolls to March.",
        f"NG1 {v('NG1','2026-01-28')} -> {v('NG1','2026-01-29')}; NG2 {v('NG2','2026-01-28')} -> {v('NG2','2026-01-29')}.",
        "potentially genuine curve structure; the jump is a generic-roll artifact, not a return",
        "Shows how large NG roll gaps can be in winter.",
        "An uncorrected generic series would record a -64% 'futures return' and make futures look like a terrible hedge.",
        "Roll-correct in Stage 2 (same-contract returns only).", "No weekly futures return spans two contracts.", "high")
    al = hub_alignment()
    win = al[(al.month >= "2020-01") & (al.month <= "2021-04")]
    lag_months = int((win.closer_match == "FRED previous day").sum())
    cc = hub_futures_anchor()
    w2 = cc[cc.period == "2020-01..2021-04"].iloc[0]
    w1 = cc[cc.period == "2017-01..2019-12"].iloc[0]
    add("NATGAS", "NGUSHHUB vs DHHNGSP vs NG1", "2020-01-01", "2021-04-30", "date misalignment",
        "Bloomberg Henry Hub appears to be dated one trading day late from about Jan-2020 to Apr-2021: it matches FRED's previous-day value and moves with the previous day's futures.",
        f"months where Bloomberg(t) is closer to FRED(t-1) than to FRED(t): {lag_months} of {len(win)} in 2020-01..2021-04 "
        f"(in 2019 the two are identical: monthly median |log diff| 0.000). Daily-change correlation with NG1 in 2020-01..2021-04: "
        f"Bloomberg same-day {w2.hub_vs_ng1_same_day:.3f}, prev-day {w2.hub_vs_ng1_prev_day:.3f}; FRED same-day {w2.fred_vs_ng1_same_day:.3f}. "
        f"Control 2017-2019: Bloomberg same-day {w1.hub_vs_ng1_same_day:.3f}. Feb-2021: FRED jumps on 02-11 (6.50), Bloomberg on 02-12 (6.51).",
        "verified inconsistency between sources; attribution to a Bloomberg dating shift is strongly supported by the futures anchor (reasonable interpretation)",
        "Spot and futures must be observed on the same day for basis and hedged returns to be meaningful; this window contains COVID and Winter Storm Uri, both H2 stress windows.",
        "A one-day lag between spot and futures adds artificial basis noise for ~70 weeks, lowers measured hedge effectiveness for every model and is likely to favour OLS over naive, biasing the H2 natural-gas conclusion.",
        "Decision needed: for Jan-2020..Apr-2021 use FRED DHHNGSP (complete in that window) as the NG spot, or shift Bloomberg back one trading day under a documented rule; report sensitivity either way.",
        "After the fix: correlation of daily spot changes with same-day NG1 in the window is similar to 2017-19 and 2021-23 levels.", "high")
    hub = S["NGUSHHUB"]
    add("NATGAS", "NGUSHHUB", "2005-09-26", "2005-10-06", "stale prices",
        "Bloomberg Henry Hub is flat at 14.50 for 9 consecutive trading days (2005-09-26..2005-10-06) after Hurricane Rita; FRED is blank on the same days.",
        f"max stale run {q.loc['NGUSHHUB'].max_stale_run} starting {q.loc['NGUSHHUB'].max_stale_run_start}; Wednesdays affected 2005-09-28, 2005-10-05.",
        "potentially genuine event (Henry Hub/Sabine shut-in) with carried-forward values that are not real trades",
        "Two Wednesdays with zero spot return followed by a catch-up move.",
        "Artificially low spot volatility then a jump; distorts semivariance and basis in a known stress period.",
        "Flag these weeks; sensitivity with them treated as missing.", "Stage 2 flag column; HE with/without.", "low")
    a = q.loc["DHHNGSP"]
    add("NATGAS", "DHHNGSP", "1997-01-07", "2007-12-31", "missing-data cluster",
        "FRED Henry Hub is mostly blank before 2007.",
        f"{int(a.blank_obs)} blank rows; {int(a.wednesdays_missing)} Wednesdays missing ({a.wednesdays_missing_share:.1%}); ~70% of 1997-2006 trading days blank.",
        "verified (file content); whether FRED itself is this sparse is unresolved",
        "Rules out FRED as primary NG spot before 2007 and therefore a 1997 start.",
        "Proposal's 1997-2026 NG sample cannot be delivered with this file.",
        "Use NGUSHHUB (from 1999-01-04) as primary; change the proposal's NG sample to 1999-2026.", "n/a", "medium")
    a = x.loc[("NG1", "NGUSHHUB", 1.0)]
    add("NATGAS", "NG1 vs NGUSHHUB", "1999-01-04", "2026-11-09", "basis regime",
        "NG spot-futures basis is wide and time varying (largest of the six markets).",
        f"median NG1/spot {a.median_ratio}; p1/p99 {a.p01_ratio}/{a.p99_ratio}; 2024 median {xy('NG1 vs NGUSHHUB', 2024)}.",
        "potentially genuine (seasonality, storage, delivery-month mismatch)",
        "This is the core H2 mechanism; also means the roll convention materially changes NG futures returns.",
        "Mis-specifying the roll would be confounded with genuine basis risk.",
        "Report NG results under the main roll rule and one alternative.", "Stage 2 sensitivity.", "medium")
    add("NATGAS", "NGUSHHUB", "2026-11-06", "2026-11-09", "stale end-of-sample",
        "The last two NGUSHHUB values are identical (2.589).",
        f"2026-11-06 {v('NGUSHHUB','2026-11-06')}, 2026-11-09 {v('NGUSHHUB','2026-11-09')}.",
        "unresolved (possibly pulled before the 11-09 assessment)", "Outside the last sample Wednesday (2026-11-04).",
        "None for weekly analysis if the sample ends 2026-11-04.", "End the sample at 2026-11-04 or earlier.", "n/a", "low")

    # --- Macro ---------------------------------------------------------------
    cf = S["CFNAI"]
    add("MACRO", "CFNAI", "2026-10-01", "2026-11-04", "coverage end / vintage",
        "CFNAI ends at 2026-09; the series is revised over time, and this is a single (current) vintage.",
        f"last {fmt(cf.index.max())}; April-2020 value {cf.get(pd.Timestamp('2020-04-01'))} is an extreme (COVID) observation.",
        "verified coverage; vintage effect is a reasonable interpretation",
        "Regime labels for Oct-Nov 2026 weeks are unavailable; revised data differ from what the paper's authors saw in 2023.",
        "Small differences from the paper's regime split; mislabelled final weeks if forward-filled.",
        "Leave the last weeks unlabelled; note the vintage; assign monthly CFNAI to weeks by calendar month (decision in Stage 2).",
        "Count of weeks per regime vs paper where reported.", "low")
    us = S["USREC"]
    add("MACRO", "USREC", "1990-01-01", "2026-10-01", "definition / provisional values",
        "USREC marks 4 recessions since 1990 matching NBER dates (FRED convention: month after peak through trough); recent zeros are provisional until NBER rules.",
        "episodes: " + ", ".join(f"{fmt(a_)}..{fmt(b2)}" for a_, b2 in _episodes(us.loc['1990':])),
        "verified coverage", "Recession-period comparisons depend on this.",
        "Minor; a future NBER call could relabel 2025-26 months.", "Use as is; note provisional status.", "n/a", "low")

    # --- Reference / project-level ----------------------------------------
    sx = pd.read_csv(RAW / "bloomberg/SOXX_US_Equity.csv", parse_dates=["date"]).set_index("date")
    add("AI_LENS", "SOXX PX_LAST vs TOT_RETURN", "2024-03-07", "2026-11-05", "unadjusted splits",
        "SOXX PX_LAST is unadjusted: a 3-for-1 split on 2024-03-07 and another drop of ~3.4x on 2026-11-05.",
        f"2024-03-07 PX {sx.PX_LAST.get(pd.Timestamp('2024-03-06'))}->{sx.PX_LAST.get(pd.Timestamp('2024-03-07'))}, TR {sx.TOT_RETURN_INDEX_GROSS_DVDS.get(pd.Timestamp('2024-03-06'))}->{sx.TOT_RETURN_INDEX_GROSS_DVDS.get(pd.Timestamp('2024-03-07'))}; "
        f"2026-11-05 PX {sx.PX_LAST.get(pd.Timestamp('2026-11-04'))}->{sx.PX_LAST.get(pd.Timestamp('2026-11-05'))}, TR {sx.TOT_RETURN_INDEX_GROSS_DVDS.get(pd.Timestamp('2026-11-04'))}->{sx.TOT_RETURN_INDEX_GROSS_DVDS.get(pd.Timestamp('2026-11-05'))} (-12%).",
        "2024: corporate action (genuine split); 2026-11-05: unresolved (split plus a genuine ~12% fall per TR index)",
        "SOXX is only an optional marker of AI-stress weeks.",
        "Using PX_LAST would flag split days as -100% AI crashes.",
        "Use TOT_RETURN_INDEX_GROSS_DVDS only.", "n/a", "low")
    add("ALL", "contract calendars", "", "", "ticker ambiguity",
        "Bloomberg uses single-digit years for live contracts (e.g. BTCZ7 = Dec-2027, BPM1 = Jun-2031), which collide with historical tickers.",
        "single-digit-year tickers per root: " + ", ".join(f"{r.root}:{r.single_digit_year_tickers}" for r in cal.itertuples()),
        "verified", "Ticker parsing cannot recover contract year.", "Wrong contract ordering if sorted by ticker.",
        "Order and map contracts by LAST_TRADEABLE_DT only.", "Stage 2 unit test.", "low")
    add("ALL", "data/raw/eia/ (absent)", "", "", "missing files vs project context",
        "The context doc lists EIA originals (RWTCd.xls, RNGWHHDd.xls, RWTC.csv, RNGWHHD.csv) under data/raw/eia/; the folder does not exist.",
        "No eia/ directory under data/raw; not listed in manifest.csv.",
        "verified absence", "The claim 'EIA originals are identical to FRED, including the gaps' cannot be checked here.",
        "The FRED gap question (A02, DHHNGSP) stays open.",
        "Ask the teammate who holds them to add the files, or re-download from EIA.", "Diff EIA vs FRED.", "medium")
    return pd.DataFrame(A)


def hub_alignment() -> pd.DataFrame:
    """Monthly median |log| distance of Bloomberg HH(t) to FRED HH(t) and to FRED's previous observation."""
    h, f = series("NGUSHHUB"), series("DHHNGSP")
    j = pd.concat({"h": h, "f": f, "fp": f.shift(1)}, axis=1).dropna()
    j["same"] = np.abs(np.log(j.h / j.f))
    j["lag"] = np.abs(np.log(j.h / j.fp))
    m = j.groupby(pd.Grouper(freq="ME"))[["same", "lag"]].agg(["median", "size"])
    out = pd.DataFrame({"month": [d.strftime("%Y-%m") for d in m.index],
                        "days_compared": m[("same", "size")].values,
                        "median_absdiff_same_day": m[("same", "median")].round(4).values,
                        "median_absdiff_vs_fred_prev": m[("lag", "median")].round(4).values})
    out = out[out.days_compared > 0]
    out["closer_match"] = np.where(out.median_absdiff_vs_fred_prev < out.median_absdiff_same_day,
                                   "FRED previous day", "FRED same day")
    return out


def hub_futures_anchor() -> pd.DataFrame:
    h = np.log(series("NGUSHHUB")).diff()
    f = np.log(series("DHHNGSP")).diff()
    g = np.log(series("NG1")).diff()
    rows = []
    for a, b in [("2017-01", "2019-12"), ("2020-01", "2021-04"), ("2021-06", "2023-12")]:
        j = pd.concat({"h": h, "f": f, "g": g}, axis=1).loc[a:b]
        rows.append(dict(period=f"{a}..{b}", hub_vs_ng1_same_day=round(j.h.corr(j.g), 3),
                         hub_vs_ng1_prev_day=round(j.h.corr(j.g.shift(1)), 3),
                         fred_vs_ng1_same_day=round(j.f.corr(j.g), 3),
                         fred_vs_ng1_prev_day=round(j.f.corr(j.g.shift(1)), 3)))
    return pd.DataFrame(rows)


_YEARLY: pd.DataFrame | None = None


def xy(pair: str, year: int):
    if _YEARLY is None:
        return ""
    r = _YEARLY[(_YEARLY.pair == pair) & (_YEARLY.year == year)]
    return r.median_ratio.iloc[0] if len(r) else ""


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    global _YEARLY
    inv = inventory()
    outl = outlier_screen()
    qs, wcov = quality_summary(outl)
    xs, yearly = cross_source()
    _YEARLY = yearly
    cal, roll = calendar_checks()
    man = manifest_comparison(inv)
    anom = anomaly_register(qs, xs, cal, roll)

    inv.to_csv(OUT / "raw_data_inventory.csv", index=False)
    qs.to_csv(OUT / "data_quality_summary.csv", index=False)
    man.to_csv(OUT / "manifest_comparison.csv", index=False)
    anom.to_csv(OUT / "anomaly_register.csv", index=False)
    outl.to_csv(SUP / "daily_outlier_screen.csv", index=False)
    wcov.to_csv(SUP / "wednesday_coverage.csv", index=False)
    xs.to_csv(SUP / "cross_source_comparison.csv", index=False)
    yearly.to_csv(SUP / "cross_source_yearly_ratio.csv", index=False)
    hub_alignment().to_csv(SUP / "henry_hub_date_alignment_by_month.csv", index=False)
    hub_futures_anchor().to_csv(SUP / "henry_hub_futures_anchor_correlations.csv", index=False)
    cal.to_csv(SUP / "contract_calendar_checks.csv", index=False)
    roll.to_csv(SUP / "generic_roll_cycle_test.csv", index=False)

    hash_after = hash_tree()
    unchanged = hash_after == HASH_BEFORE
    with open(OUT / "run_log.txt", "w", encoding="utf-8") as f:
        f.write(f"run_at={datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"python={sys.version.split()[0]} pandas={pd.__version__} numpy={np.__version__} platform={platform.platform()}\n")
        f.write(f"raw_files_hashed={len(HASH_BEFORE)} raw_files_unchanged_after_run={unchanged}\n")
        f.write(f"inventory_rows={len(inv)} quality_rows={len(qs)} manifest_rows={len(man)} anomalies={len(anom)} outlier_rows={len(outl)}\n")
    print(open(OUT / "run_log.txt", encoding="utf-8").read())
    if not unchanged:
        raise SystemExit("ERROR: a file under data/raw changed during the audit run")


if __name__ == "__main__":
    main()
