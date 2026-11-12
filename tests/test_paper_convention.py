"""Tests for the paper-setting dataset (strict Wednesdays, spliced futures, the paper's roll rule).

Run from the project root:  python -m pytest -q tests
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frm_data import config as C, io                        # noqa: E402
from frm_data.contracts import generics                      # noqa: E402
from frm_data.paper import PAPER_FILE, held_on, paper_calendar, spliced_price  # noqa: E402


def weekly() -> pd.DataFrame:
    return pd.read_csv(io.PROCESSED / PAPER_FILE, parse_dates=["target_wed", "obs_date"])


class TestCalendar(unittest.TestCase):
    def test_original_sample_has_the_papers_1728_wednesdays(self):
        cal = paper_calendar(C.ORIGINAL_END)
        self.assertEqual(len(cal), 1728)
        self.assertTrue((cal.dayofweek == 2).all())

    def test_only_wti_ever_uses_a_non_wednesday(self):
        w = weekly()
        moved = w[w["obs_date"] != w["target_wed"]]
        self.assertEqual(set(moved["market"]), {"WTI"})
        self.assertTrue(((moved["target_wed"] - moved["obs_date"]).dt.days <= C.LOOKBACK_DAYS).all())


class TestRollRule(unittest.TestCase):
    def test_wti_is_the_front_generic(self):
        w = weekly().query("market == 'WTI'")
        cl1 = generics("CL")["G1"]
        np.testing.assert_allclose(w["fut_price"].to_numpy(), cl1.reindex(w["obs_date"]).to_numpy())

    def test_gbp_rolls_on_first_day_of_contract_month(self):
        m = C.MARKETS["GBPUSD"]
        d = pd.DatetimeIndex(["2024-02-28", "2024-03-01", "2024-03-06"])
        self.assertEqual([t.split()[0] for t in held_on(m, d)["ticker"]], ["BPH24", "BPM24", "BPM24"])
        bp2 = generics("BP")["G2"]            # BPM24 is still the second generic in early March
        self.assertAlmostEqual(spliced_price(m, d[[2]])["fut_price"].iloc[0], bp2[d[2]] / 100.0)

    def test_sp500_switches_from_big_contract_to_emini(self):
        m = C.MARKETS["SP500"]
        roots = held_on(m, pd.DatetimeIndex(["2021-08-25", "2021-09-08"]))["root"].tolist()
        self.assertEqual(roots, ["SP", "ES"])


class TestReturns(unittest.TestCase):
    def test_returns_are_spliced_log_price_changes(self):
        for _, g in weekly().groupby("market"):
            np.testing.assert_allclose(g["fut_logret"].to_numpy()[1:], np.diff(np.log(g["fut_price"].to_numpy())), atol=1e-9)
            np.testing.assert_allclose(g["spot_logret"].to_numpy()[1:], np.diff(np.log(g["spot_price"].to_numpy())), atol=1e-9)

    def test_wti_april_2020_roll_week_is_spliced(self):
        w = weekly().query("market == 'WTI'").set_index("target_wed")
        r = w.loc["2020-04-22"]
        self.assertTrue(r["roll"])
        self.assertAlmostEqual(r["fut_logret"], np.log(13.78 / 19.87), places=3)   # CLM20 against CLK20 a week earlier


if __name__ == "__main__":
    unittest.main()
