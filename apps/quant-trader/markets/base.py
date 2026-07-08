"""Unified market interface.

Each Market subclass encapsulates:
- Symbol normalization (user string -> exchange format)
- Data feed factory (connects to the right data source)
- Broker factory (connects to the right broker)
- Calendar (trading hours, holidays, timezone)
- Lot size, currency, commission defaults
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

from .calendar import TradingCalendar, get_calendar


@dataclass
class MarketMeta:
    """Static metadata for a market."""

    code: str  # "CN", "HK", "US"
    name: str  # "A-Share", "Hong Kong", "US Equities"
    currency: str  # "CNY", "HKD", "USD"
    timezone: str  # "Asia/Shanghai", etc.
    lot_size: int = 1  # minimum tradeable unit (100 for CN, 1 for HK/US)
    commission_rate: float = 0.0003  # default commission fraction
    stamp_duty: float = 0.0  # stamp duty fraction (CN sell-side)
    min_commission: float = 5.0  # minimum commission in local currency


class Market(abc.ABC):
    """Base class for market implementations.

    Subclass and implement the abstract properties/methods to add a new market.
    """

    @property
    @abc.abstractmethod
    def meta(self) -> MarketMeta: ...

    @property
    def calendar(self) -> TradingCalendar:
        return get_calendar(self.meta.code)

    @abc.abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """Convert user-facing symbol to exchange-standard format.

        Examples:
            CN: "600519" -> "600519.SH", "sh600519" -> "600519.SH"
            HK: "00700" -> "00700.HK", "腾讯" -> "00700.HK"
            US: "aapl" -> "AAPL", "msft" -> "MSFT"
        """

    @abc.abstractmethod
    def get_data_feed(self, **kwargs):
        """Return a DataFeed instance configured for this market."""

    @abc.abstractmethod
    def get_broker(self, **kwargs):
        """Return a Broker instance configured for this market."""

    def is_trading_day(self, date=None) -> bool:
        return self.calendar.is_trading_day(date)

    def is_market_open(self, dt_utc=None) -> bool:
        return self.calendar.is_market_open(dt_utc)

    def now_local(self, dt_utc=None):
        """Current time in the market's local timezone."""
        return self.calendar.market_time(dt_utc)

    def calc_commission(self, notional: float, side: str = "buy") -> float:
        """Calculate commission for a given trade notional."""
        comm = abs(notional) * self.meta.commission_rate
        comm = max(comm, self.meta.min_commission)
        # Stamp duty is sell-side only (CN market)
        if side == "sell" and self.meta.stamp_duty > 0:
            comm += abs(notional) * self.meta.stamp_duty
        return round(comm, 2)

    def round_qty(self, qty: float) -> int:
        """Round quantity to the market's minimum lot size."""
        lot = self.meta.lot_size
        return (int(qty) // lot) * lot

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.meta.code} {self.meta.currency}>"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[Market]] = {}


def register_market(code: str, cls: type[Market]) -> None:
    _REGISTRY[code.upper()] = cls


def get_market(code: str) -> Market:
    """Get a Market instance by code ('CN', 'HK', 'US')."""
    code = code.upper().strip()
    if code not in _REGISTRY:
        # Lazy import to avoid circular deps
        pass
    cls = _REGISTRY.get(code)
    if cls is None:
        raise ValueError(f"Unknown market: {code!r}. Available: {list(_REGISTRY.keys())}")
    return cls()


def list_markets() -> list[str]:
    """Return all registered market codes."""
    # Ensure all markets are imported

    return sorted(_REGISTRY.keys())
