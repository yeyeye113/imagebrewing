"""Value-at-Risk calculator — Historical, Parametric (variance-covariance), Monte Carlo.

VaR answers: "What is the worst-case loss at confidence level X over horizon Y?"

Three methods with increasing sophistication:
  1. Historical  — resamples past returns directly (non-parametric, fat-tail friendly)
  2. Parametric  — assumes normal distribution (fast, but underestimates tail risk)
  3. Monte Carlo — simulates thousands of paths (most flexible, slowest)

Usage:
    from quanttrader.advanced_risk.var import VaR
    var = VaR(returns=portfolio_returns_series, confidence=0.95, horizon=1)
    result = var.historical()
    result = var.parametric()
    result = var.monte_carlo(n_sims=10000)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class VaRResult:
    """Unified output for all VaR methods."""

    method: str  # "historical" | "parametric" | "monte_carlo"
    confidence: float  # e.g. 0.95
    horizon: int  # trading days
    var: float  # worst-case loss as fraction of portfolio (negative = loss)
    cvar: float  # Conditional VaR (expected shortfall) — avg loss beyond VaR
    annual_var: float  # annualized VaR (scaled by sqrt(horizon) for parametric)
    metadata: dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"[{self.method.upper()}] VaR({self.confidence:.0%}, {self.horizon}d) = "
            f"{self.var:.4%}  |  CVaR = {self.cvar:.4%}  |  "
            f"Annual VaR = {self.annual_var:.4%}"
        )

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "confidence": self.confidence,
            "horizon": self.horizon,
            "var": self.var,
            "cvar": self.cvar,
            "annual_var": self.annual_var,
            **self.metadata,
        }


class VaR:
    """Value-at-Risk calculator.

    Args:
        returns: pd.Series of daily simple returns (e.g. equity.pct_change()).
        confidence: probability level, default 0.95 (95%).
        horizon: forward-looking period in trading days, default 1.
        seed: random seed for Monte Carlo reproducibility.
    """

    def __init__(
        self,
        returns: pd.Series,
        confidence: float = 0.95,
        horizon: int = 1,
        seed: int | None = None,
    ):
        if confidence <= 0.5 or confidence >= 1.0:
            raise ValueError(f"confidence must be in (0.5, 1.0), got {confidence}")
        if horizon < 1:
            raise ValueError(f"horizon must be >= 1, got {horizon}")

        self.returns = returns.dropna().values.astype(float)
        self.confidence = confidence
        self.horizon = horizon
        self._rng = np.random.default_rng(seed)

    # ── Historical ────────────────────────────────────────────────────
    def historical(self, n_bootstrap: int = 0) -> VaRResult:
        """Non-parametric VaR: rank historical returns, pick the (1-confidence) quantile.

        Args:
            n_bootstrap: if >0, bootstrap-sample to get a confidence interval on VaR itself.
        """
        r = self.returns
        # Scale to horizon by compounding daily returns
        if self.horizon > 1:
            r = self._compound_returns(r, self.horizon)

        alpha = 1 - self.confidence
        var_val = float(np.percentile(r, alpha * 100))
        cvar_val = float(r[r <= var_val].mean()) if np.any(r <= var_val) else var_val

        metadata = {}
        if n_bootstrap > 0:
            boot_vars = []
            for _ in range(n_bootstrap):
                sample = self._rng.choice(r, size=len(r), replace=True)
                boot_vars.append(np.percentile(sample, alpha * 100))
            metadata["var_ci_low"] = float(np.percentile(boot_vars, 2.5))
            metadata["var_ci_high"] = float(np.percentile(boot_vars, 97.5))

        return VaRResult(
            method="historical",
            confidence=self.confidence,
            horizon=self.horizon,
            var=var_val,
            cvar=cvar_val,
            annual_var=var_val * np.sqrt(TRADING_DAYS),
            metadata=metadata,
        )

    # ── Parametric (Variance-Covariance) ─────────────────────────────
    def parametric(self) -> VaRResult:
        """Parametric VaR assuming normal distribution: VaR = -(mu + z * sigma).

        Fast but underestimates tail risk in fat-tailed markets.
        """
        r = self.returns
        mu = r.mean()
        sigma = r.std(ddof=1)

        # z-score for the given confidence (upper tail)
        z = self._norm_ppf(self.confidence)

        # Horizon scaling (assumes iid returns)
        mu_h = mu * self.horizon
        sigma_h = sigma * np.sqrt(self.horizon)

        var_val = -(mu_h + z * sigma_h)

        # CVaR for normal distribution: E[X | X <= -VaR] = mu - sigma * phi(z) / alpha
        alpha = 1 - self.confidence
        z_alpha = self._norm_ppf(alpha)
        phi_z = self._norm_pdf(z_alpha)
        cvar_val = -(mu_h + sigma_h * phi_z / alpha)

        return VaRResult(
            method="parametric",
            confidence=self.confidence,
            horizon=self.horizon,
            var=float(var_val),
            cvar=float(cvar_val),
            annual_var=float(var_val * np.sqrt(TRADING_DAYS)),
            metadata={"mu_daily": float(mu), "sigma_daily": float(sigma)},
        )

    # ── Monte Carlo ──────────────────────────────────────────────────
    def monte_carlo(
        self,
        n_sims: int = 10_000,
        model: Literal["normal", "historical"] = "normal",
    ) -> VaRResult:
        """Simulate future PnL paths and derive VaR from the simulated distribution.

        Args:
            n_sims: number of simulation paths.
            model: "normal" fits mu/sigma and draws from normal;
                   "historical" resamples observed returns directly.
        """
        r = self.returns
        mu = r.mean()
        sigma = r.std(ddof=1)

        if model == "normal":
            # Simulate horizon-day compounded returns
            daily_sims = self._rng.normal(mu, sigma, size=(n_sims, self.horizon))
            sim_returns = np.prod(1 + daily_sims, axis=1) - 1
        else:
            # Historical resampling
            sim_returns = np.zeros(n_sims)
            for i in range(n_sims):
                sample = self._rng.choice(r, size=self.horizon, replace=True)
                sim_returns[i] = np.prod(1 + sample) - 1

        alpha = 1 - self.confidence
        var_val = float(np.percentile(sim_returns, alpha * 100))
        cvar_val = float(sim_returns[sim_returns <= var_val].mean()) if np.any(sim_returns <= var_val) else var_val

        return VaRResult(
            method="monte_carlo",
            confidence=self.confidence,
            horizon=self.horizon,
            var=var_val,
            cvar=cvar_val,
            annual_var=float(var_val * np.sqrt(TRADING_DAYS)),
            metadata={"n_sims": n_sims, "model": model},
        )

    # ── Helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _compound_returns(daily_returns: np.ndarray, horizon: int) -> np.ndarray:
        """Rolling compound of consecutive daily returns over `horizon` days."""
        if len(daily_returns) < horizon:
            return daily_returns
        n = len(daily_returns) - horizon + 1
        rolled = np.lib.stride_tricks.as_strided(
            daily_returns,
            shape=(n, horizon),
            strides=(daily_returns.strides[0], daily_returns.strides[0]),
        )
        return np.prod(1 + rolled, axis=1) - 1

    @staticmethod
    def _norm_ppf(p: float) -> float:
        """Rational approximation for the normal inverse CDF (Abramowitz & Stegun)."""
        # For p in (0, 1). Accurate to ~4.5e-4.
        if p <= 0 or p >= 1:
            raise ValueError(f"p must be in (0,1), got {p}")
        if p < 0.5:
            return -VaR._norm_ppf(1 - p)
        t = np.sqrt(-2 * np.log(1 - p))
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308
        return float(t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t))

    @staticmethod
    def _norm_pdf(x: float) -> float:
        return float(np.exp(-0.5 * x * x) / np.sqrt(2 * np.pi))
