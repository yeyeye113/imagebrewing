from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..strategy.base import Signal, Strategy
from .metrics import infer_periods_per_year, performance_summary, trade_stats
from .portfolio import Portfolio
from .position_sizing import SizingConfig, compute_entry_notional
from .risk import PositionRisk, RiskConfig


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    signals: pd.Series
    portfolio: Portfolio
    stats: dict
    risk_events: list | None = None  # (timestamp, reason) forced exits

    @property
    def n_trades(self) -> int:
        return len(self.portfolio.fills)

    @property
    def trade_stats(self) -> dict:
        """逐笔交易统计 (融合兼容: 工作区 reporter/research 以属性方式访问)。"""
        from .metrics import trade_stats as _trade_stats
        return _trade_stats(self.portfolio.fills)


class Backtester:
    """Event-driven (bar-by-bar) backtest for a single symbol.

    To avoid look-ahead bias, the signal computed from bar *t* is executed at
    the open-equivalent (close) of bar *t+1*. Equity is marked at each bar's
    close.

    Performance: uses NumPy arrays internally for ~200× faster loop body vs
    ``DataFrame.iterrows()``, while preserving the stateful event-driven
    structure (risk exits, circuit breakers, entry/exit logic).
    """

    def __init__(
        self,
        cash: float = 100_000.0,
        order_size: float = 0.95,
        commission: float = 0.0005,
        slippage: float = 0.0005,
        lot_size: int = 1,
        risk: RiskConfig | None = None,
        sizing: SizingConfig | None = None,
        symbol: str = "",
    ):
        self.cash = cash
        self.order_size = order_size
        self.commission = commission
        self.slippage = slippage
        self.lot_size = lot_size
        self.risk = risk or RiskConfig()
        self.sizing = sizing or SizingConfig()
        self.symbol = symbol

    def run(self, prices: pd.DataFrame, strategy: Strategy) -> BacktestResult:
        symbol = self.symbol or getattr(strategy, "name", "__default__")
        target = strategy.generate(prices).reindex(prices.index).fillna(Signal.HOLD)
        executed = target.shift(1).fillna(Signal.HOLD)

        pf = Portfolio(
            cash=self.cash,
            commission=self.commission,
            slippage=self.slippage,
            lot_size=self.lot_size,
        )

        # ── NumPy arrays for O(1) per-bar access ──
        timestamps = prices.index.values
        closes = prices["close"].values.astype(np.float64)
        n = len(closes)

        # 年化因子按 bar 间隔推断(日线 252 / 日内更高)，供绩效指标与波动率目标共用，
        # 避免日内回测仍按 252 天错算 Sharpe / CAGR / 年化波动。
        ppy = infer_periods_per_year(prices.index)
        vol_arr: np.ndarray | None = None
        if self.sizing.target_volatility > 0:
            vol_series = prices["close"].pct_change().rolling(self.sizing.vol_lookback).std().mul(ppy**0.5).shift(1)
            vol_arr = vol_series.values.astype(np.float64)

        equity = np.empty(n, dtype=np.float64)
        risk_events: list[tuple] = []
        pos_risk: PositionRisk | None = None
        halted = False
        peak_equity = self.cash
        i = 0

        for i in range(n):
            ts = timestamps[i]
            price = closes[i]
            want = int(executed.iloc[i])

            # 1) Risk-driven exits
            if pf.position > 0 and pos_risk is not None:
                pos_risk.update(price)
                reason = pos_risk.hit_stop(price, self.risk)
                if reason:
                    pf.sell_all(ts, symbol, price)
                    pos_risk = None
                    risk_events.append((ts, reason))

            # 2) Portfolio circuit breaker
            cur_equity = pf.equity(price)
            peak_equity = max(peak_equity, cur_equity)
            if self.risk.max_drawdown and not halted:
                if cur_equity <= peak_equity * (1 - self.risk.max_drawdown):
                    if pf.position > 0:
                        pf.sell_all(ts, symbol, price)
                        pos_risk = None
                        risk_events.append((ts, "max_drawdown_halt"))
                    halted = True

            # 3) Strategy entries/exits
            if not halted:
                if want == Signal.BUY and pf.position == 0:
                    pos_val = pf.position * price
                    vol = None
                    if vol_arr is not None:
                        v = vol_arr[i]
                        vol = float(v) if not np.isnan(v) else None
                    notional = compute_entry_notional(
                        cur_equity,
                        pf.cash,
                        pos_val,
                        self.order_size,
                        self.sizing,
                        self.risk,
                        volatility=vol,
                    )
                    pf.buy(ts, symbol, price, notional)
                    if pf.position > 0:
                        pos_risk = PositionRisk(price)
                elif want != Signal.BUY and pf.position > 0:
                    pf.sell_all(ts, symbol, price)
                    pos_risk = None

            equity[i] = pf.equity(price)

        equity_curve = pd.Series(equity, index=prices.index, name="equity")
        stats = performance_summary(equity_curve, periods_per_year=ppy)
        # 合并逐笔交易质量指标：让回测/优化都能判断信号是否真的成交、胜率与盈亏比如何，
        # 避免「零成交/单笔持有」被高 Sharpe 假象掩盖。
        stats.update(trade_stats(pf.fills))
        stats["n_trades"] = len(pf.fills)
        # JSON 不支持 inf/nan：无亏损时 profit_factor/payoff_ratio 为 inf，统一降级为 None 防止序列化失败。
        for _k, _v in list(stats.items()):
            if isinstance(_v, float) and not math.isfinite(_v):
                stats[_k] = None
        return BacktestResult(equity_curve, target, pf, stats, risk_events)
