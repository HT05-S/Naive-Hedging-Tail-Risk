"""The six hedge-ratio models of Cao & Conlon (2025), estimated on a rolling window.

Every model answers one question: given the last `window` weeks of spot returns s
and futures returns f, how many units of futures (b) should hedge one unit of spot?

  naive    b = 1
  ols      minimum variance: cov(s, f) / var(f)
  sv       minimum semivariance of the hedged return
  hs       minimum historical-simulation VaR or CVaR
  cfe      minimum Cornish-Fisher VaR or CVaR
  copula   minimum VaR or CVaR on 10,000 draws from a fitted Clayton copula

'Downside' is the lower tail of s - b*f (the short hedger). 'Upside' is its upper
tail, which is the lower tail of -s + b*f (the long hedger). Models other than
naive and ols give a different b for each side; hs, cfe and copula also give a
different b for each risk measure (VaR, CVaR) and level (10%, 5%, 1%).

The risk-minimising b is found by grid search over GRID, as the paper describes
for semivariance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from scipy.optimize import minimize_scalar
from scipy.stats import norm, rankdata

ALPHAS = (0.10, 0.05, 0.01)
SIDES = ("down", "up")
MEASURES = ("VaR", "CVaR")
GRID = np.round(np.arange(0.0, 2.0001, 0.01), 2)
SCENARIOS = [(side, meas, a) for side in SIDES for meas in MEASURES for a in ALPHAS]
MODELS = ("naive", "ols", "hs", "cfe", "copula", "sv")
MODEL_LABELS = {"naive": "Naïve", "ols": "OLS", "hs": "HS", "cfe": "CFE", "copula": "Copula", "sv": "Semivariance"}


# ---------------------------------------------------------------- tail risk of a sample

def tail_index(n: int, alpha: float) -> tuple[int, float]:
    """Position of the alpha-quantile in a sorted sample of size n (linear interpolation)."""
    h = (n - 1) * alpha
    k = int(np.floor(h))
    return k, h - k


def lower_tail(ys: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray]:
    """VaR and CVaR (as positive losses) of the lower tail. `ys` is sorted ascending along axis 0.

    VaR is minus the alpha-quantile. CVaR is minus the mean of the observations at or below it.
    """
    k, frac = tail_index(ys.shape[0], alpha)
    q = ys[k] + (ys[k + 1] - ys[k]) * frac
    return -q, -ys[: k + 1].mean(axis=0)


def semivariance(y: np.ndarray, axis: int = 0) -> np.ndarray:
    """Mean squared shortfall below a target return of zero."""
    return np.mean(np.minimum(y, 0.0) ** 2, axis=axis)


# ---------------------------------------------------------------- Cornish-Fisher

def cf_risk(sd, skew, exk, alpha: float):
    """Cornish-Fisher VaR and CVaR (paper equations 7 and 8), as positive losses."""
    c = norm.ppf(alpha)
    phi = norm.pdf(c)
    m1 = -phi / alpha
    m2 = 1.0 - c * phi / alpha
    m3 = -(c ** 2 + 2.0) * phi / alpha
    var = -sd * (c + (c ** 2 - 1) * skew / 6 + (c ** 3 - 3 * c) * exk / 24 - (2 * c ** 3 - 5 * c) * skew ** 2 / 36)
    cvar = -sd * (m1 + (m2 - 1) * skew / 6 + (m3 - 3 * m1) * exk / 24 - (2 * m3 - 5 * m1) * skew ** 2 / 36)
    return var, cvar


# ---------------------------------------------------------------- Clayton copula

def clayton_theta(u: np.ndarray, v: np.ndarray) -> float:
    """Maximum-likelihood Clayton parameter from pseudo-observations."""
    lu, lv = np.log(u), np.log(v)

    def nll(t):
        a = np.exp(-t * lu) + np.exp(-t * lv) - 1.0
        return -np.sum(np.log1p(t) - (1 + t) * (lu + lv) - (2 + 1 / t) * np.log(a))

    return float(minimize_scalar(nll, bounds=(1e-3, 60.0), method="bounded").x)


def clayton_draws(theta: float, u1: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Second uniform of a Clayton pair, by conditional inversion."""
    return (u1 ** (-theta) * (w ** (-theta / (1 + theta)) - 1.0) + 1.0) ** (-1.0 / theta)


# ---------------------------------------------------------------- rolling estimation

def _argbest(risk: np.ndarray) -> np.ndarray:
    """Grid value with the lowest risk, for risk shaped (..., len(GRID))."""
    return GRID[np.nanargmin(risk, axis=-1)]


