from __future__ import annotations

import pandas as pd

from .base import BarRequest, DataFeed, _normalize


class YahooDataFeed(DataFeed):
    """Real market data via Yahoo Finance (the `yfinance` package).

    No API key required. Good for free EOD / intraday equity & ETF data.
    """

    def history(self, req: BarRequest) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "yfinance is not installed. Run `pip install yfinance` "
                "or use data_source: synthetic for an offline demo."
            ) from exc

        raw = yf.download(
            tickers=req.symbol,
            start=req.start,
            end=req.end,
            interval=req.interval,
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        if raw is None or raw.empty:
            raise RuntimeError(
                f"No data returned for {req.symbol!r}. Check the symbol, date range, or your network connection."
            )
        return _normalize(raw)
