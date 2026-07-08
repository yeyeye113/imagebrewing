from __future__ import annotations

import re

import pandas as pd

from .base import BarRequest, DataFeed, _normalize

# Map akshare's Chinese column names to the standard OHLCV schema.
_CN_COLS = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
}


def normalize_cn_symbol(symbol: str) -> str:
    """Extract the 6-digit A-share code from inputs like 'sh600519', '600519.SH'."""
    digits = re.findall(r"\d{6}", str(symbol))
    if not digits:
        raise ValueError(f"Not a valid A-share symbol: {symbol!r} (expected a 6-digit code).")
    return str(digits[0])


def _to_yyyymmdd(date_str: str | None, default: str) -> str:
    s = date_str or default
    if not s or s.strip() == "":
        import datetime as _dt

        s = _dt.date.today().isoformat()
    return s.replace("-", "").replace("/", "")[:8]


class AkShareDataFeed(DataFeed):
    """A-share (Shanghai/Shenzhen) market data via the free `akshare` package.

    No API token required. Returns front-adjusted (前复权) daily bars by default.
    Symbols accept plain codes ('600519'), prefixed ('sh600519'), or suffixed
    ('600519.SH') forms.
    """

    def __init__(self, adjust: str = "qfq", period: str = "daily", retries: int = 3):
        # adjust: "qfq" (前复权) | "hfq" (后复权) | "" (不复权)
        self.adjust = adjust
        self.period = period
        self.retries = max(1, int(retries))

    def history(self, req: BarRequest) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "akshare is not installed. Run `pip install akshare` for A-share data, "
                "or use data_source: synthetic for an offline demo."
            ) from exc

        code = normalize_cn_symbol(req.symbol)
        period = self.period if req.interval in (None, "1d", "daily") else req.interval

        # Bypass proxy for A-share data endpoints — CC Switch / corporate VPNs
        # interfere with eastmoney SSL connections.
        import os

        os.environ.setdefault("no_proxy", "")
        os.environ["no_proxy"] += ",eastmoney.com,push2his.eastmoney.com,"
        for _key in ("NO_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
            if os.environ.get(_key):
                os.environ.pop(_key, None)

        # akshare's free endpoints (eastmoney/sina) intermittently drop the
        # connection, so retry a few times with a short backoff before giving up.
        import time

        raw = None
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                raw = ak.stock_zh_a_hist(
                    symbol=code,
                    period=period,
                    start_date=_to_yyyymmdd(req.start, "20220101"),
                    end_date=_to_yyyymmdd(req.end, "20240101"),
                    adjust=self.adjust,
                )
                if raw is not None and not raw.empty:
                    break
            except Exception as exc:  # network hiccup — retry
                last_exc = exc
            time.sleep(0.6 * (attempt + 1))

        if raw is None or raw.empty:
            msg = f"No A-share data for {code!r} after {self.retries} tries. Check code/date/network."
            if last_exc is not None:
                raise RuntimeError(msg) from last_exc
            raise RuntimeError(msg)

        df = raw.rename(columns=_CN_COLS)
        df = df[[c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return _normalize(df)