def estimate(s: np.ndarray, f: np.ndarray, window: int = 52, n_sim: int = 10_000, seed: int = 0,
             copula: bool = True) -> pd.DataFrame:
    """Hedge ratios from every window of `window` consecutive observations.

    Row j holds the ratios estimated on observations j-window+1 .. j. Columns are
    (model, side, measure, alpha); naive, ols and sv repeat across the columns they do not depend on.
    """
    s, f = np.asarray(s, float), np.asarray(f, float)
    S = sliding_window_view(s, window)          # (n_win, window)
    F = sliding_window_view(f, window)
    n_win = S.shape[0]
    rng = np.random.default_rng(seed)
    u1, w = rng.uniform(1e-9, 1 - 1e-9, n_sim), rng.uniform(1e-9, 1 - 1e-9, n_sim)   # common random numbers

    col = {m: {sc: np.full(n_win, np.nan) for sc in SCENARIOS} for m in MODELS}
    for sc in SCENARIOS:
        col["naive"][sc][:] = 1.0

    fc = F - F.mean(axis=1, keepdims=True)
    ols = (fc * (S - S.mean(axis=1, keepdims=True))).sum(axis=1) / (fc ** 2).sum(axis=1)
    for sc in SCENARIOS:
        col["ols"][sc] = ols

    for lo in range(0, n_win, 250):             # chunks keep memory modest
        sl = slice(lo, min(lo + 250, n_win))
        Y = S[sl, :, None] - F[sl, :, None] * GRID            # (chunk, window, grid)
        Ys = np.sort(Y, axis=1)
        mu = Y.mean(axis=1, keepdims=True)
        sd = Y.std(axis=1, ddof=1)
        z = (Y - mu) / Y.std(axis=1, keepdims=True)
        skew, exk = (z ** 3).mean(axis=1), (z ** 4).mean(axis=1) - 3.0
        for side in SIDES:
            sign = 1.0 if side == "down" else -1.0
            ys = np.moveaxis(Ys if side == "down" else -Ys[:, ::-1, :], 1, 0)   # sorted lower tail of the side
            sv_b = _argbest(semivariance(sign * Y, axis=1))
            for a in ALPHAS:
                v, c = lower_tail(ys, a)
                cv, cc = cf_risk(sd, sign * skew, exk, a)
                col["hs"][(side, "VaR", a)][sl], col["hs"][(side, "CVaR", a)][sl] = _argbest(v), _argbest(c)
                col["cfe"][(side, "VaR", a)][sl], col["cfe"][(side, "CVaR", a)][sl] = _argbest(cv), _argbest(cc)
                for meas in MEASURES:
                    col["sv"][(side, meas, a)][sl] = sv_b

    if copula:
        ks = sorted({k for a in ALPHAS for k in tail_index(n_sim, a)[:1]} | {tail_index(n_sim, a)[0] + 1 for a in ALPHAS})
        kth = sorted(set(ks) | {n_sim - 1 - k for k in ks})
        for j in range(n_win):
            sw, fw = S[j], F[j]
            us, uf = rankdata(sw) / (window + 1), rankdata(fw) / (window + 1)
            theta = clayton_theta(uf, us)
            u2 = clayton_draws(theta, u1, w)
            fsim, ssim = np.quantile(fw, u1), np.quantile(sw, u2)     # inverse empirical marginals
            Yp = np.partition(ssim[:, None] - fsim[:, None] * GRID, kth, axis=0)
            for side in SIDES:
                for a in ALPHAS:
                    k, frac = tail_index(n_sim, a)
                    if side == "down":
                        q = Yp[k] + (Yp[k + 1] - Yp[k]) * frac
                        var, cvar = -q, -Yp[: k + 1].mean(axis=0)
                    else:
                        hi, hi2 = n_sim - 1 - k, n_sim - 2 - k
                        q = Yp[hi] + (Yp[hi2] - Yp[hi]) * frac
                        var, cvar = q, Yp[hi:].mean(axis=0)
                    col["copula"][(side, "VaR", a)][j] = GRID[np.argmin(var)]
                    col["copula"][(side, "CVaR", a)][j] = GRID[np.argmin(cvar)]

    out = pd.DataFrame({(m,) + sc: col[m][sc] for m in MODELS for sc in SCENARIOS})
    out.columns.names = ["model", "side", "measure", "alpha"]
    out.index = np.arange(window - 1, len(s))    # position of the last observation in each window
    return out
