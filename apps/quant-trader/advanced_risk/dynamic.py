"""Dynamic stop-loss — volatility-adaptive stops that adjust to market conditions.

The core idea: in high-volatility environments, widen stops to avoid noise-driven
stop-outs; in low-volatility environments, tighten stops to lock in gains.

Methods:
  1. ATR-based: stop = entry - k * ATR (Average True Range)
  2. Volatility percentile: stop widens/narrows based on where current vol sits
     in its historical distribution.
  3. Chandelier exit: trailing stop based on highest high minus k * ATR.

Integration with existing risk.py:
  This module generates a RiskConfig-like dict that can be passed into
  PositionRisk.hit_stop() or used as a drop-in replacement.

Usage:
    from quanttrader.advanced_risk.dynamic import DynamicStop

    ds = DynamicStop(highs, lows, closes)
    stop_price = ds.atr_stop(entry_price, k=2.0)
    stop_price = ds.chandelier_stop(highest_since_entry, k=3.0)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StopLevel:
    """Computed dynamic stop with diagnostics."""

    stop_price: float
    method: str
    k: float  # multiplier used
    atr_value: float  # current ATR
    vol_percentile: float  # where current vol sits in history (0-100)
    cushion_pct: float  # stop distance as % of entry
    triggered: bool  # True if current price <= stop


class DynamicStop:
    """Volatility-adaptive stop-loss calculator.

    Args:
        highs: pd.Series of daily high prices.
        lows: pd.Series of daily low prices.
        closes: pd.Series of daily close prices.
        atr_period: lookback for ATR calculation (default 14).
        vol_period: lookback for volatility percentile (default 60).
    """

    def __init__(
        self,
        highs: pd.Series,
        lows: pd.Series,
        closes: pd.Series,
        atr_period: int = 14,
        vol_period: int = 60,
    ):
        # Align all series
        idx = highs.index.intersection(lows.index).intersection(closes.index)
        self.highs = highs.loc[idx].values.astype(float)
        self.lows = lows.loc[idx].values.astype(float)
        self.closes = closes.loc[idx].values.astype(float)
        self.n = len(self.closes)

        if self.n < atr_period + 1:
            raise ValueError(f"Need at least {atr_period + 1} data points, got {self.n}")

        self.atr_period = atr_period
        self.vol_period = vol_period

        # Precompute ATR series
        self._atr = self._compute_atr(atr_period)
        # Precompute daily returns for vol percentile
        self._returns = np.diff(self.closes) / self.closes[:-1]

    # ── ATR-based stop ───────────────────────────────────────────────

    def atr_stop(
        self,
        entry_price: float,
        k: float = 2.0,
        side: str = "long",
    ) -> StopLevel:
        """ATR-based stop: stop = entry - k * ATR (for long).

        Args:
            entry_price: trade entry price.
            k: ATR multiplier. Typical: 1.5-3.0. Higher = wider stop.
            side: "long" or "short".
        """
        atr = self._atr[-1]
        vol_pct = self._current_vol_percentile()

        # Adjust k based on volatility regime
        adjusted_k = self._vol_adjusted_k(k, vol_pct)

        if side == "long":
            stop_price = entry_price - adjusted_k * atr
        else:
            stop_price = entry_price + adjusted_k * atr

        current_price = self.closes[-1]
        cushion = abs(current_price - stop_price) / current_price

        return StopLevel(
            stop_price=float(stop_price),
            method="atr",
            k=adjusted_k,
            atr_value=float(atr),
            vol_percentile=float(vol_pct),
            cushion_pct=float(cushion),
            triggered=self._is_triggered(current_price, stop_price, side),
        )

    # ── Chandelier exit (trailing) ───────────────────────────────────

    def chandelier_stop(
        self,
        highest_since_entry: float,
        k: float = 3.0,
        side: str = "long",
        lowest_since_entry: float | None = None,
    ) -> StopLevel:
        """Chandelier exit: trail from highest high minus k * ATR.

        For longs: stop = highest_high - k * ATR
        For shorts: stop = lowest_low + k * ATR

        Args:
            highest_since_entry: highest price since trade entry.
            k: ATR multiplier (default 3.0 = conservative).
            lowest_since_entry: for short trades, lowest price since entry.
        """
        atr = self._atr[-1]
        vol_pct = self._current_vol_percentile()
        adjusted_k = self._vol_adjusted_k(k, vol_pct)

        current_price = self.closes[-1]

        if side == "long":
            stop_price = highest_since_entry - adjusted_k * atr
        else:
            ref = lowest_since_entry if lowest_since_entry is not None else current_price
            stop_price = ref + adjusted_k * atr

        cushion = abs(current_price - stop_price) / current_price

        return StopLevel(
            stop_price=float(stop_price),
            method="chandelier",
            k=adjusted_k,
            atr_value=float(atr),
            vol_percentile=float(vol_pct),
            cushion_pct=float(cushion),
            triggered=self._is_triggered(current_price, stop_price, side),
        )

    # ── Volatility percentile stop ───────────────────────────────────

    def vol_percentile_stop(
        self,
        entry_price: float,
        base_stop_pct: float = 0.05,
        side: str = "long",
    ) -> StopLevel:
        """Stop based on where current volatility sits in its historical distribution.

        Logic:
          - vol_percentile < 25 (calm): stop = base_stop_pct * 0.7 (tight)
          - vol_percentile 25-75 (normal): stop = base_stop_pct
          - vol_percentile > 75 (volatile): stop = base_stop_pct * 1.5 (wide)

        Args:
            entry_price: trade entry price.
            base_stop_pct: base stop distance as fraction of entry (e.g. 0.05 = 5%).
            side: "long" or "short".
        """
        vol_pct = self._current_vol_percentile()

        if vol_pct < 25:
            multiplier = 0.7
        elif vol_pct > 75:
            multiplier = 1.5
        else:
            multiplier = 1.0

        stop_pct = base_stop_pct * multiplier

        if side == "long":
            stop_price = entry_price * (1 - stop_pct)
        else:
            stop_price = entry_price * (1 + stop_pct)

        current_price = self.closes[-1]
        atr = self._atr[-1]
        cushion = abs(current_price - stop_price) / current_price

        return StopLevel(
            stop_price=float(stop_price),
            method="vol_percentile",
            k=multiplier,
            atr_value=float(atr),
            vol_percentile=float(vol_pct),
            cushion_pct=float(cushion),
            triggered=self._is_triggered(current_price, stop_price, side),
        )

    # ── Composite recommendation ─────────────────────────────────────

    def recommend(
        self,
        entry_price: float,
        highest_since_entry: float | None = None,
        side: str = "long",
    ) -> dict:
        """Compute all stop methods and return the consensus recommendation.

        Returns a dict with each method's stop and an overall recommendation
        (the tightest stop that is still reasonable).
        """
        atr_stop = self.atr_stop(entry_price, k=2.0, side=side)
        chandelier_stop = self.chandelier_stop(
            highest_since_entry=highest_since_entry or entry_price,
            k=3.0,
            side=side,
        )
        vol_stop = self.vol_percentile_stop(entry_price, base_stop_pct=0.05, side=side)

        stops = [atr_stop, chandelier_stop, vol_stop]

        # For longs: tightest (highest) stop is most protective
        if side == "long":
            best = max(stops, key=lambda s: s.stop_price)
        else:
            best = min(stops, key=lambda s: s.stop_price)

        return {
            "atr_stop": atr_stop,
            "chandelier_stop": chandelier_stop,
            "vol_percentile_stop": vol_stop,
            "recommended": best,
            "current_price": float(self.closes[-1]),
            "current_atr": float(self._atr[-1]),
        }

    # ── Internal helpers ─────────────────────────────────────────────

    def _compute_atr(self, period: int) -> np.ndarray:
        """Average True Range via Wilder's smoothing."""
        highs = self.highs
        lows = self.lows
        closes = self.closes

        # True Range
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1]),
            ),
        )

        # Wilder's smoothing (EMA with alpha = 1/period)
        atr = np.zeros(len(tr))
        atr[period - 1] = tr[:period].mean()
        for i in range(period, len(tr)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        # Pad to align with original series
        return np.concatenate([[np.nan], atr])

    def _current_vol_percentile(self) -> float:
        """Where current 20-day realized vol sits in the trailing vol_period distribution."""
        if len(self._returns) < self.vol_period:
            return 50.0  # neutral if insufficient data

        # Rolling 20-day vol (annualized)
        window = min(20, len(self._returns))
        rolling_vol = pd.Series(self._returns).rolling(window).std().dropna() * np.sqrt(252)

        if len(rolling_vol) < 2:
            return 50.0

        current_vol = rolling_vol.iloc[-1]
        pct = (rolling_vol < current_vol).sum() / len(rolling_vol) * 100
        return float(pct)

    def _vol_adjusted_k(self, base_k: float, vol_percentile: float) -> float:
        """Scale k multiplier based on volatility regime."""
        if vol_percentile < 20:
            return base_k * 0.8  # calm market: tighter stops
        elif vol_percentile > 80:
            return base_k * 1.3  # volatile market: wider stops
        return base_k

    def _is_triggered(self, price: float, stop: float, side: str) -> bool:
        if side == "long":
            return price <= stop
        return price >= stop
