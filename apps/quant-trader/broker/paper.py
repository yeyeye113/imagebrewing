from __future__ import annotations

from .base import (
    Account,
    Broker,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    _now_iso,
    norm_side,
    norm_type,
)

_BUY = OrderSide.BUY.value
_SELL = OrderSide.SELL.value
_LIMIT = OrderType.LIMIT.value
_PENDING = OrderStatus.PENDING.value
_FILLED = OrderStatus.FILLED.value
_REJECTED = OrderStatus.REJECTED.value


class PaperBroker(Broker):
    """In-memory simulated broker. No network, no real money.

    Prices are pushed in via ``set_price`` by the live loop's data feed, so the
    same loop code works for both paper and real brokers. Supports market and
    limit orders, partial sells, an order log, and cancellation of resting
    (unfilled) limit orders.
    """

    is_live = False

    def __init__(self, cash: float = 100_000.0, commission: float = 0.0005, slippage: float = 0.0005):
        self.cash = cash
        self.commission = commission
        self.slippage = slippage
        self._positions: dict[str, Position] = {}
        self._prices: dict[str, float] = {}
        self._orders: list[Order] = []

    # ---- Pricing -----------------------------------------------------------
    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price
        self._try_fill_pending(symbol)

    def last_price(self, symbol: str) -> float:
        if symbol not in self._prices:
            raise RuntimeError(f"No price set for {symbol!r}. Call set_price() first.")
        return self._prices[symbol]

    # ---- Account / positions ----------------------------------------------
    def get_account(self) -> Account:
        equity = self.cash + sum(pos.qty * self._prices.get(sym, pos.avg_price) for sym, pos in self._positions.items())
        return Account(cash=self.cash, equity=equity)

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    # ---- Fill hooks (overridden by CnPaperBroker for lots / T+1) -----------
    def _fill_buy(self, symbol: str, notional: float, ref_price: float):
        """Return (qty, exec_price, fees) or None if the order can't fill."""
        notional = min(notional, self.cash)
        if notional <= 0:
            return None
        price = ref_price * (1 + self.slippage)
        gross = notional / (1 + self.commission)
        qty = gross / price
        if qty <= 0:
            return None
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
        return qty, price, fees

    def _fill_sell(self, symbol: str, qty: float, ref_price: float):
        """Return (qty, exec_price, fees) or None. Reduces or closes a position."""
        pos = self._positions.get(symbol)
        if not pos or pos.qty <= 0:
            return None
        qty = min(qty, pos.qty) if qty else pos.qty
        if qty <= 0:
            return None
        price = ref_price * (1 - self.slippage)
        gross = qty * price
        fees = gross * self.commission
        self.cash += gross - fees
        remaining = pos.qty - qty
        if remaining > 1e-9:
            self._positions[symbol] = Position(symbol, remaining, pos.avg_price)
        else:
            self._positions.pop(symbol, None)
        return qty, price, fees

    # ---- Order entry -------------------------------------------------------
    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float | None = None,
        notional: float | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
        note: str = "",
    ) -> Order:
        order = Order(
            symbol=symbol,
            side=norm_side(side),
            type=norm_type(order_type),
            qty=qty,
            notional=notional,
            limit_price=limit_price,
            note=note,
        )
        self._orders.append(order)
        self._activate(order)
        return order

    def _activate(self, order: Order) -> None:
        price = self._prices.get(order.symbol)
        if price is None:
            order.status = _REJECTED
            order.note = (order.note + " | " if order.note else "") + "no price available"
            return

        # Limit orders only fill when the market reaches the limit.
        if order.type == _LIMIT and order.limit_price is not None:
            if order.side == _BUY and price > order.limit_price:
                order.status = _PENDING
                return
            if order.side == _SELL and price < order.limit_price:
                order.status = _PENDING
                return

        self._do_fill(order, price)

    def _do_fill(self, order: Order, price: float) -> None:
        if order.side == _BUY:
            notional = order.notional
            if notional is None and order.qty:
                notional = order.qty * price
            res = self._fill_buy(order.symbol, notional or 0.0, price)
        else:
            res = self._fill_sell(order.symbol, order.qty or 0.0, price)

        if res is None:
            order.status = _REJECTED
            order.note = (order.note + " | " if order.note else "") + "not fillable (cash/position/lot/T+1)"
            return
        qty, exec_price, fees = res
        order.filled_qty = qty
        order.filled_price = exec_price
        order.fees = fees
        order.status = _FILLED
        order.filled_at = _now_iso()

    def _try_fill_pending(self, symbol: str) -> None:
        for order in self._orders:
            if order.status == _PENDING and order.symbol == symbol:
                self._activate(order)

    # ---- Backward-compatible convenience ----------------------------------
    def buy(self, symbol: str, notional: float) -> None:
        self.submit_order(symbol, _BUY, notional=notional)

    def sell(self, symbol: str, qty: float) -> None:
        self.submit_order(symbol, _SELL, qty=qty)

    def sell_all(self, symbol: str) -> None:
        pos = self._positions.get(symbol)
        qty = pos.qty if pos else 0.0
        if qty <= 0:
            return
        self.submit_order(symbol, _SELL, qty=qty)
