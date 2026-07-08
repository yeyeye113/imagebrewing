"""ML-based trading strategy.

Integrates the ML pipeline into the quant-trader strategy interface.
Supports two modes:
- ``predict``: load a pre-trained model and generate signals
- ``train_predict``: train on historical data then generate signals

The strategy auto-trains if no saved model is found, making it
work out-of-the-box for backtesting.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)

# Default model directory (relative to project root)
_DEFAULT_MODEL_DIR = "models/ml_strategy"


class MLStrategy(Strategy):
    """Machine Learning trading strategy.

    Parameters
    ----------
    model_path : str
        Path to a trained model directory. If the path does not exist
        the strategy will auto-train on the provided price data.
    confidence_threshold : float
        Minimum confidence to issue BUY/SELL (below -> HOLD).
    horizon : int
        Label prediction horizon (bars ahead) for auto-training.
    label_threshold : float
        Return threshold for BUY/SELL labels in auto-training.
    model_names : list[str]
        Models for auto-training ensemble (default: ["rf", "gb"]).
    auto_train : bool
        If True and model_path doesn't exist, train automatically.
    """

    name = "ml"

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL_DIR,
        confidence_threshold: float = 0.55,
        horizon: int = 5,
        label_threshold: float = 0.02,
        model_names: list[str] | None = None,
        auto_train: bool = True,
    ):
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.horizon = horizon
        self.label_threshold = label_threshold
        self.model_names = model_names or ["rf", "gb"]
        self.auto_train = auto_train
        self._predictor = None

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        """Generate signals for the full price history.

        If a trained model exists at ``model_path``, it is loaded.
        Otherwise, if ``auto_train`` is True, the model is trained on
        *prices* before generating signals.
        """
        from .predictor import MLPredictor

        # Check if model exists
        if not self._model_exists():
            if self.auto_train:
                logger.info("No saved model found at %s. Auto-training...", self.model_path)
                self._train(prices)
            else:
                logger.warning("No saved model at %s and auto_train=False. Returning HOLD.", self.model_path)
                return pd.Series(int(Signal.HOLD), index=prices.index, dtype="int64")

        # Load predictor
        predictor = MLPredictor(self.model_path, self.confidence_threshold)
        predictor.load()

        # Generate signals
        signals = predictor.predict_series(prices)

        return signals

    def predict_latest(self, prices: pd.DataFrame) -> dict:
        """Predict signal for the latest bar only (for live/dashboard use).

        Returns a dict with signal, confidence, probabilities.
        """
        from .predictor import MLPredictor

        if not self._model_exists():
            if self.auto_train:
                self._train(prices)
            else:
                return {"signal": 0, "confidence": 0.0, "probabilities": {}, "raw_signal": 0}

        predictor = MLPredictor(self.model_path, self.confidence_threshold)
        prediction = predictor.predict(prices)
        return prediction.as_dict()

    def train(self, prices: pd.DataFrame) -> dict:
        """Explicitly train and save the model. Returns training metrics."""
        return self._train(prices)

    # -- internals ----------------------------------------------------------

    def _model_exists(self) -> bool:
        return (self.model_path / "ensemble" / "model.joblib").exists()

    def _train(self, prices: pd.DataFrame) -> dict:
        from .trainer import MLTrainer

        trainer = MLTrainer(
            horizon=self.horizon,
            threshold=self.label_threshold,
            model_names=self.model_names,
            cv_splits=5,
            label_mode="classification",
        )
        result = trainer.train(prices, model_dir=self.model_path)
        return result.metrics
