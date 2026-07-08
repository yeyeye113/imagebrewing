"""期货历史 K 线 — akshare 真实数据，支持 5 年级回测窗口。"""
from __future__ import annotations

import re

import pandas as pd

from .synthetic_futures_provider import assert_not_synthetic, is_synthetic

# 与 data_backfill / sina_futures 对齐
_COL_MAP = {
    "日期": "date",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量": "volume",
    "持仓量": "open_interest",
    "动态结算价": "settlement",
    # futures_zh_daily_sina 英文列
    "date": "date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


def _normalize_symbol(code: str) -> str:
    c = str(code).strip().upper()
    if re.fullmatch(r"[A-Z]{1,4}0?", c):
        return c if c.endswith("0") else f"{c}0"
    return c


def _normalize_df(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        key = str(col).strip()
        if key in _COL_MAP:
            renamed[col] = _COL_MAP[key]
        elif key.encode("utf-8") in {k.encode("utf-8") for k in _COL_MAP}:
            for cn, en in _COL_MAP.items():
                if key == cn:
                    renamed[col] = en
                    break
    out = df.rename(columns=renamed)
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.set_index("date")
    elif not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")
    for c in ("open", "high", "low", "close", "volume"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["close"]).sort_index()
    out.attrs["source_type"] = "akshare"
    out.attrs["symbol"] = symbol
    return out


def get_futures_history(code: str, days: int = 1260) -> pd.DataFrame:
    """拉取期货主力连续日线，默认约 5 个交易日年。

    优先 ak.futures_main_sina；失败则 futures_zh_daily_sina。
    无 akshare 时仅测试环境可回退 synthetic（训练脚本应检测并拒绝）。
    """
    sym = _normalize_symbol(code)
    base = sym.rstrip("0") or sym

    try:
        import akshare as ak
    except ImportError:
        from .synthetic_futures_provider import get_synthetic_history

        return get_synthetic_history(base, days=days)

    df = None
    for fetcher, kwargs in (
        ("futures_main_sina", {"symbol": sym}),
        ("futures_zh_daily_sina", {"symbol": sym}),
    ):
        try:
            fn = getattr(ak, fetcher)
            df = fn(**kwargs)
            if df is not None and len(df) > 0:
                break
        except Exception:
            continue

    if df is None or len(df) == 0:
        from .synthetic_futures_provider import get_synthetic_history

        return get_synthetic_history(base, days=days)

    out = _normalize_df(df, base)
    if days > 0 and len(out) > days:
        out = out.tail(int(days))
    assert_not_synthetic(out, context="get_futures_history")
    return out
