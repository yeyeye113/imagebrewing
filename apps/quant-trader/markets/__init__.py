"""Multi-market support for quant-trader.

Provides:
- Unified Market interface (normalize_symbol, get_data_feed, get_broker)
- Per-market calendars with holidays and trading hours
- Timezone conversion (UTC <-> local)
- Market registry (get_market, list_markets)

Usage::

    from quanttrader.markets import get_market, list_markets

    hk = get_market("HK")
    print(hk.normalize_symbol("700"))   # "00700.HK"
    print(hk.is_market_open())          # True/False
    feed = hk.get_data_feed()

    us = get_market("US")
    print(us.normalize_symbol("aapl"))  # "AAPL"
    broker = us.get_broker(api_key="...", api_secret="...")
"""

from .base import Market, MarketMeta, get_market, list_markets, register_market
from .calendar import (
    TradingCalendar,
    get_calendar,
    to_local,
    to_utc,
    utc_now,
)
from .hk import HKMarket
from .us import USMarket

__all__ = [
    # Markets
    "HKMarket",
    # Core
    "Market",
    "MarketMeta",
    # Calendar
    "TradingCalendar",
    "USMarket",
    "get_calendar",
    "get_market",
    "list_markets",
    "register_market",
    "to_local",
    "to_utc",
    "utc_now",
]
