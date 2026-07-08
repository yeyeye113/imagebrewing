"""Multi-asset portfolio backtesting with capital allocation.

Runs the same strategy across several symbols, splits capital between them by a
chosen allocation scheme, and combines the per-symbol equity curves into one
portfolio curve. This captures the single biggest free lunch in investing —
diversification — which the single-asset backtester can't show.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pandas as pd

from ..strategy.base import Strategy
from .backtest import Backtester, BacktestResult
from .metrics import infer_periods_per_year, performance_summary
from .position_sizing import SizingConfig, compute_portfolio_weights
from .risk import RiskConfig


@dataclass
class MultiAssetResult:
    equity_curve: pd.Series
    per_symbol: dict  # symbol -> BacktestResult
    weights: dict  # symbol -> capital fraction
    stats: dict
    allocation: str

    @property
    def risk_events(self) -> list:
        events: list = []
        for res in self.per_symbol.values():
            events.extend(res.risk_events or [])
        return events

    @property
    def portfolio(self):
        """Advisor-compatible view: concatenated fills across all sleeves."""
        fills: list = []
        for res in self.per_symbol.values():
            fills.extend(res.portfolio.fills)
        return SimpleNamespace(fills=fills)

    @property
    def n_trades(self) -> int:
        return sum(res.n_trades for res in self.per_symbol.values())


class MultiBacktester:
    """Backtest a strategy over many symbols and aggregate into a portfolio."""

    def __init__(
        self,
        cash: float = 100_000.0,
        allocation: str = "equal",  # "equal" | "inverse_vol"
        order_size: float = 0.95,
        commission: float = 0.0005,
        slippage: float = 0.0005,
        lot_size: int = 1,
        risk: RiskConfig | None = None,
        sizing: SizingConfig | None = None,
    ):
        self.cash = cash
        self.allocation = allocation
        self.sizing = sizing or SizingConfig()
        self.bt_kwargs: dict[str, Any] = dict(
            order_size=order_size,
            commission=commission,
            slippage=slippage,
            lot_size=lot_size,
            risk=risk,
            sizing=self.sizing,
        )

    def _weights(self, prices_by_symbol: dict[str, pd.DataFrame]) -> dict:
        return compute_portfolio_weights(prices_by_symbol, self.allocation, self.sizing)

    def run(
        self,
        prices_by_symbol: dict[str, pd.DataFrame],
        strategy_factory: Callable[[], Strategy],
    ) -> MultiAssetResult:
        if not prices_by_symbol:
            raise ValueError("No symbols provided.")

        weights = self._weights(prices_by_symbol)
        per_symbol: dict[str, BacktestResult] = {}
        curves = []

        for sym, df in prices_by_symbol.items():
            slice_cash = self.cash * weights[sym]
            if slice_cash <= 0 or df.empty:
                continue
            bt = Backtester(cash=slice_cash, **self.bt_kwargs)
            res = bt.run(df, strategy_factory())
            per_symbol[sym] = res
            curves.append(res.equity_curve.rename(sym))

        if not curves:
            raise RuntimeError("No symbol produced a usable equity curve.")

        # Align on the union of dates; forward-fill, then back-fill the pre-start
        # gap with each sleeve's initial capital so the sum is always sensible.
        combined = pd.concat(curves, axis=1).sort_index()
        combined = combined.ffill()
        for col in combined.columns:
            start_cap = self.cash * weights[col]
            combined[col] = combined[col].fillna(start_cap)
        portfolio_curve = combined.sum(axis=1)
        idle_cash = self.cash * (1.0 - sum(weights.values()))
        if idle_cash > 0:
            portfolio_curve = portfolio_curve + idle_cash
        portfolio_curve.name = "equity"

        stats = performance_summary(
            portfolio_curve, periods_per_year=infer_periods_per_year(portfolio_curve.index)
        )
        return MultiAssetResult(
            equity_curve=portfolio_curve,
            per_symbol=per_symbol,
            weights=weights,
            stats=stats,
            allocation=self.allocation,
        )
