from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .base import BarRequest, DataFeed, _normalize


def _stable_symbol_offset(symbol: str) -> int:
    """Deterministic per-symbol seed offset.

    Python's built-in hash() is salted per process (PYTHONHASHSEED), which would
    make synthetic prices differ between runs. Use a stable digest instead so
    backtests are reproducible.
    """
    digest = hashlib.sha256(symbol.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 10_000


class SyntheticDataFeed(DataFeed):
    """Offline geometric-brownian-motion price generator.

    Lets the whole stack run end-to-end with zero network access, so you can
    try the engine before wiring up a real data source or broker.
    """

    def __init__(self, seed: int = 42, mu: float = 0.08, sigma: float = 0.20, s0: float = 100.0):
        self.seed = seed
        self.mu = mu  # annual drift
        self.sigma = sigma  # annual volatility
        self.s0 = s0  # starting price

    def history(self, req: BarRequest) -> pd.DataFrame:
        start = pd.Timestamp(req.start or "2022-01-01")
        end = pd.Timestamp(req.end or "2024-01-01")
        # Use a fixed business-day grid so results are deterministic per seed.
        idx = pd.bdate_range(start=start, end=end)
        n = len(idx)
        if n < 2:
            raise RuntimeError("Date range too short to generate synthetic data.")

        rng = np.random.default_rng(self.seed + _stable_symbol_offset(req.symbol))
        dt = 1.0 / 252.0
        shocks = rng.normal(
            (self.mu - 0.5 * self.sigma**2) * dt,
            self.sigma * np.sqrt(dt),
            size=n,
        )
        close = self.s0 * np.exp(np.cumsum(shocks))

        # Build plausible OHLC around the close path.
        noise = np.abs(rng.normal(0, 0.005, size=n))
        open_ = np.concatenate([[self.s0], close[:-1]])
        high = np.maximum(open_, close) * (1 + noise)
        low = np.minimum(open_, close) * (1 - noise)
        volume = rng.integers(1_000_000, 5_000_000, size=n)

        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=idx,
        )
        return _normalize(df)
