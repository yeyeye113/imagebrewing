"""Risk Parity & Risk Budgeting — 风险平价/风险预算组合.

- Risk Parity: 每个资产对组合总风险的贡献相等
- Risk Budget: 按指定预算分配风险贡献

Reference: Maillard, Roncalli & Teïletche (2010) "The Properties of Equally Weighted Risk Contribution Portfolios".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .mean_variance import OptimizationResult, OptimizerConstraints, _build_bounds
from .risk_models import CovarianceEstimator

# ---------------------------------------------------------------------------
# Risk contribution helpers
# ---------------------------------------------------------------------------


def _risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Marginal risk contribution of each asset.

    RC_i = w_i * (Sigma @ w)_i / sqrt(w' Sigma w)
    Sum(RC) = portfolio volatility.
    """
    port_vol = np.sqrt(w @ cov @ w)
    if port_vol <= 0:
        return np.zeros_like(w)
    marginal = cov @ w
    return np.asarray(w * marginal / port_vol)


def _risk_contribution_pct(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Percentage risk contribution (sums to 1.0)."""
    rc = _risk_contributions(w, cov)
    total = rc.sum()
    if total <= 0:
        return np.ones_like(w) / len(w)
    return np.asarray(rc / total)


# ---------------------------------------------------------------------------
# Risk Parity
# ---------------------------------------------------------------------------


@dataclass
class RiskParityResult:
    """Result from risk parity optimization."""

    weights: OptimizationResult
    risk_contributions: np.ndarray  # absolute risk contribution per asset
    risk_pcts: np.ndarray  # percentage risk contribution
    rc_target: np.ndarray  # target risk contribution pct


class RiskParity:
    """Equal Risk Contribution (ERC) portfolio optimizer.

    Each asset contributes equally to total portfolio risk.

    Usage:
        rp = RiskParity()
        result = rp.optimize(returns_df)
        print(result.risk_pcts)  # should be ~equal
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

    def optimize(self, returns: pd.DataFrame) -> RiskParityResult:
        """Find the equal risk contribution portfolio."""
        estimator = CovarianceEstimator(method=self.cov_method, periods_per_year=self.periods_per_year)
        cov = estimator.fit(returns)
        symbols = list(returns.columns)
        n = len(symbols)
        target_pcts = np.ones(n) / n  # equal contribution

        return _solve_risk_budget(cov, symbols, target_pcts, self.constraints, self.periods_per_year, "risk_parity")


# ---------------------------------------------------------------------------
# Risk Budgeting
# ---------------------------------------------------------------------------


class RiskBudget:
    """Risk budgeting portfolio optimizer.

    Allocate risk according to specified budgets instead of equal.

    Usage:
        rb = RiskBudget()
        budgets = {"A": 0.4, "B": 0.3, "C": 0.3}  # must sum to 1.0
        result = rb.optimize(returns_df, budgets)
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

    def optimize(
        self,
        returns: pd.DataFrame,
        budgets: dict[str, float] | None = None,
    ) -> RiskParityResult:
        """Find the risk-budgeted portfolio.

        Args:
            returns: (T, n) DataFrame.
            budgets: dict of symbol -> target risk fraction. If None, equal risk.
        """
        symbols = list(returns.columns)
        n = len(symbols)

        if budgets is None:
            target_pcts = np.ones(n) / n
        else:
            total = sum(budgets.values())
            if total <= 0:
                raise ValueError("Budgets must sum to > 0")
            target_pcts = np.array([budgets.get(s, 0.0) / total for s in symbols])

        estimator = CovarianceEstimator(method=self.cov_method, periods_per_year=self.periods_per_year)
        cov = estimator.fit(returns)

        return _solve_risk_budget(cov, symbols, target_pcts, self.constraints, self.periods_per_year, "risk_budget")


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


def _solve_risk_budget(
    cov: np.ndarray,
    symbols: list[str],
    target_pcts: np.ndarray,
    constraints: OptimizerConstraints,
    periods_per_year: int,
    method_name: str,
) -> RiskParityResult:
    """Solve for weights that match the target risk contribution percentages.

    Minimizes: sum_i (RC_i% - target_i%)^2
    """
    n = len(cov)

    def objective(w):
        # Allow slightly negative weights during optimization for solver stability
        w_pos = np.maximum(w, 1e-12)
        rc_pct = _risk_contribution_pct(w_pos, cov)
        return float(np.sum((rc_pct - target_pcts) ** 2))

    # Use inverse volatility as initial guess
    vols = np.sqrt(np.diag(cov))
    vols[vols == 0] = 1.0
    x0 = 1.0 / vols
    x0 /= x0.sum()

    bounds = _build_bounds(n, constraints)
    # Relax constraint slightly: allow near-zero but not negative
    bounds = [(max(1e-8, b[0]), b[1]) for b in bounds]

    # Only equality constraint: sum to 1
    scipy_cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    result = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=scipy_cons,
        options={"maxiter": 2000, "ftol": 1e-14},
    )

    w = np.maximum(result.x, 0)
    w_sum = w.sum()
    if w_sum > 0:
        w /= w_sum

    # Compute final stats
    rc = _risk_contributions(w, cov)
    rc_pct = _risk_contribution_pct(w, cov)
    port_vol = float(np.sqrt(w @ cov @ w))
    mu_dummy = np.zeros(n)  # risk parity doesn't optimize for return

    opt_result = OptimizationResult(
        weights=w,
        symbols=symbols,
        expected_return=0.0,  # not optimized for return
        volatility=port_vol,
        sharpe=0.0,
        method=method_name,
    )

    return RiskParityResult(
        weights=opt_result,
        risk_contributions=rc,
        risk_pcts=rc_pct,
        rc_target=target_pcts,
    )


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def risk_parity_weights(
    returns: pd.DataFrame,
    cov_method: str = "ledoit_wolf",
) -> dict[str, float]:
    """One-liner: get risk parity weights as a dict."""
    rp = RiskParity(cov_method=cov_method)
    return rp.optimize(returns).weights.to_dict()


def risk_budget_weights(
    returns: pd.DataFrame,
    budgets: dict[str, float],
    cov_method: str = "ledoit_wolf",
) -> dict[str, float]:
    """One-liner: get risk budget weights as a dict."""
    rb = RiskBudget(cov_method=cov_method)
    return rb.optimize(returns, budgets).weights.to_dict()
