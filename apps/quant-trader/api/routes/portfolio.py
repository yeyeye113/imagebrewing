"""Portfolio & order routes: /portfolio, /orders, /signal."""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException

from ...strategy.base import Signal
from ..helpers import _RECENT_END, _RECENT_START, load_prices
from ..schemas import AccountResponse, OrderRequest, OrderResponse, OrdersListResponse, SignalRequest


def register_portfolio_routes(app, shared, auth):
    """Register portfolio, order and signal endpoints."""

    def _positions_list():
        positions = getattr(shared.broker, "_positions", {})
        return [
            {"symbol": p.symbol, "qty": p.qty, "avg_price": p.avg_price}
            for p in positions.values()
        ]

    def _price_into_broker(symbol: str, source: str) -> None:
        if hasattr(shared.broker, "set_price"):
            try:
                prices, _ = load_prices(symbol, source, _RECENT_START, _RECENT_END, "1d")
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Data load failed: {e}")
            shared.broker.set_price(symbol, float(prices["close"].iloc[-1]))

    def _account_payload():
        acct = shared.broker.get_account()
        return AccountResponse(
            cash=acct.cash, equity=acct.equity, positions=_positions_list(),
            is_live=getattr(shared.broker, "is_live", False),
        )

    @app.get("/portfolio", response_model=AccountResponse, dependencies=[Depends(auth)])
    def portfolio():
        return _account_payload()

    @app.post("/orders", response_model=OrderResponse, dependencies=[Depends(auth)])
    def submit_order(order: OrderRequest):
        if getattr(shared.broker, "is_live", False) and os.environ.get("QT_ALLOW_LIVE", "") not in ("1", "true", "yes"):
            raise HTTPException(status_code=403,
                                detail="Live (real-money) trading disabled. Set QT_ALLOW_LIVE=1 to enable.")
        _price_into_broker(order.symbol, order.source)
        try:
            if order.side == "buy":
                notional = order.notional
                if notional is None and order.qty is None:
                    notional = shared.broker.get_account().cash * 0.95
                placed = shared.broker.submit_order(
                    order.symbol, "buy", qty=order.qty, notional=notional,
                    order_type=order.order_type, limit_price=order.limit_price, note=order.note,
                )
            else:
                if order.qty:
                    placed = shared.broker.submit_order(
                        order.symbol, "sell", qty=order.qty,
                        order_type=order.order_type, limit_price=order.limit_price, note=order.note,
                    )
                else:
                    pos = shared.broker.get_position(order.symbol)
                    qty = pos.qty if pos else 0.0
                    placed = shared.broker.submit_order(order.symbol, "sell", qty=qty, note=order.note or "sell_all")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Order failed: {e}")

        acct = shared.broker.get_account()
        return OrderResponse(
            order=placed.to_dict(),
            account={"cash": acct.cash, "equity": acct.equity,
                     "positions": _positions_list(), "is_live": getattr(shared.broker, "is_live", False)},
        )

    @app.get("/orders", response_model=OrdersListResponse, dependencies=[Depends(auth)])
    def list_orders(status: str | None = None, limit: int = 100):
        return OrdersListResponse(orders=[o.to_dict() for o in shared.broker.list_orders(status, limit)])

    @app.delete("/orders/{order_id}", dependencies=[Depends(auth)])
    def cancel_order(order_id: str):
        ok = shared.broker.cancel_order(order_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Order not found or not cancelable.")
        return {"canceled": order_id}

    @app.post("/signal", response_model=AccountResponse, dependencies=[Depends(auth)])
    def submit_signal(sig: SignalRequest):
        if getattr(shared.broker, "is_live", False) and os.environ.get("QT_ALLOW_LIVE", "") not in ("1", "true", "yes"):
            raise HTTPException(status_code=403,
                                detail="Live (real-money) trading disabled. Set QT_ALLOW_LIVE=1 to enable.")
        _price_into_broker(sig.symbol, sig.source)
        pos = shared.broker.get_position(sig.symbol)
        if sig.signal == Signal.BUY and (pos is None or pos.qty == 0):
            notional = sig.notional or shared.broker.get_account().cash * 0.95
            shared.broker.submit_order(sig.symbol, "buy", notional=notional, note="signal")
        elif sig.signal != Signal.BUY and pos is not None and pos.qty > 0:
            shared.broker.submit_order(sig.symbol, "sell", qty=pos.qty, note="signal")
        return _account_payload()
