"""Black-Litterman Model — 结合市场均衡与主观观点的组合优化.

将市场隐含均衡收益与投资者主观观点(如 LLM 信号)融合，
输出后验收益估计，再用均值-方差框架求解权重。

Reference: Black & Litterman (1992) "Global Portfolio Optimization".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .mean_variance import MeanVarianceOptimizer, OptimizationResult, OptimizerConstraints
from .risk_models import CovarianceEstimator

# ---------------------------------------------------------------------------
# View structure
# ---------------------------------------------------------------------------


@dataclass
class BLView:
    """A single investor view.

    - assets: list of symbol names involved in this view
    - weights: relative weights among those assets (e.g. [1, -1] for a pair trade)
    - expected_return: the view's expected excess return
    - confidence: 0..1, how confident in this view (1 = very confident)

    Examples:
        # Absolute view: "stock A returns 10%"
        BLView(assets=["A"], weights=[1.0], expected_return=0.10, confidence=0.7)

        # Relative view: "A outperforms B by 5%"
        BLView(assets=["A", "B"], weights=[1.0, -1.0], expected_return=0.05, confidence=0.5)
    """

    assets: list[str]
    weights: list[float]
    expected_return: float
    confidence: float = 0.5


@dataclass
class BLResult:
    """Result of Black-Litterman optimization."""

    weights: OptimizationResult
    equilibrium_returns: np.ndarray  # market-implied returns (pi)
    posterior_returns: np.ndarray  # combined returns after views
    views: list[BLView]
    symbols: list[str]

    def to_dict(self) -> dict:
        return {
            "weights": self.weights.to_dict(),
            "equilibrium_returns": dict(zip(self.symbols, self.equilibrium_returns.tolist())),
            "posterior_returns": dict(zip(self.symbols, self.posterior_returns.tolist())),
        }


# ---------------------------------------------------------------------------
# Core Black-Litterman
# ---------------------------------------------------------------------------


class BlackLitterman:
    """Black-Litterman portfolio optimizer.

    Usage:
        bl = BlackLitterman(risk_aversion=2.5, tau=0.05)
        views = [BLView(["A"], [1.0], 0.10, 0.7)]
        result = bl.optimize(returns_df, views, market_caps)
        posterior_returns = result.posterior_returns
        weights = result.weights.to_dict()
    """

    def __init__(
        self,
        risk_aversion: float = 2.5,
        tau: float = 0.05,
        cov_method: str = "ledoit_wolf",
        constraints: OptimizerConstraints | None = None,
        periods_per_year: int = 252,
    ):
        """
        Args:
            risk_aversion: delta — risk aversion parameter. Higher = more conservative.
                           Typical: 1.0 to 5.0.
            tau: uncertainty scaling for the prior. Small (0.01..0.1) means high
                 confidence in equilibrium. Typical: 0.05.
            cov_method: covariance estimation method.
            constraints: weight constraints for the final optimization.
            periods_per_year: trading days per year.
        """
        self.delta = risk_aversion
        self.tau = tau
        self.cov_method = cov_method
        self.constraints = constraints or OptimizerConstraints()
        self.periods_per_year = periods_per_year

    def _implied_equilibrium_returns(
        self,
        cov: np.ndarray,
        market_caps: np.ndarray,
    ) -> np.ndarray:
        """Compute market-implied excess returns: pi = delta * Sigma @ w_mkt.

        market_caps: array of market capitalizations (same order as cov rows).
        """
        total = market_caps.sum()
        if total <= 0:
            raise ValueError("Market caps must sum to > 0")
        w_mkt = market_caps / total
        return np.asarray(self.delta * cov @ w_mkt)

    def _build_view_matrices(
        self,
        views: list[BLView],
        symbols: list[str],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Build P (pick matrix), Q (view returns), omega (view uncertainty).

        P: (k, n) — each row is a view expressed over n assets
        Q: (k,)   — expected returns for each view
        omega: (k, k) — diagonal uncertainty matrix
        """
        n = len(symbols)
        k = len(views)
        sym_idx = {s: i for i, s in enumerate(symbols)}

        P = np.zeros((k, n))
        Q = np.zeros(k)
        omega_diag = np.zeros(k)

        for i, view in enumerate(views):
            Q[i] = view.expected_return
            for asset, w in zip(view.assets, view.weights):
                if asset not in sym_idx:
                    raise ValueError(f"View asset '{asset}' not in symbol list")
                P[i, sym_idx[asset]] = w

            # omega_i = (1/confidence - 1) * tau * p_i @ Sigma @ p_i.T
            # Higher confidence = lower uncertainty
            confidence = np.clip(view.confidence, 0.01, 0.99)
            omega_diag[i] = (1.0 / confidence - 1.0) * self.tau

        omega = np.diag(omega_diag)
        return P, Q, omega

    def optimize(
        self,
        returns: pd.DataFrame,
        views: list[BLView],
        market_caps: dict[str, float] | np.ndarray | None = None,
    ) -> BLResult:
        """Run Black-Litterman optimization.

        Args:
            returns: (T, n) DataFrame of asset returns.
            views: list of BLView.
            market_caps: market cap per asset. If None, uses equal caps
                        (degenerates to reverse optimization with equal weights).

        Returns:
            BLResult with posterior returns and optimal weights.
        """
        symbols = list(returns.columns)
        n = len(symbols)

        # Estimate covariance
        estimator = CovarianceEstimator(method=self.cov_method, periods_per_year=self.periods_per_year)
        cov = estimator.fit(returns)

        # Market cap weights
        if market_caps is None:
            caps = np.ones(n)
        elif isinstance(market_caps, dict):
            caps = np.array([market_caps.get(s, 1.0) for s in symbols])
        else:
            caps = np.asarray(market_caps, dtype=float)

        # Step 1: Implied equilibrium returns (pi)
        pi = self._implied_equilibrium_returns(cov, caps)

        # Step 2: Build view matrices
        if not views:
            # No views — just use equilibrium
            posterior_mu = pi
        else:
            P, Q, omega = self._build_view_matrices(views, symbols)

            # Step 3: Posterior return = [(tau*Sigma)^-1 + P'Omega^-1 P]^-1
            #                             * [(tau*Sigma)^-1 pi + P'Omega^-1 Q]
            tau_cov = self.tau * cov
            tau_cov_inv = np.linalg.inv(tau_cov)
            omega_inv = np.linalg.inv(omega)

            # M = (tau*Sigma)^-1 + P' * Omega^-1 * P
            M = tau_cov_inv + P.T @ omega_inv @ P
            M_inv = np.linalg.inv(M)

            # posterior_mu = M_inv @ [(tau*Sigma)^-1 @ pi + P' @ Omega^-1 @ Q]
            posterior_mu = M_inv @ (tau_cov_inv @ pi + P.T @ omega_inv @ Q)

        # Step 4: Optimize with posterior returns
        opt = MeanVarianceOptimizer(
            risk_free_rate=0.0,  # returns are already excess
            cov_method="sample",  # use pre-computed cov
            constraints=self.constraints,
            periods_per_year=self.periods_per_year,
        )

        # Override the optimizer's internal stats with our BL posterior
        # We need to pass returns through but override mu and cov
        # Use a synthetic approach: create a dummy optimize that uses posterior_mu
        from scipy.optimize import minimize

        def neg_sharpe(w):
            ret = float(w @ posterior_mu)
            vol = float(np.sqrt(w @ cov @ w))
            if vol <= 0:
                return 1e10
            return -(ret / vol)

        bounds = [(max(0.0, self.constraints.w_min), min(1.0, self.constraints.w_max))] * n
        scipy_cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        x0 = caps / caps.sum()
        result = minimize(
            neg_sharpe,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=scipy_cons,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        w = np.clip(result.x, 0, None)
        w_sum = w.sum()
        if w_sum > 0:
            w /= w_sum

        ret = float(w @ posterior_mu)
        vol = float(np.sqrt(w @ cov @ w))
        sharpe = ret / vol if vol > 0 else 0.0

        opt_result = OptimizationResult(
            weights=w,
            symbols=symbols,
            expected_return=ret,
            volatility=vol,
            sharpe=sharpe,
            method="black_litterman",
        )

        return BLResult(
            weights=opt_result,
            equilibrium_returns=pi,
            posterior_returns=posterior_mu,
            views=views,
            symbols=symbols,
        )
