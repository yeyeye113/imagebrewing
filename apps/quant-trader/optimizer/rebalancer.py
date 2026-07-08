"""Rebalancer — 组合再平衡引擎.

支持:
- 定期再平衡 (calendar-based)
- 阈值触发再平衡 (threshold-based)
- 最小交易过滤 (忽略小变动)
- 交易成本约束
- 换手率控制

集成均值-方差、风险平价、BL 等优化器。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .black_litterman import BlackLitterman
from .mean_variance import MeanVarianceOptimizer, OptimizerConstraints
from .risk_parity import RiskParity

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class RebalanceConfig:
    """Rebalancing configuration.

    method:
        - "periodic": rebalance every N days regardless
        - "threshold": rebalance when any weight drifts beyond threshold
        - "periodic_threshold": both — whichever triggers first
        - "none": optimize once, no rebalancing

    optimizer:
        - "max_sharpe", "min_variance", "risk_parity", "equal_weight", "black_litterman"
    """

    method: Literal["periodic", "threshold", "periodic_threshold", "none"] = "periodic_threshold"
    frequency_days: int = 21  # ~monthly
    drift_threshold: float = 0.05  # 5% drift triggers rebalance
    min_trade_pct: float = 0.01  # ignore trades < 1% of portfolio
    max_turnover: float = 0.50  # cap total turnover per rebalance
    transaction_cost: float = 0.001  # 10bp per unit traded
    optimizer: str = "risk_parity"
    cov_method: str = "ledoit_wolf"
    w_min: float = 0.0
    w_max: float = 0.40  # no single stock > 40%
    risk_free_rate: float = 0.02


@dataclass
class RebalanceAction:
    """A single trade in a rebalance event."""

    symbol: str
    side: str  # "BUY" or "SELL"
    weight_delta: float  # change in weight (+buy, -sell)
    trade_cost: float  # estimated cost


@dataclass
class RebalanceResult:
    """Result of a single rebalance event."""

    date: object
    old_weights: dict[str, float]
    new_weights: dict[str, float]
    actions: list[RebalanceAction]
    turnover: float
    total_cost: float
    reason: str  # "periodic", "threshold", "both"


@dataclass
class RebalanceSeries:
    """Full rebalance backtest result."""

    events: list[RebalanceResult]
    weight_history: pd.DataFrame  # date x symbol weights
    turnover_history: pd.Series  # per-event turnover
    cost_history: pd.Series  # per-event cost
    total_cost: float
    n_rebalances: int


# ---------------------------------------------------------------------------
# Rebalancer
# ---------------------------------------------------------------------------


class Rebalancer:
    """Portfolio rebalancing engine.

    Usage:
        rb = Rebalancer(RebalanceConfig(optimizer="risk_parity", frequency_days=21))
        series = rb.run(returns_df)

        # Single rebalance
        result = rb.rebalance(current_weights, returns_df, date=today)
    """

    def __init__(self, config: RebalanceConfig | None = None):
        self.config = config or RebalanceConfig()

    def _optimize(self, returns: pd.DataFrame, current_weights: dict[str, float] | None = None) -> dict[str, float]:
        """Run the configured optimizer to get target weights."""
        cfg = self.config
        cons = OptimizerConstraints(
            w_min=cfg.w_min,
            w_max=cfg.w_max,
            turnover_limit=cfg.max_turnover,
            transaction_cost=cfg.transaction_cost,
        )

        # Set current weights for turnover constraint
        if current_weights:
            symbols = list(returns.columns)
            cons.current_weights = np.array([current_weights.get(s, 0.0) for s in symbols])

        opt_name = cfg.optimizer.lower()

        if opt_name in ("equal_weight", "equal", "ew"):
            n = len(returns.columns)
            return {s: 1.0 / n for s in returns.columns}

        if opt_name in ("risk_parity", "riskparity", "rp"):
            rp = RiskParity(cov_method=cfg.cov_method, constraints=cons)
            return rp.optimize(returns).weights.to_dict()

        if opt_name in ("min_variance", "minvar", "min_var"):
            mvo = MeanVarianceOptimizer(cov_method=cfg.cov_method, constraints=cons, periods_per_year=252)
            return mvo.min_variance(returns).to_dict()

        if opt_name in ("max_sharpe", "sharpe", "tangency"):
            mvo = MeanVarianceOptimizer(
                risk_free_rate=cfg.risk_free_rate,
                cov_method=cfg.cov_method,
                constraints=cons,
            )
            return mvo.max_sharpe(returns).to_dict()

        if opt_name in ("black_litterman", "bl"):
            # Without explicit views, BL degenerates to equilibrium
            bl = BlackLitterman(cov_method=cfg.cov_method, constraints=cons)
            result = bl.optimize(returns, views=[])
            return result.weights.to_dict()

        raise ValueError(f"Unknown optimizer: {cfg.optimizer}")

    def _should_rebalance(
        self,
        current_weights: dict[str, float],
        target_weights: dict[str, float],
        days_since_last: int,
    ) -> tuple[bool, str]:
        """Check if rebalance should occur based on config method."""
        cfg = self.config

        # Check drift
        max_drift = 0.0
        for sym in set(list(current_weights.keys()) + list(target_weights.keys())):
            drift = abs(current_weights.get(sym, 0.0) - target_weights.get(sym, 0.0))
            max_drift = max(max_drift, drift)

        drifted = max_drift >= cfg.drift_threshold
        periodic = days_since_last >= cfg.frequency_days

        if cfg.method == "none":
            return False, "none"
        if cfg.method == "periodic":
            return periodic, "periodic"
        if cfg.method == "threshold":
            return drifted, "threshold"
        # periodic_threshold
        if periodic and drifted:
            return True, "both"
        if periodic:
            return True, "periodic"
        if drifted:
            return True, "threshold"
        return False, ""

    def _compute_actions(
        self,
        old_weights: dict[str, float],
        new_weights: dict[str, float],
    ) -> tuple[list[RebalanceAction], float, float]:
        """Compute trades and costs from weight changes."""
        cfg = self.config
        symbols = sorted(set(list(old_weights.keys()) + list(new_weights.keys())))

        actions = []
        total_turnover = 0.0
        total_cost = 0.0

        for sym in symbols:
            old_w = old_weights.get(sym, 0.0)
            new_w = new_weights.get(sym, 0.0)
            delta = new_w - old_w

            # Skip tiny trades
            if abs(delta) < cfg.min_trade_pct:
                continue

            total_turnover += abs(delta)
            cost = abs(delta) * cfg.transaction_cost
            total_cost += cost

            side = "BUY" if delta > 0 else "SELL"
            actions.append(
                RebalanceAction(
                    symbol=sym,
                    side=side,
                    weight_delta=delta,
                    trade_cost=cost,
                )
            )

        return actions, total_turnover, total_cost

    def rebalance(
        self,
        current_weights: dict[str, float],
        returns: pd.DataFrame,
        date: object = None,
        force: bool = False,
    ) -> RebalanceResult | None:
        """Execute a single rebalance decision.

        Args:
            current_weights: symbol -> weight (must sum ~1.0)
            returns: recent returns for optimization (enough history)
            date: timestamp for this rebalance
            force: if True, rebalance regardless of method/threshold

        Returns:
            RebalanceResult if rebalance needed, None otherwise.
        """
        symbols = list(returns.columns)
        # Ensure current_weights covers all symbols
        for s in symbols:
            if s not in current_weights:
                current_weights[s] = 0.0

        target_weights = self._optimize(returns, current_weights)

        if not force:
            should, reason = self._should_rebalance(current_weights, target_weights, 999)
            if not should:
                return None
        else:
            reason = "forced"

        actions, turnover, cost = self._compute_actions(current_weights, target_weights)

        return RebalanceResult(
            date=date,
            old_weights=current_weights,
            new_weights=target_weights,
            actions=actions,
            turnover=turnover,
            total_cost=cost,
            reason=reason,
        )

    def run(
        self,
        returns: pd.DataFrame,
        lookback: int = 60,
        initial_weights: dict[str, float] | None = None,
    ) -> RebalanceSeries:
        """Full rebalance backtest over a returns series.

        Args:
            returns: (T, n) daily returns DataFrame.
            lookback: number of days of history for each optimization.
            initial_weights: starting weights. If None, equal weight.

        Returns:
            RebalanceSeries with all events and history.
        """
        symbols = list(returns.columns)
        n = len(symbols)
        dates = returns.index

        if initial_weights is None:
            weights = {s: 1.0 / n for s in symbols}
        else:
            weights = {s: initial_weights.get(s, 0.0) for s in symbols}

        events: list[RebalanceResult] = []
        weight_records = []
        turnover_records = []
        cost_records = []
        last_rebalance_idx = -self.config.frequency_days  # allow first rebalance

        for i in range(lookback, len(dates)):
            date = dates[i]

            # Check if rebalance needed
            days_since = i - last_rebalance_idx

            # Get lookback window
            window = returns.iloc[max(0, i - lookback) : i]
            if len(window) < 20:
                continue

            target_weights = self._optimize(window, weights)
            should, reason = self._should_rebalance(weights, target_weights, days_since)

            if should:
                actions, turnover, cost = self._compute_actions(weights, target_weights)
                event = RebalanceResult(
                    date=date,
                    old_weights=dict(weights),
                    new_weights=target_weights,
                    actions=actions,
                    turnover=turnover,
                    total_cost=cost,
                    reason=reason,
                )
                events.append(event)
                weights = target_weights
                last_rebalance_idx = i
                turnover_records.append((date, turnover))
                cost_records.append((date, cost))
            else:
                # Drift weights with daily returns (no rebalance)
                for s in symbols:
                    daily_ret = returns.iloc[i].get(s, 0.0)
                    weights[s] = weights.get(s, 0.0) * (1.0 + daily_ret)
                # Re-normalize
                total = sum(weights.values())
                if total > 0:
                    weights = {s: w / total for s, w in weights.items()}

            weight_records.append((date, dict(weights)))

        # Build DataFrames
        if weight_records:
            weight_history = pd.DataFrame(
                [r[1] for r in weight_records],
                index=[r[0] for r in weight_records],
            )
        else:
            weight_history = pd.DataFrame(columns=symbols)

        turnover_series = (
            pd.Series(
                [r[1] for r in turnover_records],
                index=[r[0] for r in turnover_records],
                name="turnover",
            )
            if turnover_records
            else pd.Series(dtype=float, name="turnover")
        )

        cost_series = (
            pd.Series(
                [r[1] for r in cost_records],
                index=[r[0] for r in cost_records],
                name="cost",
            )
            if cost_records
            else pd.Series(dtype=float, name="cost")
        )

        return RebalanceSeries(
            events=events,
            weight_history=weight_history,
            turnover_history=turnover_series,
            cost_history=cost_series,
            total_cost=float(cost_series.sum()),
            n_rebalances=len(events),
        )
