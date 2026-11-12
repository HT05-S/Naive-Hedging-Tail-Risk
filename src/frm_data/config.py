"""Fixed rules for Stage 1B. Every rule here was set from data coverage, contract
specifications or the published methodology, before any hedge was estimated.

Roll-trigger rules (a contract c is held over the weekly interval ending at
target Wednesday T only if T < R_c):
  "cm_start"        R_c = first calendar day of c's contract (delivery) month.
                    This is Cao & Conlon's stated rule (Section 4, p. 983).
  "ltd"             R_c = c's last tradeable date (expiry-based roll).
  "ltd_month_start" R_c = first calendar day of the month that contains c's
                    last tradeable date (an earlier, pre-expiry-month roll).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

FIRST_TARGET = pd.Timestamp("1990-01-03")    # first Wednesday of 1990
ORIGINAL_END = pd.Timestamp("2023-06-28")    # last Wednesday of the paper's sample
EXTENSION_START = pd.Timestamp("2023-07-05")
LAST_TARGET = pd.Timestamp("2026-11-04")     # last Wednesday before the 2026-11-09 data pull
LOOKBACK_DAYS = 2                            # primary rule B: Wednesday, else Tue, else Mon
MAX_HOLDING_DAYS = 9                         # 7 +/- 2; anything longer is never a 'weekly' return

# Henry Hub source switch: first month from which FRED/EIA reports a price on
# >= 90% of NG1 trading days in every subsequent calendar year (see
# natural_gas_source_comparison.csv). Fixed from coverage only.
NG_FRED_START = pd.Timestamp("2007-04-01")
BTC_CME_FIRST_TRADE = pd.Timestamp("2017-12-18")   # CME Bitcoin futures launch (trade date)


@dataclass(frozen=True)
class SpotSegment:
    label: str          # e.g. "FRED:DCOILWTICO"
    rel: str            # path under data/raw
    col: str
    start: pd.Timestamp | None = None   # first target Wednesday that may START an interval with this source
    end: pd.Timestamp | None = None     # last target Wednesday that may START an interval with this source


@dataclass(frozen=True)
class FutLeg:
    root: str
    cycle: str                          # month codes of the generic cycle
    cm_min: pd.Timestamp | None = None  # use only contracts with contract month >= cm_min
    cm_max: pd.Timestamp | None = None  # ... and <= cm_max


@dataclass(frozen=True)
class Market:
    market: str
    spot: tuple[SpotSegment, ...]
    legs: tuple[FutLeg, ...]
    roll_primary: str
    roll_alt: str
    unit_divisor: float = 1.0           # futures price / divisor = spot units
    first_target: pd.Timestamp = FIRST_TARGET
    spot_alt: SpotSegment | None = None
    notes: str = ""


ALL = "FGHJKMNQUVXZ"

MARKETS: dict[str, Market] = {
    "WTI": Market(
        "WTI",
        spot=(SpotSegment("FRED:DCOILWTICO", "fred/DCOILWTICO.csv", "DCOILWTICO"),),
        legs=(FutLeg("CL", ALL),),
        roll_primary="ltd", roll_alt="ltd_month_start",
        notes="Contract month starts after expiry, so the paper's cm_start rule is infeasible; "
              "primary holds the nearest contract that has not reached its LTD by the interval end."),
    "GBPUSD": Market(
        "GBPUSD",
        spot=(SpotSegment("BBG:GBPUSD", "bloomberg/GBPUSD_Curncy.csv", "PX_LAST"),),
        legs=(FutLeg("BP", "HMUZ"),),
        roll_primary="cm_start", roll_alt="ltd", unit_divisor=100.0,
        notes="BP futures are quoted in US cents per GBP."),
    "SP500": Market(
        "SP500",
        spot=(SpotSegment("BBG:SPX", "bloomberg/SPX_Index.csv", "PX_LAST"),),
        legs=(FutLeg("SP", "HMUZ", cm_max=pd.Timestamp("2021-09-01")),
              FutLeg("ES", "HMUZ", cm_min=pd.Timestamp("2021-12-01"))),
        roll_primary="cm_start", roll_alt="ltd",
        notes="Big S&P (SP) through SPU21, its last listed contract; E-mini (ES) from ESZ21."),
    "GOLD": Market(
        "GOLD",
        spot=(SpotSegment("BBG:XAU", "bloomberg/XAU_Curncy.csv", "PX_LAST"),),
        legs=(FutLeg("GC", "GJMQVZ"),),
        roll_primary="cm_start", roll_alt="ltd",
        notes="LBMA PM file is empty; XAU spot substitutes."),
    "BTC": Market(
        "BTC",
        spot=(SpotSegment("BBG:BRR", "bloomberg/BRR_Index.csv", "PX_LAST"),),
        legs=(FutLeg("BTC", ALL),),
        roll_primary="cm_start", roll_alt="ltd",
        first_target=pd.Timestamp("2017-12-20"),
        spot_alt=SpotSegment("BBG:XBTUSD", "bloomberg/XBTUSD_Curncy.csv", "PX_LAST")),
    "NATGAS": Market(
        "NATGAS",
        spot=(SpotSegment("BBG:NGUSHHUB", "bloomberg/NGUSHHUB_Index.csv", "PX_LAST",
                          end=NG_FRED_START - pd.Timedelta(days=1)),
              SpotSegment("FRED:DHHNGSP", "fred/DHHNGSP.csv", "DHHNGSP", start=NG_FRED_START)),
        legs=(FutLeg("NG", ALL),),
        roll_primary="ltd", roll_alt="ltd_month_start",
        first_target=pd.Timestamp("1999-01-06"),
        notes="Composite Henry Hub spot: Bloomberg for intervals starting before 2007-04-01, "
              "FRED/EIA from then on; each return uses one source at both ends."),
}


@dataclass(frozen=True)
class Exclusion:
    rel: str
    start: str
    end: str
    reason: str
    evidence: str


# Observation-level exclusions. Raw values are preserved on disk; these dates are
# treated as 'not observed' in the processed data and every one is logged.
EXCLUSIONS: tuple[Exclusion, ...] = (
    Exclusion("bloomberg/NGUSHHUB_Index.csv", "2005-09-26", "2005-10-06",
              "stale value during Henry Hub shutdown after Hurricane Rita",
              "NGUSHHUB repeats 14.50 for 9 trading days; FRED/EIA has no Henry Hub print on any of "
              "these days; NG1 moves 12.44 -> 13.38 over the same days"),
    Exclusion("bloomberg/NGUSHHUB_Index.csv", "2025-09-29", "2025-09-29",
              "isolated bad print",
              "0.2571 vs FRED 2.93 the same day and 2.9-3.0 on adjacent days in both sources; NG1 3.27"),
    Exclusion("bloomberg/NGUSHHUB_Index.csv", "2020-01-01", "2021-03-12",
              "dated by gas-flow day, not trade day (incompatible with futures settlement dates)",
              "every NG1 trading Monday missing, prints on NYMEX holidays, daily changes track "
              "prior-day NG1 (see natural_gas_source_comparison.csv)"),
    Exclusion("bloomberg/BTC1_Curncy.csv", "2017-12-15", "2017-12-15",
              "row predates CME launch (first trade date 2017-12-18)", "round-number values"),
    Exclusion("bloomberg/BTC2_Curncy.csv", "2017-12-15", "2017-12-15",
              "row predates CME launch (first trade date 2017-12-18)", "round-number values"),
    Exclusion("bloomberg/BTC3_Curncy.csv", "2017-12-15", "2017-12-15",
              "row predates CME launch (first trade date 2017-12-18)", "round-number values"),
)
