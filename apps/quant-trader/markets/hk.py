"""Hong Kong market implementation.

Exchanges: HKEX (Main Board, GEM)
Currency: HKD
Lot size: varies per stock (typically 100-2000), default 1000
Trading hours: 09:30-12:00, 13:00-16:00 HKT
"""

from __future__ import annotations

import re

from .base import Market, MarketMeta, register_market

# HKEX common lot sizes (fallback to 1000 for unknown)
_HK_LOT_SIZES: dict[str, int] = {
    "00700": 100,  # Tencent
    "09988": 100,  # Alibaba
    "03690": 100,  # Meituan
    "09618": 100,  # JD
    "01810": 200,  # Xiaomi
    "00005": 400,  # HSBC
    "00941": 500,  # China Mobile
    "02318": 500,  # Ping An
    "01299": 200,  # AIA
    "00388": 100,  # HKEX
    "09999": 100,  # NetEase
    "02020": 200,  # Anta Sports
    "09961": 200,  # Trip.com
}

_HK_META = MarketMeta(
    code="HK",
    name="Hong Kong",
    currency="HKD",
    timezone="Asia/Hong_Kong",
    lot_size=1000,  # conservative default
    commission_rate=0.0003,  # ~0.03% typical HK broker
    stamp_duty=0.0013,  # 0.13% stamp duty (both sides)
    min_commission=50.0,  # HKD 50 minimum
)


class HKMarket(Market):
    """Hong Kong stock market (HKEX)."""

    @property
    def meta(self) -> MarketMeta:
        return _HK_META

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize HK stock symbol to ``NNNNN.HK`` format.

        Handles:
            "00700"   -> "00700.HK"
            "00700.HK" -> "00700.HK"
            "700"     -> "00700.HK"
            "0700"    -> "00700.HK"
            "hk00700" -> "00700.HK"
        """
        s = symbol.strip().upper()
        # Strip common prefixes
        s = re.sub(r"^(HK|\.HK)", "", s)
        # Strip existing .HK suffix
        s = re.sub(r"\.HK$", "", s)
        # Strip leading zeros for normalization, then re-pad to 5 digits
        s = s.lstrip("0") or "0"
        return f"{s.zfill(5)}.HK"

    def get_lot_size(self, symbol: str) -> int:
        """Return lot size for a specific HK stock."""
        code = self.normalize_symbol(symbol).replace(".HK", "")
        return _HK_LOT_SIZES.get(code, self.meta.lot_size)

    def round_qty(self, qty: float) -> int:
        """Round to the stock's specific lot size."""
        code = self.normalize_symbol(str(getattr(self, "_last_symbol", "00700"))).replace(".HK", "")
        lot = _HK_LOT_SIZES.get(code, self.meta.lot_size)
        return (int(qty) // lot) * lot

    def get_data_feed(self, **kwargs):
        """Return a Yahoo DataFeed (HK stocks use .HK suffix on Yahoo)."""
        from ..data import YahooDataFeed

        return YahooDataFeed(**kwargs)

    def get_broker(self, **kwargs):
        """Return a paper broker for HK market.

        For live HK trading, extend with a real broker adapter.
        """
        from ..broker import PaperBroker

        kwargs.setdefault("lot_size", self.meta.lot_size)
        return PaperBroker(**kwargs)


register_market("HK", HKMarket)
