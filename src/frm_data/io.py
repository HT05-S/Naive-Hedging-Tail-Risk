"""Read-only access to raw files plus an integrity guard.

All raw files are read as strings first so that nothing is silently coerced;
blank cells and FRED's "." become NaN explicitly.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
EXTERNAL = ROOT / "data" / "external" / "verification_2026-11-11"
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "audit" / "results"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_tree(base: Path = RAW) -> dict[str, str]:
    return {str(p.relative_to(base)).replace("\\", "/"): sha256(p)
            for p in sorted(base.rglob("*")) if p.is_file()}


@lru_cache(maxsize=None)
def _read_strings(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def read_series(rel: str, col: str | None = None, base: Path = RAW, valid_only: bool = False) -> pd.Series:
    """Return a float Series indexed by date. Blank and '.' become NaN (never filled)."""
    d = _read_strings(str(base / rel)).copy()
    dcol = d.columns[0]
    col = col or d.columns[1]
    idx = pd.DatetimeIndex(pd.to_datetime(d[dcol], errors="raise"))
    vals = pd.to_numeric(d[col].replace({"": np.nan, ".": np.nan}), errors="raise")
    s = pd.Series(vals.to_numpy(dtype=float), index=idx, name=rel.split("/")[-1].split(".")[0])
    if not s.index.is_unique:
        raise ValueError(f"duplicate dates in {rel}")
    if not s.index.is_monotonic_increasing:
        raise ValueError(f"unsorted dates in {rel}")
    return s.dropna() if valid_only else s


def read_calendar(root: str) -> pd.DataFrame:
    d = _read_strings(str(RAW / "bloomberg" / f"{root}_contracts.csv")).copy()
    d["LTD"] = pd.to_datetime(d["LAST_TRADEABLE_DT"], errors="raise")
    d["FND"] = pd.to_datetime(d["FUT_NOTICE_FIRST"], errors="raise")
    return d


def read_eia_xls(path: Path) -> pd.Series:
    """EIA 'hist_xls' daily file, sheet 'Data 1', header rows 0-2."""
    import xlrd  # optional dependency used only for external verification
    book = xlrd.open_workbook(str(path))
    sh = book.sheet_by_name("Data 1")
    dates, vals = [], []
    for r in range(3, sh.nrows):
        c0 = sh.cell_value(r, 0)
        if c0 == "":
            continue
        dates.append(xlrd.xldate_as_datetime(c0, book.datemode))
        v = sh.cell_value(r, 1)
        vals.append(float(v) if v != "" else np.nan)
    return pd.Series(vals, index=pd.DatetimeIndex(dates), dtype=float)
