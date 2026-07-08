"""AkShare 期货数据源 — 中国期货市场实时和历史数据。"""

from __future__ import annotations

import re
import time
from datetime import datetime

import pandas as pd

from .base import BarRequest, DataFeed, _normalize

# akshare 期货列名映射
_CN_FUTURES_COLS = {
    "日期": "date",
    "开盘价": "open",
    "收盘价": "close",
    "最高价": "high",
    "最低价": "low",
    "成交量": "volume",
}


def normalize_futures_symbol(symbol: str) -> str:
    """规范化期货品种代码。

    支持格式:
    - M0 → M0 (保持不变)
    - SI0 → SI0
    - si0 → SI0
    - SI → SI0 (自动补齐)
    """
    s = symbol.strip().upper()
    # 如果不以0结尾，补一个0
    if not s.endswith("0") and len(s) <= 4:
        s = s + "0"
    return s


class AkShareFuturesFeed(DataFeed):
    """中国期货市场数据 via akshare。

    支持:
    - 主力合约历史数据: ak.futures_main_sina(symbol='M0')
    - 实时行情: ak.futures_zh_realtime(symbol='M0')

    品种代码格式: M0, SI0, AU0, AG0 等
    """

    def __init__(self, retries: int = 3):
        self.retries = max(1, int(retries))

    def history(self, req: BarRequest) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError as exc:
            raise ImportError(
                "akshare is not installed. Run `pip install akshare` for futures data."
            ) from exc

        # 规范化品种代码
        symbol = normalize_futures_symbol(req.symbol)

        # 清除可能干扰的代理设置
        import os

        for _key in ("NO_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
            if os.environ.get(_key):
                os.environ.pop(_key, None)
        os.environ.setdefault("no_proxy", "")

        # 获取历史数据
        raw = None
        last_exc: Exception | None = None

        for attempt in range(self.retries):
            try:
                # 使用新浪期货主力合约数据
                raw = ak.futures_main_sina(symbol=symbol)
                if raw is not None and not raw.empty:
                    break
            except Exception as exc:
                last_exc = exc
            time.sleep(0.6 * (attempt + 1))

        if raw is None or raw.empty:
            msg = f"No futures data for {symbol!r} after {self.retries} tries."
            if last_exc is not None:
                raise RuntimeError(msg) from last_exc
            raise RuntimeError(msg)

        # 重命名列
        df = raw.rename(columns=_CN_FUTURES_COLS)

        # 只保留需要的列
        cols = ["date", "open", "high", "low", "close", "volume"]
        df = df[[c for c in cols if c in df.columns]]

        # 转换日期
        df["date"] = pd.to_datetime(df["date"])

        # 按日期排序
        df = df.sort_values("date")

        # 过滤日期范围
        if req.start:
            df = df[df["date"] >= pd.to_datetime(req.start)]
        if req.end:
            df = df[df["date"] <= pd.to_datetime(req.end)]

        df = df.set_index("date")
        return _normalize(df)

    def realtime(self, symbols: list[str]) -> dict[str, dict]:
        """获取实时行情。"""
        try:
            import akshare as ak
        except ImportError:
            return {}

        results = {}
        for symbol in symbols:
            try:
                sym = normalize_futures_symbol(symbol)
                df = ak.futures_zh_realtime(symbol=sym)
                if not df.empty:
                    results[symbol] = {
                        "symbol": sym,
                        "close": float(df.iloc[0]["最新价"]),
                        "high": float(df.iloc[0]["最高价"]),
                        "low": float(df.iloc[0]["最低价"]),
                        "open": float(df.iloc[0]["今开"]),
                        "volume": int(df.iloc[0]["成交量"]),
                        "time": df.iloc[0]["更新时间"] if "更新时间" in df.columns else "",
                    }
            except Exception:
                continue
        return results
