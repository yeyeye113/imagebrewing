"""五行元数据解析: 股票/期货代码 → (code, name, sector, element)."""
from __future__ import annotations

from .constants import FUTURES_POOL, STOCK_50


def resolve_stock_meta(symbol: str, name: str = "") -> tuple[str, str, str, str]:
    """解析 A 股代码 → (code, name, sector, element). 池外标的用五行推断属性."""
    raw = (symbol or "").strip().upper()
    code = raw.zfill(6) if raw.isdigit() else raw
    for c, n, sec, elem in STOCK_50:
        if c == code:
            return c, n, sec, elem
    dn = (name or "").strip() or code
    return code, dn, "自选", "?"


def resolve_future_meta(symbol: str, name: str = "") -> tuple[str, str, str, str]:
    """解析期货代码 → (code, name, sector, element). 支持多种格式."""
    raw = (symbol or "").strip().upper()

    # 精确匹配
    for c, n, sec, elem in FUTURES_POOL:
        if c == raw:
            return c, n, sec, elem

    # 模糊匹配 (去掉数字后缀)
    base = raw.rstrip("0123456789")
    if base and base != raw:
        for c, n, sec, elem in FUTURES_POOL:
            if c == base:
                return c, n, sec, elem

    # 带M后缀 (主力合约)
    if raw.endswith("M"):
        base = raw[:-1]
        for c, n, sec, elem in FUTURES_POOL:
            if c == base:
                return c, n, sec, elem

    dn = (name or "").strip() or raw
    return raw, dn, "自选", "土"
