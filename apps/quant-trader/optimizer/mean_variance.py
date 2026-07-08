"""Mean-Variance Optimization — Markowitz 组合优化.

支持:
- 最大夏普比 (tangency portfolio)
- 最小方差
- 目标收益优化
- 有效前沿
- 最大分散化

约束: 权重上下限、个股集中度、换手率、交易成本。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .risk_models import CovarianceEstimator

# ---------------------------------------------------------------------------
# Constraints & config
# ---------------------------------------------------------------------------


@dataclass
class OptimizerConstraints:
    """Optimization constraints.

    All weights are fractions of total portfolio (0.0 to 1.0).
    """

    w_min: float = 0.0  # per-asset lower bound
    w_max: float = 1.0  # per-asset upper bound
    max_concentration: float = 1.0  # max single-asset weight (same as w_max but explicit)
    sector_limits: dict[str, float] | None = None  # sector -> max total weight
    turnover_limit: float = 1.0  # max total turnover (sum of |delta_w|)
    transaction_cost: float = 0.0  # cost per unit turnover (e.g. 0.001 = 10bp)
    current_weights: np.ndarray | None = None  # for turnover calc


@dataclass
class OptimizationResult:
    """Result of a portfolio optimization."""

    weights: np.ndarray
    symbols: list[str]
    expected_return: float
    volatility: float
    sharpe: float
    method: str
    turnover: float = 0.0
    cost: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return dict(zip(self.symbols, self.weights.tolist()))

    def to_series(self) -> pd.Series:
        return pd.Series(self.weights, index=self.symbols, name="weight")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _annualized_stats(returns: pd.DataFrame, cov: np.ndarray, periods: int = 252):
    """(expected_returns, covariance) both annualized."""
    mu = returns.mean().values * periods
    return mu, cov


def _build_bounds(n: int, cons: OptimizerConstraints) -> list[tuple[float, float]]:
    w_lo = max(0.0, cons.w_min)
    w_hi = min(1.0, cons.w_max, cons.max_concentration)
    return [(w_lo, w_hi)] * n


def _build_constraints(
    n: int,
    cons: OptimizerConstraints,
    sector_map: dict[str, list[int]] | None = None,
) -> list[dict]:
    """Build scipy constraint list."""
    cs = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]  # fully invested

    # Turnover constraint
    if cons.turnover_limit < 1.0 and cons.current_weights is not None:
        cw = cons.current_weights
        cs.append(
            {
                "type": "ineq",
                "fun": lambda w: cons.turnover_limit - np.sum(np.abs(w - cw)),
            }
        )

    # Sector concentration
    if cons.sector_limits and sector_map:
        for sector, limit in cons.sector_limits.items():
            idxs = sector_map.get(sector, [])
            if idxs:
                cs.append(
                    {
                        "type": "ineq",
                        "fun": lambda w, idxs=idxs, lim=limit: lim - np.sum(w[idxs]),
                    }
                )

    return cs


def _portfolio_stats(w: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> tuple[float, float, float]:
    """(return, volatility, sharpe)."""
    ret = float(w @ mu)
    vol = float(np.sqrt(w @ cov @ w))
    sharpe = ret / vol if vol > 0 else 0.0
    return ret, vol, sharpe


def _neg_sharpe(w, mu, cov, cons: OptimizerConstraints):
    """Negative Sharpe ratio (for minimization) with cost penalty."""
    ret, vol, _ = _portfolio_stats(w, mu, cov)
    if vol <= 0:
        return 1e10
    cost = 0.0
    if cons.transaction_cost > 0 and cons.current_weights is not None:
        turnover = np.sum(np.abs(w - cons.current_weights))
        cost = cons.transaction_cost * turnover
    return -(ret - cost) / vol


# ---------------------------------------------------------------------------
# Core optimizer
# ---------------------------------------------------------------------------


class MeanVarianceOptimizer:
    """Markowitz mean-variance portfolio optimizer.

    Usage:
        opt = MeanVarianceOptimizer(risk_free_rate=0.02)
        result = opt.max_sharpe(returns_df)
        result = opt.min_variance(returns_df)
        result = opt.target_return(returns_df, target=0.15)
        frontier = opt.efficient_frontier(returns_df, n_points=20)
    """

    def __init__(
        self,
        risk_free_rate: float = 0.02,
        cov_method: str = "ledoit_wolf",
        constraints: OptimizerConstraints | None = None,
        periods_per_year: int = 252,
    ):
        self.risk_free_rate = risk_free_rate
        self.cov_method = cov_method
        self.constraints = constraints or OptimizerConstraints()
        self.periods_per_year = periods_per_year
        self._estimator = CovarianceEstimator(method=cov_method, periods_per_year=periods_per_year)

    def _prepare(self, returns: pd.DataFrame):
        """Estimate cov, compute annualized mu."""
        cov = self._estimator.fit(returns)
        mu, cov = _annualized_stats(returns, cov, self.periods_per_year)
        return mu, cov

    def _solve(
        self,
        objective,
        mu: np.ndarray,
        cov: np.ndarray,
        symbols: list[str],
        method_name: str,
        x0: np.ndarray | None = None,
    ) -> OptimizationResult:
        """Run scipy.optimize.minimize with constraints."""
        n = len(mu)
        cons = self.constraints
        bounds = _build_bounds(n, cons)
        scipy_cons = _build_constraints(n, cons)

        if x0 is None:
            x0 = np.ones(n) / n

        result = minimize(
            objective,
            x0,
            args=(mu, cov, cons),
            method="SLSQP",
            bounds=bounds,
            constraints=scipy_cons,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        w = np.clip(result.x, 0, None)
        w_sum = w.sum()
        if w_sum > 0:
            w /= w_sum

        ret, vol, sharpe = _portfolio_stats(w, mu, cov)

        turnover = 0.0
        cost = 0.0
        if cons.current_weights is not None:
            turnover = float(np.sum(np.abs(w - cons.current_weights)))
            cost = turnover * cons.transaction_cost

        return OptimizationResult(
            weights=w,
            symbols=symbols,
            expected_return=ret,
            volatility=vol,
            sharpe=sharpe,
            method=method_name,
            turnover=turnover,
            cost=cost,
        )

    def max_sharpe(self, returns: pd.DataFrame) -> OptimizationResult:
        """Maximum Sharpe ratio (tangency) portfolio."""
        mu, cov = self._prepare(returns)
        symbols = list(returns.columns)

        def obj(w, mu, cov, cons):
            return _neg_sharpe(w, mu, cov, cons)

        return self._solve(obj, mu, cov, symbols, "max_sharpe")

    def min_variance(self, returns: pd.DataFrame) -> OptimizationResult:
        """Minimum variance portfolio."""
        mu, cov = self._prepare(returns)
        symbols = list(returns.columns)

        def obj(w, mu, cov, cons):
            vol = np.sqrt(w @ cov @ w)
            cost = 0.0
            if cons.transaction_cost > 0 and cons.current_weights is not None:
                cost = cons.transaction_cost * np.sum(np.abs(w - cons.current_weights))
            return vol + cost

        return self._solve(obj, mu, cov, symbols, "min_variance")

    def target_return(
        self,
        returns: pd.DataFrame,
        target: float,
    ) -> OptimizationResult:
        """Minimize variance subject to a return target."""
        mu, cov = self._prepare(returns)
        symbols = list(returns.columns)
        n = len(mu)
        cons = self.constraints

        # Extra constraint: return >= target
        bounds = _build_bounds(n, cons)
        scipy_cons = _build_constraints(n, cons)
        scipy_cons.append({"type": "ineq", "fun": lambda w: w @ mu - target})

        x0 = np.ones(n) / n
        result = minimize(
            lambda w, mu, cov, cons: np.sqrt(w @ cov @ w),
            x0,
            args=(mu, cov, cons),
            method="SLSQP",
            bounds=bounds,
            constraints=scipy_cons,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        w = np.clip(result.x, 0, None)
        w_sum = w.sum()
        if w_sum > 0:
            w /= w_sum

        ret, vol, sharpe = _portfolio_stats(w, mu, cov)
        turnover = 0.0
        if cons.current_weights is not None:
            turnover = float(np.sum(np.abs(w - cons.current_weights)))

        return OptimizationResult(
            weights=w,
            symbols=symbols,
            expected_return=ret,
            volatility=vol,
            sharpe=sharpe,
            method=f"target_return({target:.2%})",
            turnover=turnover,
        )

    def efficient_frontier(
        self,
        returns: pd.DataFrame,
        n_points: int = 20,
    ) -> list[OptimizationResult]:
        """Compute the efficient frontier as a list of portfolios."""
        mu, cov = self._prepare(returns)

        # Min and max achievable returns
        n = len(mu)
        cons = self.constraints
        bounds = _build_bounds(n, cons)
        scipy_cons = _build_constraints(n, cons)

        # Min var portfolio return
        min_res = self.min_variance(returns)

        # Max return portfolio (maximize return = minimize -return)
        def neg_ret(w, mu, cov, cons):
            return -(w @ mu)

        max_ret_res = self._solve(neg_ret, mu, cov, list(returns.columns), "max_return")

        ret_lo = min_res.expected_return
        ret_hi = max_ret_res.expected_return

        if ret_hi <= ret_lo:
            return [min_res]

        targets = np.linspace(ret_lo, ret_hi, n_points)
        frontier = []
        for t in targets:
            try:
                pt = self.target_return(returns, target=t)
                frontier.append(pt)
            except Exception:
                continue
        return frontier


# ---------------------------------------------------------------------------
# Max Diversification
# ---------------------------------------------------------------------------


class MaxDiversification:
    """Maximum Diversification Portfolio.

    Maximizes the diversification ratio: weighted average volatility / portfolio volatility.
    Equivalent to finding the most "diversified" combination.
    """

    def __init__(
        self,
        cov_method: str = "ledoit_wolf",
        constraints: OptimizerConstraints | None = None,
        periods_per_year: int = 252,
    ):
        self.cov_method = cov_method
        self.constraints = constraints or OptimizerConstraints()
        self.periods_per_year = periods_per_year

    def optimize(self, returns: pd.DataFrame) -> OptimizationResult:
        """Find the maximum diversification portfolio."""
        estimator = CovarianceEstimator(method=self.cov_method, periods_per_year=self.periods_per_year)
        cov = estimator.fit(returns)
        vols = np.sqrt(np.diag(cov))
        symbols = list(returns.columns)
        n = len(symbols)
        cons = self.constraints

        # Diversification ratio = (w' @ sigma) / sqrt(w' @ Cov @ w)
        # Maximize = minimize negative
        def neg_div_ratio(w, _mu=None, _cov=None, _cons=None):
            w_vols = w @ vols
            port_vol = np.sqrt(w @ cov @ w)
            if port_vol <= 0:
                return 1e10
            return -w_vols / port_vol

        bounds = _build_bounds(n, cons)
        scipy_cons = _build_constraints(n, cons)
        x0 = np.ones(n) / n

        result = minimize(
            neg_div_ratio,
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

        mu = returns.mean().values * self.periods_per_year
        ret, vol, sharpe = _portfolio_stats(w, mu, cov)
        div_ratio = -result.fun if result.fun < 0 else 0.0

        return OptimizationResult(
            weights=w,
            symbols=symbols,
            expected_return=ret,
            volatility=vol,
            sharpe=sharpe,
            method=f"max_diversification(dr={div_ratio:.3f})",
        )


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def max_sharpe_weights(
    returns: pd.DataFrame,
    risk_free_rate: float = 0.02,
    cov_method: str = "ledoit_wolf",
    w_min: float = 0.0,
    w_max: float = 1.0,
) -> dict[str, float]:
    """One-liner: get max-Sharpe weights as a dict."""
    cons = OptimizerConstraints(w_min=w_min, w_max=w_max)
    opt = MeanVarianceOptimizer(risk_free_rate=risk_free_rate, cov_method=cov_method, constraints=cons)
    return opt.max_sharpe(returns).to_dict()


def min_variance_weights(
    returns: pd.DataFrame,
    cov_method: str = "ledoit_wolf",
    w_min: float = 0.0,
    w_max: float = 1.0,
) -> dict[str, float]:
    """One-liner: get min-variance weights as a dict."""
    cons = OptimizerConstraints(w_min=w_min, w_max=w_max)
    opt = MeanVarianceOptimizer(cov_method=cov_method, constraints=cons)
    return opt.min_variance(returns).to_dict()


def efficient_frontier(
    returns: pd.DataFrame,
    n_points: int = 20,
    risk_free_rate: float = 0.02,
    cov_method: str = "ledoit_wolf",
) -> list[dict]:
    """Compute efficient frontier, return as list of dicts for API/CLI."""
    opt = MeanVarianceOptimizer(risk_free_rate=risk_free_rate, cov_method=cov_method)
    results = opt.efficient_frontier(returns, n_points)
    return [
        {
            "return": r.expected_return,
            "volatility": r.volatility,
            "sharpe": r.sharpe,
            "weights": r.to_dict(),
        }
        for r in results
    ]
