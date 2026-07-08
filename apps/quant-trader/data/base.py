from __future__ import annotations

import abc
from dataclasses import dataclass

import pandas as pd


@dataclass
class BarRequest:
    symbol: str
    start: str | None = None
    end: str | None = None
    interval: str = "1d"


class DataFeed(abc.ABC):
    """Abstract OHLCV data source.

    Implementations must return a DataFrame indexed by timestamp with columns:
    ``open, high, low, close, volume``.
    """

    @abc.abstractmethod
    def history(self, req: BarRequest) -> pd.DataFrame: ...


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case columns, keep OHLCV, sort by time, drop incomplete rows."""
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].copy()
    df = df.sort_index()
    df = df.dropna(subset=["close"])
    return df


def get_feed(name: str, **kwargs) -> DataFeed:
    """Factory: build a data feed by name, with graceful fallback.

    If ``yahoo`` is requested but yfinance is not installed, callers can catch
    the ImportError; the CLI falls back to synthetic data automatically.
    """
    name = (name or "synthetic").lower()
    if name in ("yahoo", "yfinance"):
        from .yahoo import YahooDataFeed

        return YahooDataFeed(**kwargs)
    if name in ("synthetic", "demo", "offline"):
        from .synthetic import SyntheticDataFeed

        return SyntheticDataFeed(**kwargs)
    if name in ("akshare", "cn", "ashare", "a股"):
        from .akshare_cn import AkShareDataFeed

        return AkShareDataFeed(**kwargs)
    if name in ("csv", "file"):
        from .csv_feed import CsvDataFeed

        return CsvDataFeed(**kwargs)
    raise ValueError(f"Unknown data source: {name!r}")
