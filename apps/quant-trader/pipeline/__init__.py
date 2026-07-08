"""数据管道 — 统一获取接口（实时 / 历史 / 缓存 / 质量检查）。

用法::

    from quanttrader.pipeline import Pipeline

    pipe = Pipeline(symbols=["600519", "000001"], cache_dir="cache")
    # 历史数据（自动缓存）
    df = pipe.history("600519", start="2024-01-01")
    # 实时行情（WebSocket / fallback 轮询）
    quote = pipe.realtime("600519")
    # 批量下载
    pipe.batch_download(start="2024-01-01")
    # 质量检查
    report = pipe.quality_check("600519")
"""

from __future__ import annotations

import datetime as _dt
import pathlib
from typing import Any

import pandas as pd

from .cache import FileCache
from .historical import batch_download, get_history
from .quality import QualityReport, check_quality
from .realtime import RealtimeQuote, get_realtime

__all__ = [
    "Pipeline",
    "QualityReport",
    "RealtimeQuote",
]


class Pipeline:
    """统一数据管道入口。

    Parameters
    ----------
    symbols : list[str]
        关注的股票代码列表。
    cache_dir : str | Path
        本地缓存目录，默认 ``cache/``。
    cache_ttl : int
        缓存有效期（秒），默认 3600（1 小时）。
    data_source : str
        底层数据源，默认 ``akshare``。
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        cache_dir: str | pathlib.Path = "cache",
        cache_ttl: int = 3600,
        data_source: str = "akshare",
    ) -> None:
        self.symbols: list[str] = symbols or []
        self.cache = FileCache(str(cache_dir), ttl=cache_ttl)
        self.data_source = data_source

    # ── 历史数据 ──────────────────────────────────────────────
    def history(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        interval: str = "1d",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """获取历史 K 线，自动走缓存。"""
        if use_cache:
            cached = self.cache.get(symbol, start=start, end=end, interval=interval)
            if cached is not None:
                return cached

        df = get_history(symbol, start=start, end=end, interval=interval, source=self.data_source)

        if use_cache and not df.empty:
            self.cache.put(symbol, df, start=start, end=end, interval=interval)

        return df

    # ── 实时行情 ──────────────────────────────────────────────
    def realtime(self, symbol: str) -> RealtimeQuote:
        """获取最新实时行情（不走缓存）。"""
        return get_realtime(symbol)

    def realtime_batch(self, symbols: list[str] | None = None) -> list[RealtimeQuote]:
        """批量获取实时行情。"""
        syms = symbols or self.symbols
        return [get_realtime(s) for s in syms]

    # ── 批量下载 ──────────────────────────────────────────────
    def batch_download(
        self,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        interval: str = "1d",
        force: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """批量下载历史数据并写入缓存。

        Parameters
        ----------
        force : bool
            True 时忽略缓存强制重新下载。
        """
        syms = symbols or self.symbols
        result: dict[str, pd.DataFrame] = {}
        for sym in syms:
            if not force:
                cached = self.cache.get(sym, start=start, end=end, interval=interval)
                if cached is not None and not cached.empty:
                    result[sym] = cached
                    continue
            try:
                df = batch_download(symbols=[sym], start=start, end=end, interval=interval, source=self.data_source)
                if sym in df:
                    result[sym] = df[sym]
                    self.cache.put(sym, df[sym], start=start, end=end, interval=interval)
            except Exception as exc:
                print(f"[pipeline] batch_download {sym} failed: {exc}")
        return result

    # ── 数据质量 ──────────────────────────────────────────────
    def quality_check(self, symbol: str, use_cache: bool = True) -> QualityReport:
        """对指定标的执行数据质量检查。"""
        df = self.history(symbol, use_cache=use_cache)
        return check_quality(df, symbol=symbol)

    def quality_report(self, symbols: list[str] | None = None, use_cache: bool = True) -> dict[str, QualityReport]:
        """批量质量检查。"""
        syms = symbols or self.symbols
        return {s: self.quality_check(s, use_cache=use_cache) for s in syms}
