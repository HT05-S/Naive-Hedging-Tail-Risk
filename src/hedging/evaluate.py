"""Hedging effectiveness, the Wilcox et al. (2014) quantile test and mean-variance utility."""
from __future__ import annotations

import numpy as np
from scipy.stats import beta

from .models import lower_tail, semivariance

RISK_AVERSION = 6.0
COST_PER_TRADE = 0.0003       # 0.03% of turnover, as in the paper


def side_adjust(y: np.ndarray, side: str) -> np.ndarray:
    """Downside looks at the lower tail of y; upside at the lower tail of -y."""
    return y if side == "down" else -y


def risk(y: np.ndarray, side: str, measure: str, alpha: float) -> float:
    """Historical-simulation VaR or CVaR (positive loss), or semivariance ('SV'), of one tail."""
    x = side_adjust(np.asarray(y, float), side)
    if measure == "SV":
        return float(semivariance(x))
    var, cvar = lower_tail(np.sort(x), alpha)
    return float(var if measure == "VaR" else cvar)


def effectiveness(y: np.ndarray, s: np.ndarray, side: str, measure: str, alpha: float) -> float:
    """HE = 1 - risk(hedged) / risk(unhedged)."""
    return 1.0 - risk(y, side, measure, alpha) / risk(s, side, measure, alpha)


def variance_effectiveness(y: np.ndarray, s: np.ndarray) -> float:
    return 1.0 - np.var(y, ddof=1) / np.var(s, ddof=1)


def hd_weights(n: int, q: float) -> np.ndarray:
    """Harrell-Davis (1982) weights on the order statistics for the q-quantile."""
    a, b = (n + 1) * q, (n + 1) * (1 - q)
    edges = beta.cdf(np.arange(n + 1) / n, a, b)
    return np.diff(edges)


def wilcox_pvalue(y_model: np.ndarray, y_naive: np.ndarray, side: str, alpha: float,
                  n_boot: int = 2000, seed: int = 0, paired: bool = False) -> float:
    """One-sided percentile-bootstrap p-value that the model has LOWER tail risk than the naive hedge.

    Tail risk is the Harrell-Davis alpha-quantile of the side-adjusted hedged return. A small p-value
    means the model beats the naive hedge; values above 0.5 mean the naive hedge had the smaller tail risk.

    paired=False resamples the two series independently, as in Wilcox et al. (2014) and the paper.
    paired=True resamples whole weeks, keeping each week's two hedged returns together. The two series
    come from the same weeks and are highly correlated, so this version is the more powerful one.
    """
    xm, xn = side_adjust(np.asarray(y_model, float), side), side_adjust(np.asarray(y_naive, float), side)
    rng = np.random.default_rng(seed)
    wm, wn = hd_weights(len(xm), alpha), hd_weights(len(xn), alpha)
    im = rng.integers(0, len(xm), (n_boot, len(xm)))
    i_n = im if paired else rng.integers(0, len(xn), (n_boot, len(xn)))
    qm = np.sort(xm[im], axis=1) @ wm
    qn = np.sort(xn[i_n], axis=1) @ wn
    d = qm - qn                                   # > 0: model's lower quantile is higher, i.e. less tail risk
    return float(np.mean(d < 0) + 0.5 * np.mean(d == 0))


def utility(y: np.ndarray, b: np.ndarray) -> float:
    """Mean-variance utility net of total transaction costs (paper equation 16)."""
    turnover = np.abs(np.diff(b)).sum()
    return float(np.mean(y) - COST_PER_TRADE * turnover - 0.5 * RISK_AVERSION * np.var(y, ddof=1))
