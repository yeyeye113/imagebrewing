from __future__ import annotations

import os
from typing import Any

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


class AlpacaBroker(Broker):
    """Real broker adapter using Alpaca's trading API (`alpaca-py`).

    Supports both paper trading (fake money, free) and live trading. Get free
    API keys at https://alpaca.markets. Set ``paper=True`` to be safe.

    Real-money safety: when ``paper=False`` the adapter refuses to initialise
    unless ``allow_live=True`` (or env ``QT_ALLOW_LIVE=1``) is set, so you can't
    accidentally route real orders.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        paper: bool = True,
        allow_live: bool | None = None,
        allow_leverage: bool = False,
    ):
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.trading.client import TradingClient
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "alpaca-py is not installed. Run `pip install alpaca-py` to use the live/paper Alpaca broker."
            ) from exc

        if not api_key or not api_secret or api_key.startswith("YOUR_"):
            raise ValueError("Alpaca API key/secret missing. Edit config.yaml under broker:.")

        self.is_live = not paper
        if self.is_live:
            if allow_live is None:
                allow_live = os.environ.get("QT_ALLOW_LIVE", "") in ("1", "true", "yes")
            if not allow_live:
                raise PermissionError(
                    "Refusing to start a LIVE (real-money) Alpaca broker. Set "
                    "broker.allow_live: true in config (or env QT_ALLOW_LIVE=1) to confirm."
                )

        self.allow_leverage = allow_leverage
        self._trading = TradingClient(api_key, api_secret, paper=paper)
        self._data = StockHistoricalDataClient(api_key, api_secret)
        self._orders: list[Order] = []

    def get_account(self) -> Account:
        # alpaca-py 返回 TradeAccount | dict 联合类型, 按属性访问 (raw dict 仅出现在 use_raw_data 模式)
        acct: Any = self._trading.get_account()
        return Account(cash=float(acct.cash), equity=float(acct.equity))

    def get_position(self, symbol: str) -> Position | None:
        p: Any
        try:
            p = self._trading.get_open_position(symbol)
        except Exception:
            return None
        return Position(symbol, float(p.qty), float(p.avg_entry_price))

    def last_price(self, symbol: str) -> float:
        from alpaca.data.requests import StockLatestTradeRequest

        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trade = self._data.get_stock_latest_trade(req)
        return float(trade[symbol].price)

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
        from alpaca.trading.enums import OrderSide as AlpacaSide
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        side = norm_side(side)
        otype = norm_type(order_type)

        # No leverage: clamp a buy's dollar amount to non-margin buying power
        # (cash) so the account can never go on margin unless explicitly allowed.
        if side == OrderSide.BUY.value and notional and not self.allow_leverage:
            try:
                acct_raw: Any = self._trading.get_account()
                cash = float(acct_raw.cash)
                if notional > cash:
                    notional = round(max(0.0, cash), 2)
                    note = (note + " | " if note else "") + "clamped to cash (no-leverage)"
            except Exception:
                pass

        order = Order(
            symbol=symbol, side=side, type=otype, qty=qty, notional=notional, limit_price=limit_price, note=note
        )
        a_side = AlpacaSide.BUY if side == OrderSide.BUY.value else AlpacaSide.SELL

        try:
            req: LimitOrderRequest | MarketOrderRequest
            if otype == OrderType.LIMIT.value and limit_price is not None:
                req = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    notional=notional,
                    side=a_side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=round(float(limit_price), 2),
                )
            else:
                req = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    notional=round(notional, 2) if notional else None,
                    side=a_side,
                    time_in_force=TimeInForce.DAY,
                )
            resp = self._trading.submit_order(req)
            order.id = str(getattr(resp, "id", order.id))
            status = str(getattr(resp, "status", "pending"))
            order.status = (
                OrderStatus.FILLED.value if status in ("filled", "accepted", "new") else OrderStatus.PENDING.value
            )
            order.note = (note + " | " if note else "") + f"alpaca:{status}"
        except Exception as exc:  # pragma: no cover - network path
            order.status = OrderStatus.REJECTED.value
            order.note = (note + " | " if note else "") + f"error: {exc}"

        self._orders.append(order)
        return order

    def buy(self, symbol: str, notional: float) -> None:
        if notional and notional > 0:
            self.submit_order(symbol, OrderSide.BUY.value, notional=notional)

    def sell(self, symbol: str, qty: float) -> None:
        if qty and qty > 0:
            self.submit_order(symbol, OrderSide.SELL.value, qty=qty)

    def sell_all(self, symbol: str) -> None:
        try:
            self._trading.close_position(symbol)
            self._orders.append(
                Order(
                    symbol=symbol,
                    side="sell",
                    note="close_position",
                    status=OrderStatus.FILLED.value,
                    filled_at=_now_iso(),
                )
            )
        except Exception:
            pass

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._trading.cancel_order_by_id(order_id)
            local = self.get_order(order_id)
            if local is not None:
                local.status = OrderStatus.CANCELED.value
            return True
        except Exception:
            return False
