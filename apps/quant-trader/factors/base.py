"""Factor base classes and engine registry.

All factors receive a standard OHLCV DataFrame (columns: open, high, low,
close, volume) and return a FactorResult containing the computed Series and
metadata.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


class FactorCategory(enum.Enum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    ALTERNATIVE = "alternative"
    COMPOSITE = "composite"


@dataclass
class FactorResult:
    """Output of a single factor computation."""

    name: str
    values: pd.Series
    category: FactorCategory
    description: str = ""
    meta: dict = field(default_factory=dict)

    def normalized(self) -> pd.Series:
        """Z-score normalization (cross-sectional or rolling)."""
        v = self.values.dropna()
        if len(v) < 2 or v.std() == 0:
            return self.values * 0.0
        return (self.values - v.mean()) / v.std()


class Factor(abc.ABC):
    """Abstract base for all factors.

    Subclasses must set ``name`` and ``category``, and implement ``compute``.
    Optional ``_lookback`` hints how many bars of history are needed.
    """

    name: str = "base_factor"
    category: FactorCategory = FactorCategory.TECHNICAL
    description: str = ""
    _lookback: int = 120

    @abc.abstractmethod
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """Compute factor from OHLCV DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data indexed by datetime, columns: open, high, low, close, volume.

        Returns
        -------
        FactorResult
        """
        ...

    def required_lookback(self) -> int:
        return self._lookback

    def __repr__(self) -> str:
        return f"<Factor {self.name} [{self.category.value}]>"


class FundamentalFactor(Factor):
    """Base for factors that require OHLCV + fundamental data.

    If ``fundamentals`` is passed as a Series/Dict, it is attached to the
    result as a constant or merged into a time series.
    """

    category: FactorCategory = FactorCategory.FUNDAMENTAL

    def apply_fundamental(
        self,
        series: pd.Series,
        fundamentals: dict[str, float] | pd.Series | None = None,
    ) -> pd.Series:
        """Broadcast a static fundamental value across the full index."""
        if fundamentals is None:
            return series
        if isinstance(fundamentals, dict):
            val = fundamentals.get(self.name, np.nan)
            return pd.Series(val, index=series.index, name=self.name)
        return fundamentals.reindex(series.index, method="ffill").fillna(np.nan)


class FactorEngine:
    """Registry and batch runner for factors.

    Usage::

        engine = FactorEngine()
        engine.register(RSIFactor())
        engine.register(MomentumFactor())
        results = engine.compute_all(ohlcv_df)
    """

    def __init__(self) -> None:
        self._factors: dict[str, Factor] = {}

    def register(self, factor: Factor) -> None:
        self._factors[factor.name] = factor

    def unregister(self, name: str) -> None:
        self._factors.pop(name, None)

    @property
    def factor_names(self) -> list[str]:
        return list(self._factors.keys())

    def get(self, name: str) -> Factor | None:
        return self._factors.get(name)

    def compute_all(self, df: pd.DataFrame) -> dict[str, FactorResult]:
        """Compute every registered factor. Returns dict keyed by name."""
        results: dict[str, FactorResult] = {}
        for name, factor in self._factors.items():
            try:
                results[name] = factor.compute(df)
            except Exception as exc:
                # Record NaN result so downstream can detect failure
                nan_series = pd.Series(np.nan, index=df.index, name=name)
                results[name] = FactorResult(
                    name=name,
                    values=nan_series,
                    category=factor.category,
                    description=f"FAILED: {exc}",
                )
        return results

    def compute_selected(self, df: pd.DataFrame, names: list[str]) -> dict[str, FactorResult]:
        """Compute only the factors whose names are in ``names``."""
        results: dict[str, FactorResult] = {}
        for name in names:
            factor = self._factors.get(name)
            if factor is None:
                continue
            try:
                results[name] = factor.compute(df)
            except Exception as exc:
                nan_series = pd.Series(np.nan, index=df.index, name=name)
                results[name] = FactorResult(
                    name=name,
                    values=nan_series,
                    category=factor.category,
                    description=f"FAILED: {exc}",
                )
        return results

    def to_matrix(self, results: dict[str, FactorResult]) -> pd.DataFrame:
        """Stack factor results into a (time x factors) DataFrame."""
        return pd.DataFrame({k: v.values for k, v in results.items()})
