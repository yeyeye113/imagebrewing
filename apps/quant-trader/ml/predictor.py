"""ML prediction pipeline.

Handles:
- Loading trained models
- Real-time feature computation
- Feature scaling
- Model inference
- Signal generation with confidence calibration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sklearn.preprocessing import StandardScaler

from .features import FeatureEngineer
from .models import ModelEnsemble

logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    """Single-bar prediction result."""

    signal: int  # -1 (SELL), 0 (HOLD), 1 (BUY)
    confidence: float  # 0.0 - 1.0
    probabilities: dict  # class -> probability
    raw_signal: int  # signal before confidence thresholding

    def as_dict(self) -> dict:
        return {
            "signal": self.signal,
            "confidence": round(self.confidence, 4),
            "probabilities": {k: round(v, 4) for k, v in self.probabilities.items()},
            "raw_signal": self.raw_signal,
        }


class MLPredictor:
    """Production predictor that loads a trained pipeline and generates signals.

    Parameters
    ----------
    model_dir : path
        Directory saved by :class:`MLTrainer`.
    confidence_threshold : float
        Minimum confidence to emit BUY/SELL (below -> HOLD).
    """

    def __init__(self, model_dir: str | Path, confidence_threshold: float = 0.55):
        self.model_dir = Path(model_dir)
        self.confidence_threshold = confidence_threshold
        self._ensemble: ModelEnsemble | None = None
        self._scaler: StandardScaler | None = None
        self._feature_names: list[str] = []
        self._feature_engineer = FeatureEngineer()
        self._loaded = False

    def load(self) -> None:
        """Load model, scaler, and metadata from disk."""
        from .trainer import load_trained_model

        self._ensemble, self._scaler, self._feature_names = load_trained_model(self.model_dir)
        self._loaded = True
        logger.info("MLPredictor loaded %d models, %d features", len(self._ensemble.models), len(self._feature_names))

    def predict(self, prices: pd.DataFrame, bar_index: int = -1) -> Prediction:
        """Generate a prediction for the bar at *bar_index*.

        Parameters
        ----------
        prices : pd.DataFrame
            Full OHLCV history (enough rows for feature lookback).
        bar_index : int
            Which bar to predict for (default: latest).

        Returns
        -------
        Prediction
        """
        if not self._loaded:
            self.load()
        assert self._ensemble is not None and self._scaler is not None  # load() 恒定完成装配

        # Compute features for the full history
        X_all = self._feature_engineer.transform(prices)

        # Align to saved feature names (drop extras, fill missing with 0)
        X_aligned = X_all.reindex(columns=self._feature_names, fill_value=0.0)

        # Select the target bar
        X_bar = X_aligned.iloc[[bar_index]]

        # Drop if NaN
        if X_bar.isna().any(axis=1).iloc[0]:
            return Prediction(
                signal=0, confidence=0.0, probabilities={"sell": 0.33, "hold": 0.34, "buy": 0.33}, raw_signal=0
            )

        # Scale
        X_scaled = pd.DataFrame(
            self._scaler.transform(X_bar.values),
            columns=self._feature_names,
            index=X_bar.index,
        )

        # Predict
        proba = self._ensemble.predict_proba(X_scaled)[0]
        raw_pred = int(self._ensemble.predict(X_scaled)[0])

        # Build probability dict
        if proba.shape[0] == 3:
            prob_dict = {"sell": float(proba[0]), "hold": float(proba[1]), "buy": float(proba[2])}
        elif proba.shape[0] == 2:
            prob_dict = {"sell": float(proba[0]), "buy": float(proba[1]), "hold": 0.0}
        else:
            prob_dict = {"sell": 0.0, "hold": 1.0, "buy": 0.0}

        # Confidence = max probability
        confidence = max(prob_dict.values())

        # Map prediction to signal
        signal = raw_pred
        if confidence < self.confidence_threshold:
            signal = 0  # not confident enough -> HOLD

        return Prediction(
            signal=signal,
            confidence=confidence,
            probabilities=prob_dict,
            raw_signal=raw_pred,
        )

    def predict_series(self, prices: pd.DataFrame) -> pd.Series:
        """Generate signals for the full price history.

        Returns a Series of -1/0/1 aligned to prices.index.
        Bars before the feature lookback window are HOLD (0).
        """
        if not self._loaded:
            self.load()
        assert self._ensemble is not None and self._scaler is not None  # load() 恒定完成装配

        X_all = self._feature_engineer.transform(prices)
        X_aligned = X_all.reindex(columns=self._feature_names, fill_value=0.0)

        # Scale all
        valid_mask = X_aligned.notna().all(axis=1)
        X_valid = X_aligned.loc[valid_mask]
        if len(X_valid) == 0:
            return pd.Series(0, index=prices.index, dtype="int64")

        X_scaled = pd.DataFrame(
            self._scaler.transform(X_valid.values),
            columns=self._feature_names,
            index=X_valid.index,
        )

        # Predict
        proba = self._ensemble.predict_proba(X_scaled)
        preds = self._ensemble.predict(X_scaled)

        # Apply confidence threshold
        if proba.shape[1] >= 2:
            max_proba = proba.max(axis=1)
            preds[max_proba < self.confidence_threshold] = 0

        # Build full series
        signals = pd.Series(0, index=prices.index, dtype="int64")
        signals.loc[X_valid.index] = preds.astype(int)
        return signals

    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names
