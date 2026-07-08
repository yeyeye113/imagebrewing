from __future__ import annotations

import datetime as dt

from .base import Position
from .paper import PaperBroker

# A-share price-limit constants.
_LIMIT_RATE = 0.10  # Main-board: ±10%; ChiNext/ST use ±20%/±5%.


def _is_at_limit(price: float, prev_close: float, direction: str, limit_rate: float = _LIMIT_RATE) -> bool:
    """Check whether a fill would execute at the given price. The limit is
    computed from the previous close; prices equal to the limit (涨停/跌停板)
    mean the market is locked and fills are unlikely.

    - "buy"  → 涨停不可买 (price is at the upper limit)
    - "sell" → 跌停不可卖 (price is at the lower limit)
    """
    if prev_close <= 0:
        return False
    upper = prev_close * (1 + limit_rate)
    lower = prev_close * (1 - limit_rate)
    if direction == "buy":
        return price >= upper - 1e-9
    return price <= lower + 1e-9


class CnPaperBroker(PaperBroker):
    """Paper broker that enforces A-share trading rules:

    * **Lot size**: buy quantities are rounded down to whole lots (100 shares).
    * **T+1**: shares bought today cannot be sold until the next trading day.
    * **Price limits**: if the reference price hits the ±10% limit board
      (涨停/跌停), the fill is rejected — 涨停不可买、跌停不可卖.

    Set ``limit_rate`` to 0.20 for ChiNext or 0.05 for ST stocks. Default is
    0.10 (main-board).
    """

    LOT = 100

    def __init__(
        self,
        cash: float = 100_000.0,
        commission: float = 0.00025,
        slippage: float = 0.0005,
        stamp_tax: float = 0.0005,
        limit_rate: float = _LIMIT_RATE,
    ):
        # A-share: commission (双向, 万2.5) + stamp tax (卖出, 千0.5/印花税).
        super().__init__(cash=cash, commission=commission, slippage=slippage)
        self.stamp_tax = stamp_tax
        self.limit_rate = limit_rate
        self._buy_date: dict[str, dt.date] = {}
        self._today: dt.date | None = None  # override for tests/backtests
        self._prev_close: dict[str, float] = {}  # symbol → previous close

    def _now(self) -> dt.date:
        return self._today or dt.date.today()

    def set_today(self, day: dt.date) -> None:
        """Inject the 'current' trading day (used by tests and backtests)."""
        self._today = day

    def set_price(self, symbol: str, price: float, prev_close: float | None = None) -> None:
        """Set the current market price. Optionally set the previous close for
        price-limit checks (涨跌停)."""
        super().set_price(symbol, price)
        if prev_close is not None:
            self._prev_close[symbol] = prev_close

    def _fill_buy(self, symbol: str, notional: float, ref_price: float):
        # Check price limit: 涨停不可买.
        prev = self._prev_close.get(symbol, ref_price)
        if _is_at_limit(ref_price, prev, "buy", self.limit_rate):
            return None

        notional = min(notional, self.cash)
        if notional <= 0:
            return None
        price = ref_price * (1 + self.slippage)
        gross = notional / (1 + self.commission)
        raw_qty = gross / price
        qty = (int(raw_qty) // self.LOT) * self.LOT  # whole lots only
        if qty <= 0:
            return None  # not enough cash for even one lot
        fees = qty * price * self.commission
        spend = qty * price + fees
        self.cash -= spend
        existing = self._positions.get(symbol)
        if existing:
            total_qty = existing.qty + qty
            avg = (existing.avg_price * existing.qty + price * qty) / total_qty
            self._positions[symbol] = Position(symbol, total_qty, avg)
        else:
            self._positions[symbol] = Position(symbol, qty, price)
        self._buy_date[symbol] = self._now()
        return qty, price, fees

    def _fill_sell(self, symbol: str, qty: float, ref_price: float):
        # Check price limit: 跌停不可卖.
        prev = self._prev_close.get(symbol, ref_price)
        if _is_at_limit(ref_price, prev, "sell", self.limit_rate):
            return None

        pos = self._positions.get(symbol)
        if not pos or pos.qty <= 0:
            return None
        # T+1: cannot sell shares purchased on the same trading day.
        bought = self._buy_date.get(symbol)
        if bought is not None and bought >= self._now():
            return None
        qty = min(qty, pos.qty) if qty else pos.qty
        # Sells must also be whole lots (unless liquidating the full position).
        if qty < pos.qty:
            qty = (int(qty) // self.LOT) * self.LOT
        if qty <= 0:
            return None
        price = ref_price * (1 - self.slippage)
        gross = qty * price
        fees = gross * (self.commission + self.stamp_tax)
        self.cash += gross - fees
        remaining = pos.qty - qty
        if remaining > 1e-9:
            self._positions[symbol] = Position(symbol, remaining, pos.avg_price)
        else:
            self._positions.pop(symbol, None)
            self._buy_date.pop(symbol, None)
        return qty, price, fees
