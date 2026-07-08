"""Market data routes: /market/bars, /market/price, /market/schedule."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from ...market_schedule import market_schedule
from ..helpers import _RECENT_END, _RECENT_START, load_prices
from ..schemas import Bar, BarsResponse, PriceResponse


def register_market_routes(app, shared, auth):
    """Register market data endpoints."""

    @app.get("/market/bars", response_model=BarsResponse, dependencies=[Depends(auth)])
    def market_bars(
        symbol: str,
        source: str = "synthetic",
        start: str = "2022-01-01",
        end: str = "2024-01-01",
        interval: str = "1d",
    ):
        try:
            prices, used = load_prices(symbol, source, start, end, interval)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Data load failed: {e}")
        bars = [
            Bar(time=str(idx), **{k: float(v) for k, v in zip(prices.columns, row)})
            for idx, row in zip(prices.index, prices.values)
        ]
        return BarsResponse(symbol=symbol, source=used, interval=interval, bars=bars)

    @app.get("/market/price", response_model=PriceResponse, dependencies=[Depends(auth)])
    def market_price(symbol: str, source: str = "synthetic"):
        prices, used = load_prices(symbol, source, _RECENT_START, _RECENT_END, "1d")
        return PriceResponse(symbol=symbol, price=float(prices["close"].iloc[-1]), source=used)

    @app.get("/market/schedule")
    def market_schedule_api():
        return market_schedule().to_dict()
