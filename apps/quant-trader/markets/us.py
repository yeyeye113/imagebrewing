"""US market implementation.

Exchanges: NYSE, NASDAQ
Currency: USD
Lot size: 1 (fractional shares supported by some brokers)
Trading hours: 09:30-16:00 ET, pre-market 04:00-09:30, after-hours 16:00-20:00
"""

from __future__ import annotations

from .base import Market, MarketMeta, register_market

_US_META = MarketMeta(
    code="US",
    name="US Equities",
    currency="USD",
    timezone="America/New_York",
    lot_size=1,
    commission_rate=0.0,  # most US brokers are commission-free
    stamp_duty=0.0,
    min_commission=0.0,
)


class USMarket(Market):
    """US stock market (NYSE / NASDAQ)."""

    @property
    def meta(self) -> MarketMeta:
        return _US_META

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize US stock symbol to uppercase.

        Handles:
            "aapl"   -> "AAPL"
            "MSFT"   -> "MSFT"
            "BRK.B"  -> "BRK.B"
            "BRK-B"  -> "BRK.B"
        """
        s = symbol.strip().upper()
        # Normalize dash to dot for class shares
        s = s.replace("-", ".")
        return s

    def get_data_feed(self, **kwargs):
        """Return a Yahoo DataFeed (US stocks are native on Yahoo)."""
        from ..data import YahooDataFeed

        return YahooDataFeed(**kwargs)

    def get_broker(self, **kwargs):
        """Return an Alpaca broker for US market.

        Requires ALPACA_API_KEY and ALPACA_API_SECRET in config or env.
        Falls back to paper broker if keys not configured.
        """
        api_key = kwargs.pop("api_key", "")
        api_secret = kwargs.pop("api_secret", "")
        paper = kwargs.pop("paper", True)

        if api_key and api_secret and not api_key.startswith("YOUR_"):
            from ..broker.alpaca import AlpacaBroker

            return AlpacaBroker(
                api_key=api_key,
                api_secret=api_secret,
                paper=paper,
                **kwargs,
            )
        # Fallback: paper broker
        from ..broker import PaperBroker

        return PaperBroker(**kwargs)


register_market("US", USMarket)
