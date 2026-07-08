from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import BarRequest, DataFeed, _normalize

# Common column aliases (incl. Chinese) mapped to the standard schema.
_ALIASES = {
    "date": "date",
    "datetime": "date",
    "time": "date",
    "timestamp": "date",
    "日期": "date",
    "open": "open",
    "开盘": "open",
    "开盘价": "open",
    "high": "high",
    "最高": "high",
    "最高价": "high",
    "low": "low",
    "最低": "low",
    "最低价": "low",
    "close": "close",
    "adj close": "close",
    "收盘": "close",
    "收盘价": "close",
    "volume": "volume",
    "vol": "volume",
    "成交量": "volume",
}


class CsvDataFeed(DataFeed):
    """Load OHLCV bars from a user-provided CSV file.

    The file needs a date/time column and at least a close column; open/high/low/
    volume are filled from close/0 when missing. Column names are matched case-
    insensitively against common English and Chinese aliases.

    Usage:
        get_feed("csv", path="my_data.csv")
        # date range from BarRequest.start/end is applied if present.
    """

    def __init__(self, path: str):
        self.path = path

    def history(self, req: BarRequest) -> pd.DataFrame:
        p = Path(self.path)
        if not p.exists():
            raise FileNotFoundError(f"CSV not found: {self.path}")

        df = pd.read_csv(p)
        rename = {}
        for col in df.columns:
            key = str(col).strip().lower()
            if key in _ALIASES:
                rename[col] = _ALIASES[key]
        df = df.rename(columns=rename)

        if "date" not in df.columns:
            raise ValueError("CSV must contain a date/time column (date/datetime/日期/...).")
        if "close" not in df.columns:
            raise ValueError("CSV must contain a close column (close/收盘/...).")

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        for col in ("open", "high", "low"):
            if col not in df.columns:
                df[col] = df["close"]
        if "volume" not in df.columns:
            df["volume"] = 0

        if req.start:
            df = df[df.index >= pd.Timestamp(req.start)]
        if req.end:
            df = df[df.index <= pd.Timestamp(req.end)]
        if df.empty:
            raise RuntimeError("CSV had no rows in the requested date range.")
        return _normalize(df)
