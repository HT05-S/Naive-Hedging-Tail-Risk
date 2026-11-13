"""Automated tests for Stage 1B (stdlib unittest; no extra dependencies).

Run from the project root:
    python -m pytest -q tests

Most tests check the delivered file data/processed/weekly_market_returns.csv
against the raw files using code paths that are independent of the builder.
Tests marked 'build' rebuild one market (about 15 s each).
"""
from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frm_data import config as C            # noqa: E402
from frm_data import io                      # noqa: E402
from frm_data.contracts import contract_table, held_contracts  # noqa: E402
from frm_data.weekly import _logret, build_market               # noqa: E402

WEEKLY = ROOT / "data" / "processed" / "weekly_market_returns.csv"
GEN_FILE = {"CL": "CL{k}_Comdty", "NG": "NG{k}_Comdty", "GC": "GC{k}_Comdty", "BP": "BP{k}_Curncy",
            "SP": "SP{k}_Index", "ES": "ES{k}_Index", "BTC": "BTC{k}_Curncy"}
CYCLE = {"CL": C.ALL, "NG": C.ALL, "GC": "GJMQVZ", "BP": "HMUZ", "SP": "HMUZ", "ES": "HMUZ", "BTC": C.ALL}


def load_weekly() -> pd.DataFrame:
    w = pd.read_csv(WEEKLY, low_memory=False)
    for c in ("target_wed", "obs_date", "prev_obs_date", "fut_ltd", "roll_trigger", "fut_contract_month"):
        w[c] = pd.to_datetime(w[c])
    return w


def raw_price(rel: str, date) -> float:
    """Independent raw read: plain CSV text, no shared helper."""
    with open(io.RAW / rel, encoding="utf-8") as f:
        for line in f:
            a, _, b = line.strip().partition(",")
            if a == pd.Timestamp(date).strftime("%Y-%m-%d"):
                return float(b) if b not in ("", ".") else float("nan")
    return float("nan")


class TestRawImmutability(unittest.TestCase):
    def test_hashes_equal_stage1_inventory(self):
        inv = pd.read_csv(ROOT / "audit" / "results" / "raw_data_inventory.csv")
        stage1 = inv.drop_duplicates("relative_path").set_index("relative_path")["sha256"].to_dict()
        now = io.hash_tree()
        for rel, h in stage1.items():
            key = rel.replace("data/raw/", "")
            self.assertIn(key, now, f"{rel} missing")
            self.assertEqual(now[key], h, f"{rel} changed since the Stage 1 audit")

    def test_no_processed_output_inside_raw(self):
        for p in io.RAW.rglob("*"):
            self.assertNotIn("weekly_market_returns", p.name)


class TestReading(unittest.TestCase):
    def _tmp(self, text):
        d = tempfile.TemporaryDirectory()
        (Path(d.name) / "x.csv").write_text(text)
        return d

    def test_duplicate_dates_rejected(self):
        d = self._tmp("date,v\n2020-01-01,1\n2020-01-01,2\n")
        with self.assertRaises(ValueError):
            io.read_series("x.csv", base=Path(d.name))
        d.cleanup()

    def test_unsorted_dates_rejected(self):
        d = self._tmp("date,v\n2020-01-02,1\n2020-01-01,2\n")
        with self.assertRaises(ValueError):
            io.read_series("x.csv", base=Path(d.name))
        d.cleanup()

    def test_blanks_become_nan_not_filled(self):
        d = self._tmp("date,v\n2020-01-01,1\n2020-01-02,.\n2020-01-03,\n2020-01-06,4\n")
        s = io.read_series("x.csv", base=Path(d.name))
        self.assertEqual(len(s), 4)
        self.assertTrue(np.isnan(s.iloc[1]) and np.isnan(s.iloc[2]))
        d.cleanup()


class TestWeeklyDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = load_weekly()
        cls.d = cls.w[cls.w.return_defined]

    # 1 + 9: missing dates / missing weeks
    def test_one_row_per_market_week(self):
        self.assertFalse(self.w.duplicated(["market", "target_wed"]).any())
        for m, g in self.w.groupby("market"):
            self.assertTrue((g.target_wed.diff().dropna() == pd.Timedelta(days=7)).all(), m)
            self.assertTrue((g.target_wed.dt.day_of_week == 2).all(), m)

    def test_obs_date_within_lookback(self):
        x = self.w.dropna(subset=["obs_date"])
        lag = (x.target_wed - x.obs_date).dt.days
        self.assertTrue(lag.between(0, C.LOOKBACK_DAYS).all())

    # 4: no silent bridging
    def test_prev_obs_is_previous_weeks_obs(self):
        for m, g in self.w.groupby("market"):
            g = g.reset_index(drop=True)
            prev = g.obs_date.shift(1)
            ok = g.return_defined
            self.assertTrue((g.loc[ok, "prev_obs_date"] == prev[ok]).all(), m)
            self.assertTrue((g.loc[ok, "holding_days"] <= C.MAX_HOLDING_DAYS).all(), m)

    def test_week_after_missing_week_is_undefined(self):
        for m, g in self.w.groupby("market"):
            g = g.reset_index(drop=True)
            after = g.index[g.obs_date.shift(1).isna()][1:]   # skip the first row of each market
            self.assertFalse(g.loc[after, "return_defined"].any(), m)

    # 2: spot and futures from the same date, recomputed independently from raw
    def test_prices_match_raw_on_obs_dates(self):
        rng = np.random.default_rng(0)
        sample = self.d.iloc[rng.choice(len(self.d), size=300, replace=False)]
        for _, r in sample.iterrows():
            src = r.spot_source.split(":")[1]
            rel = {"DCOILWTICO": "fred/DCOILWTICO.csv", "DHHNGSP": "fred/DHHNGSP.csv"}.get(
                src, f"bloomberg/{src}_{'Curncy' if src in ('GBPUSD', 'XAU', 'XBTUSD') else 'Index'}.csv")
            self.assertAlmostEqual(raw_price(rel, r.obs_date), r.spot_price, places=8)
            self.assertAlmostEqual(raw_price(rel, r.prev_obs_date), r.spot_price_prev, places=8)
            div = 100.0 if r.market == "GBPUSD" else 1.0
            for gcol, dcol, pcol in (("fut_generic", "obs_date", "fut_price"), ("fut_generic_prev", "prev_obs_date", "fut_price_prev")):
                g = r[gcol]
                root, k = g.rstrip("123"), g[-1]
                rel = "bloomberg/" + GEN_FILE[root].format(k=k) + ".csv"
                self.assertAlmostEqual(raw_price(rel, r[dcol]) / div, r[pcol], places=8)

    # 3: positivity
    def test_logs_only_of_positive_prices(self):
        cols = ["spot_price", "spot_price_prev", "fut_price", "fut_price_prev"]
        self.assertTrue((self.d[cols] > 0).all().all())
        self.assertTrue(np.isnan(_logret(-37.63, 19.87)))
        self.assertTrue(np.isnan(_logret(10.0, 0.0)))
        self.assertTrue(np.isnan(_logret(np.nan, 1.0)))

    def test_returns_recompute(self):
        r1 = np.log(self.d.spot_price / self.d.spot_price_prev)
        r2 = np.log(self.d.fut_price / self.d.fut_price_prev)
        self.assertLess((r1 - self.d.spot_logret).abs().max(), 1e-12)
        self.assertLess((r2 - self.d.fut_logret).abs().max(), 1e-12)

    # 5 + 6: contract identity, expiration and roll-adjusted returns
    def test_contract_identity_independent_rank(self):
        """Re-derive the generic rank from the calendar (count of usable contracts expiring on or
        after the date and before the held one) and check it equals the generic actually used."""
        cache = {}
        for _, r in self.d.iterrows():
            root = r.fut_root
            if root not in cache:
                t = contract_table(root, CYCLE[root])
                cache[root] = t[t.usable].sort_values("LTD")
            u = cache[root]
            ltd_c = u.loc[u.ticker == r.fut_contract, "LTD"].iloc[0]
            for dcol, gcol in (("obs_date", "fut_generic"), ("prev_obs_date", "fut_generic_prev")):
                k = int(((u.LTD >= r[dcol]) & (u.LTD <= ltd_c)).sum())
                self.assertEqual(f"{root}{k}", r[gcol], f"{r.market} {r.target_wed.date()} {dcol}")

    def test_held_contract_alive_and_before_trigger(self):
        self.assertTrue((self.d.obs_date < self.d.fut_ltd).all())
        self.assertTrue((self.d.target_wed < self.d.roll_trigger).all())

    def test_same_contract_both_ends(self):
        # a generic switch inside an interval is only allowed from G(k) to G(k-1) (the old front expired)
        g0 = self.d.fut_generic_prev.str[-1].astype(int)
        g1 = self.d.fut_generic.str[-1].astype(int)
        self.assertTrue(((g1 == g0) | (g1 == g0 - 1)).all())

    def test_cycles_and_phantoms(self):
        code = self.d.fut_contract.str.extract(r"^[A-Z]{2,3}?([FGHJKMNQUVXZ])\d")[0]
        mk = self.d.market
        self.assertTrue(code[mk == "GOLD"].isin(list("GJMQVZ")).all())
        self.assertTrue(code[mk.isin(["GBPUSD", "SP500"])].isin(list("HMUZ")).all())
        sp = contract_table("SP", "HMUZ")
        phantoms = set(sp[sp.phantom].ticker)
        self.assertEqual(len(phantoms), 12)
        self.assertFalse(self.d.fut_contract.isin(phantoms).any())
        self.assertFalse(self.w.alt_fut_contract.isin(phantoms).any())

    def test_contract_months_never_go_backwards(self):
        for m, g in self.w.groupby("market"):
            self.assertTrue(g.fut_contract_month.is_monotonic_increasing, m)

    def test_sp_to_es_switch(self):
        s = self.d[self.d.market == "SP500"]
        self.assertTrue((s[s.fut_root == "ES"].fut_contract_month >= "2021-12-01").all())
        self.assertTrue((s[s.fut_root == "SP"].fut_contract_month <= "2021-09-01").all())
        self.assertEqual(s[s.fut_root == "ES"].target_wed.min(), pd.Timestamp("2021-09-01"))

    # 7: BP units
    def test_bp_unit_normalisation(self):
        self.assertGreater(raw_price("bloomberg/BP1_Curncy.csv", "2019-03-13"), 100)   # cents in raw
        g = self.d[self.d.market == "GBPUSD"]
        ratio = g.fut_price / g.spot_price
        self.assertTrue(ratio.between(0.95, 1.05).all())

    # 8: sample boundaries
    def test_sample_boundaries(self):
        w = self.w
        h1 = w[w.market.isin(["WTI", "GBPUSD", "SP500", "GOLD"])]
        self.assertTrue((h1[h1.sample_period == "original_1990_2023"].target_wed <= C.ORIGINAL_END).all())
        self.assertTrue((h1[h1.sample_period == "extension_2023_2026"].target_wed >= C.EXTENSION_START).all())
        self.assertEqual(h1.target_wed.min(), C.FIRST_TARGET)
        self.assertEqual(w.target_wed.max(), C.LAST_TARGET)
        btc = w[w.market == "BTC"]
        self.assertTrue((btc.obs_date.dropna() >= C.BTC_CME_FIRST_TRADE).all())
        self.assertEqual(btc[btc.return_defined].target_wed.min(), pd.Timestamp("2017-12-27"))
        ng = w[w.market == "NATGAS"]
        self.assertEqual(ng.target_wed.min(), pd.Timestamp("1999-01-06"))
        nd = ng[ng.return_defined]
        self.assertTrue((nd[nd.prev_obs_date >= C.NG_FRED_START].spot_source == "FRED:DHHNGSP").all())
        self.assertTrue((nd[nd.target_wed <= "2007-04-04"].spot_source == "BBG:NGUSHHUB").all())

    # 10: stress-event preservation
    def test_stress_events_preserved(self):
        self.assertEqual(raw_price("bloomberg/CL1_Comdty.csv", "2020-04-20"), -37.63)
        self.assertEqual(raw_price("fred/DCOILWTICO.csv", "2020-04-20"), -36.98)
        ng = self.d[self.d.market == "NATGAS"].set_index("target_wed")
        self.assertAlmostEqual(ng.loc["2021-02-17", "spot_price"], 23.86)
        self.assertGreater(ng.loc["2021-02-17", "spot_logret"], 1.8)
        self.assertLess(ng.loc["2021-02-24", "spot_logret"], -2.1)
        wti = self.d[self.d.market == "WTI"].set_index("target_wed")
        self.assertLess(wti.loc["2020-04-22", "fut_logret"], -0.63)
        self.assertLess(wti.loc["2020-03-18", "spot_logret"], -0.48)

    def test_exclusions_logged(self):
        log = pd.read_csv(ROOT / "data" / "processed" / "processed_data_log.csv")
        ex = log[log.record_type == "observation_excluded"]
        self.assertIn("2025-09-29", set(ex[ex.series.str.contains("NGUSHHUB", na=False)].date))
        self.assertIn("2017-12-15", set(ex.date))
        self.assertTrue((ex.raw_value.notna()).all())


