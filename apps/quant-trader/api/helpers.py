"""Shared helper utilities for API routes."""
from __future__ import annotations

import time

from ..data.base import BarRequest, get_feed

# Bounded window for "latest price" lookups.
_RECENT_START = "2024-01-01"
_RECENT_END = "2026-01-01"

# Price cache (TTL-based, shared across routes).
_PRICE_CACHE: dict = {}
_PRICE_CACHE_TTL = 300  # 5 minutes
_PRICE_CACHE_MAX = 100


def load_prices(symbol: str, source: str, start: str, end: str, interval: str):
    """Load OHLCV, falling back to synthetic data when a real feed fails."""
    import logging

    cache_key = (symbol, source, start, end, interval)
    now = time.time()
    cached = _PRICE_CACHE.get(cache_key)
    if cached is not None:
        data, ts = cached
        if now - ts < _PRICE_CACHE_TTL:
            return data, source

    req = BarRequest(symbol=symbol, start=start, end=end, interval=interval)
    try:
        result = get_feed(source).history(req)
        if len(_PRICE_CACHE) >= _PRICE_CACHE_MAX:
            oldest_key = min(_PRICE_CACHE, key=lambda k: _PRICE_CACHE[k][1])
            del _PRICE_CACHE[oldest_key]
        _PRICE_CACHE[cache_key] = (result, now)
        return result, source
    except Exception:
        if source != "synthetic":
            logging.getLogger("api").warning(
                "数据源 %s 失败,回退到 synthetic 数据 (%s)", source, symbol)
            return get_feed("synthetic").history(req), "synthetic"
        raise


def power_label(element: str, reigning: str) -> str:
    """五行力量标签（模块已下线，保留空实现供旧引用）。"""
    _ = (element, reigning)
    return ""
