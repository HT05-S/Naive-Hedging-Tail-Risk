"""Tests for the hedge-ratio models and the evaluation measures.

Run from the project root:  python -m pytest -q tests
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hedging import evaluate as ev                  # noqa: E402
from hedging import models                          # noqa: E402


def sample(n=300, beta=0.9, noise=0.004, seed=1):
    rng = np.random.default_rng(seed)
    f = rng.standard_t(5, n) * 0.02
    return beta * f + rng.normal(0, noise, n), f


class TestModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s, cls.f = sample()
        cls.b = models.estimate(cls.s, cls.f, n_sim=2000)

    def test_shape_and_alignment(self):
        self.assertEqual(len(self.b), len(self.s) - 51)
        self.assertEqual(self.b.index[0], 51)
        self.assertEqual(self.b.shape[1], len(models.MODELS) * len(models.SCENARIOS))

    def test_naive_is_one(self):
        self.assertTrue((self.b["naive"] == 1.0).all().all())

    def test_ols_matches_regression_slope(self):
        j = 120
        slope = np.polyfit(self.f[j - 51: j + 1], self.s[j - 51: j + 1], 1)[0]
        self.assertAlmostEqual(self.b.loc[j, ("ols", "down", "VaR", 0.05)], slope, places=10)

    def test_no_look_ahead(self):
        s2, f2 = self.s.copy(), self.f.copy()
        s2[200:] *= 3.0                                      # change the future only
        f2[200:] *= -2.0
        b2 = models.estimate(s2, f2, n_sim=2000)
        np.testing.assert_array_equal(self.b.loc[:199].to_numpy(), b2.loc[:199].to_numpy())

    def test_estimated_ratios_recover_the_true_beta(self):
        for m in ("ols", "hs", "cfe", "sv"):
            self.assertAlmostEqual(self.b[m].to_numpy().mean(), 0.9, delta=0.05)

    def test_hs_minimises_window_var(self):
        j, a = 150, 0.10
        sw, fw = self.s[j - 51: j + 1], self.f[j - 51: j + 1]
        var = [-np.quantile(sw - g * fw, a) for g in models.GRID]
        self.assertAlmostEqual(self.b.loc[j, ("hs", "down", "VaR", a)], models.GRID[int(np.argmin(var))])

    def test_cornish_fisher_reduces_to_normal(self):
        var, cvar = models.cf_risk(1.0, 0.0, 0.0, 0.05)
        self.assertAlmostEqual(var, 1.6449, places=3)
        self.assertAlmostEqual(cvar, 2.0627, places=3)

    def test_clayton_draws_have_the_fitted_dependence(self):
        rng = np.random.default_rng(0)
        u1, w = rng.uniform(size=20000), rng.uniform(size=20000)
        u2 = models.clayton_draws(4.0, u1, w)
        self.assertAlmostEqual(models.clayton_theta(u1, u2), 4.0, delta=0.15)


class TestEvaluation(unittest.TestCase):
    def test_tail_measures(self):
        y = np.arange(-50, 51) / 100.0                       # 101 points, -0.50 .. 0.50
        self.assertAlmostEqual(ev.risk(y, "down", "VaR", 0.05), 0.45)
        self.assertAlmostEqual(ev.risk(y, "down", "CVaR", 0.05), np.mean([0.50, 0.49, 0.48, 0.47, 0.46, 0.45]))
        self.assertAlmostEqual(ev.risk(-y * 2, "up", "VaR", 0.05), 0.90)

    def test_perfect_hedge_has_effectiveness_one(self):
        s, _ = sample()
        self.assertAlmostEqual(ev.effectiveness(s * 0, s, "down", "CVaR", 0.05), 1.0)
        self.assertAlmostEqual(ev.effectiveness(s, s, "up", "VaR", 0.10), 0.0)

    def test_harrell_davis_weights(self):
        w = ev.hd_weights(200, 0.05)
        self.assertAlmostEqual(w.sum(), 1.0)
        x = np.sort(np.random.default_rng(0).normal(size=200))
        self.assertAlmostEqual(float(x @ w), np.quantile(x, 0.05), delta=0.15)

    def test_wilcox_direction(self):
        rng = np.random.default_rng(3)
        naive = rng.normal(0, 0.02, 800)
        self.assertLess(ev.wilcox_pvalue(naive * 0.5, naive, "down", 0.05, 500), 0.05)   # clearly less tail risk
        self.assertGreater(ev.wilcox_pvalue(naive * 2.0, naive, "down", 0.05, 500), 0.95)
        self.assertLess(ev.wilcox_pvalue(naive * 0.5, naive, "up", 0.05, 500), 0.05)

    def test_paired_test_detects_a_small_consistent_improvement(self):
        rng = np.random.default_rng(4)
        naive = rng.normal(0, 0.02, 800)
        model = naive * 0.97                                  # 3% less risk in every week
        self.assertGreater(ev.wilcox_pvalue(model, naive, "down", 0.05, 500), 0.2)        # independent: no power
        self.assertLess(ev.wilcox_pvalue(model, naive, "down", 0.05, 500, paired=True), 0.05)

    def test_utility_charges_turnover(self):
        y = np.random.default_rng(0).normal(0, 0.01, 100)
        still, moving = np.ones(100), np.tile([1.0, 1.1], 50)
        self.assertAlmostEqual(ev.utility(y, still) - ev.utility(y, moving), ev.COST_PER_TRADE * 0.1 * 99)


if __name__ == "__main__":
    unittest.main()