class TestManualStressChecks(unittest.TestCase):
    """Hand-computed values; raw prices copied from the CSV files by grep."""

    @classmethod
    def setUpClass(cls):
        w = load_weekly()
        cls.r = {(m, d.strftime("%Y-%m-%d")): row for m, d, row in zip(w.market, w.target_wed, w.to_dict("records"))}

    def check(self, m, T, spot0, spot1, f0, f1, contract):
        r = self.r[(m, T)]
        self.assertEqual(r["fut_contract"], contract)
        self.assertAlmostEqual(r["spot_logret"], math.log(spot1 / spot0), places=10)
        self.assertAlmostEqual(r["fut_logret"], math.log(f1 / f0), places=10)

    def test_wti_2020_04_22(self):
        # CLK20 expired 2020-04-21; held CLM20 = CL2 on 04-15 (26.04) and CL1 on 04-22 (13.78)
        self.check("WTI", "2020-04-22", 19.96, 13.64, 26.04, 13.78, "CLM20 Comdty")

    def test_wti_2020_04_15(self):
        self.check("WTI", "2020-04-15", 24.97, 19.96, 25.09, 19.87, "CLK20 Comdty")

    def test_wti_2020_03_18(self):
        self.check("WTI", "2020-03-18", 33.13, 20.48, 32.98, 20.37, "CLJ20 Comdty")

    def test_ng_uri_2021_02_17(self):
        self.check("NATGAS", "2021-02-17", 3.76, 23.86, 2.911, 3.219, "NGH21 Comdty")

    def test_ng_uri_2021_02_24(self):
        # NGH21 LTD 2021-02-24 = target, so NGJ21 is held: NG2 on 02-17 (3.032) and NG2 on 02-24 (2.795)
        self.check("NATGAS", "2021-02-24", 23.86, 2.80, 3.032, 2.795, "NGJ21 Comdty")

    def test_ng_2026_02_04_no_splice(self):
        # NGG26 expired 2026-01-28 at 7.46; held NGH26 = NG2 on 01-28 (3.732), NG1 on 02-04 (3.465)
        r = self.r[("NATGAS", "2026-02-04")]
        self.assertEqual(r["fut_contract"], "NGH26 Comdty")
        self.assertAlmostEqual(r["fut_logret"], math.log(3.465 / 3.732), places=10)
        self.assertGreater(r["fut_logret"], math.log(3.465 / 7.46) + 0.6)   # splice would book -0.77


