"""历史数据批量下载 — 多标的、多周期、自动重试。"""

from __future__ import annotations

import time

import pandas as pd


def get_history(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
    source: str = "akshare",
    retries: int = 3,
) -> pd.DataFrame:
    """获取单只股票历史 K 线。

    通过 data 模块的 DataFeed 获取，失败自动重试。
    """
    from quanttrader.data.base import BarRequest, get_feed

    feed = get_feed(source)
    req = BarRequest(symbol=symbol, start=start, end=end, interval=interval)

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return feed.history(req)
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5 * (attempt + 1))

    raise RuntimeError(f"Failed to get history for {symbol} after {retries} retries: {last_exc}")


def batch_download(
    symbols: list[str],
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
    source: str = "akshare",
    delay: float = 0.3,
) -> dict[str, pd.DataFrame]:
    """批量下载历史数据。

    Parameters
    ----------
    symbols : list[str]
        股票代码列表。
    delay : float
        请求间隔（秒），避免被封。

    Returns
    -------
    dict[str, DataFrame]
        {symbol: df} 字典，失败的标的不包含在结果中。
    """
    result: dict[str, pd.DataFrame] = {}
    for i, sym in enumerate(symbols):
        try:
            df = get_history(sym, start=start, end=end, interval=interval, source=source)
            if not df.empty:
                result[sym] = df
        except Exception as exc:
            print(f"[pipeline.historical] {sym} failed: {exc}")

        # 限速：除最后一个外等待
        if i < len(symbols) - 1:
            time.sleep(delay)

    return result


def download_date_range(
    symbols: list[str],
    start: str,
    end: str,
    interval: str = "1d",
    source: str = "akshare",
) -> dict[str, pd.DataFrame]:
    """按日期范围下载，返回按日期对齐的完整数据集。"""
    raw = batch_download(symbols, start=start, end=end, interval=interval, source=source)

    if not raw:
        return {}

    # 对齐到公共日期索引
    common_index = None
    for df in raw.values():
        if common_index is None:
            common_index = df.index
        else:
            common_index = common_index.intersection(df.index)

    if common_index is None or common_index.empty:
        return raw

    aligned: dict[str, pd.DataFrame] = {}
    for sym, df in raw.items():
        aligned[sym] = df.loc[common_index]

    return aligned
