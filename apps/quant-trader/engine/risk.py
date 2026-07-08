from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskConfig:
    """Risk-management rules that encode professional-trader discipline.

    All thresholds are fractions (0.08 == 8%). Set a value to 0/None to disable
    that rule. These run *inside* the backtest loop and can force an exit even
    when the strategy still says "hold".

    - stop_loss      : exit if price falls this far below entry (cut losses short)
    - take_profit    : exit if price rises this far above entry (bank the win)
    - trailing_stop  : exit if price falls this far below the peak since entry
                       (let winners run, but protect open profit)
    - max_drawdown   : portfolio circuit-breaker — if equity falls this far from
                       its peak, liquidate and stop opening new trades (capital
                       preservation first)
    - risk_per_trade : informational — suggested fraction of equity to risk per
                       trade given the stop distance (used by the advisor)
    """

    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop: float = 0.0
    max_drawdown: float = 0.0
    risk_per_trade: float = 0.01

    def enabled(self) -> bool:
        return any((self.stop_loss, self.take_profit, self.trailing_stop, self.max_drawdown))


class PositionRisk:
    """Tracks per-trade risk state (entry price, peak) for one open position."""

    def __init__(self, entry_price: float):
        self.entry_price = entry_price
        self.peak_price = entry_price

    def update(self, price: float) -> None:
        if price > self.peak_price:
            self.peak_price = price

    def hit_stop(self, price: float, cfg: RiskConfig) -> str | None:
        """Return the reason a position should be exited, or None to hold."""
        if cfg.stop_loss and price <= self.entry_price * (1 - cfg.stop_loss):
            return "stop_loss"
        if cfg.take_profit and price >= self.entry_price * (1 + cfg.take_profit):
            return "take_profit"
        if cfg.trailing_stop and price <= self.peak_price * (1 - cfg.trailing_stop):
            return "trailing_stop"
        return None