class TestBuildProperties(unittest.TestCase):
    """build: rebuilds WTI."""

    @classmethod
    def setUpClass(cls):
        cls.full, _ = build_market(C.MARKETS["WTI"])

    # 11: no look-ahead
    def test_no_lookahead(self):
        cut = pd.Timestamp("2020-04-22")
        part, _ = build_market(C.MARKETS["WTI"], last=cut, price_cutoff=cut)
        a = self.full[self.full.target_wed <= cut].reset_index(drop=True)
        b = part.reset_index(drop=True)
        cols = ["obs_date", "prev_obs_date", "fut_contract", "spot_logret", "fut_logret"]
        pd.testing.assert_frame_equal(a[cols], b[cols])

    # 9: strict Wednesday rule is the strict subset of the primary rule
    def test_strict_rule_is_subset(self):
        strict, _ = build_market(C.MARKETS["WTI"], lookback=0)
        s1 = set(strict.loc[strict.return_defined, "target_wed"])
        s2 = set(self.full.loc[self.full.return_defined & self.full.strict_wednesday, "target_wed"])
        self.assertEqual(s1, s2)

    def test_held_contract_rule_uses_calendar_only(self):
        T = pd.date_range("2020-03-04", "2020-05-27", freq="W-WED")
        h = held_contracts(C.MARKETS["WTI"], T, "ltd")
        self.assertEqual(h.loc["2020-04-15", "ticker"], "CLK20 Comdty")
        self.assertEqual(h.loc["2020-04-22", "ticker"], "CLM20 Comdty")
        self.assertTrue((T < h.LTD.values).all())


if __name__ == "__main__":
    unittest.main()
