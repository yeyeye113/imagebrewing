"""ML training pipeline.

Provides:
- Label generation (future return classification / regression)
- Time-series aware train/test split (no look-ahead)
- Time-series cross-validation
- Feature scaling (StandardScaler / RobustScaler)
- Hyperparameter tuning via grid search
- Full pipeline: data -> features -> labels -> train -> evaluate -> save
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

from .features import FeatureEngineer
from .models import ModelEnsemble, build_model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Label generation
# ---------------------------------------------------------------------------


def make_labels(
    close: pd.Series,
    horizon: int = 5,
    threshold: float = 0.02,
    mode: str = "classification",
) -> pd.Series:
    """Generate labels from future returns.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    horizon : int
        Forward-looking bars.
    threshold : float
        Classification threshold: return > threshold -> BUY (1),
        return < -threshold -> SELL (-1), else HOLD (0).
    mode : str
        ``"classification"`` (3-class) or ``"regression"`` (raw return).

    Returns
    -------
    pd.Series
        Labels aligned to close.index. Last *horizon* bars are NaN.
    """
    future_ret = close.shift(-horizon) / close - 1
    if mode == "regression":
        return future_ret
    # 3-class classification
    labels = pd.Series(0, index=close.index, dtype="int64")
    labels[future_ret > threshold] = 1  # BUY
    labels[future_ret < -threshold] = -1  # SELL
    labels[future_ret.isna()] = np.nan
    return labels


# ---------------------------------------------------------------------------
# Training result
# ---------------------------------------------------------------------------


@dataclass
class TrainResult:
    """Container for training outputs."""

    model: ModelEnsemble
    scaler: StandardScaler
    feature_names: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)
    cv_scores: list[float] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Training complete. Features: {len(self.feature_names)}"]
        for k, v in self.metrics.items():
            lines.append(f"  {k}: {v}")
        if self.cv_scores:
            lines.append(f"  CV mean: {np.mean(self.cv_scores):.4f} +/- {np.std(self.cv_scores):.4f}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------


class MLTrainer:
    """End-to-end ML training pipeline.

    Parameters
    ----------
    horizon : int
        Prediction horizon in bars (label lookahead).
    threshold : float
        Classification threshold for BUY/SELL labels.
    model_names : list[str]
        Models to include in ensemble (e.g. ["xgb", "rf", "gb"]).
    cv_splits : int
        Number of time-series cross-validation folds.
    scaler_type : str
        ``"standard"`` or ``"robust"``.
    label_mode : str
        ``"classification"`` or ``"regression"``.
    """

    def __init__(
        self,
        horizon: int = 5,
        threshold: float = 0.02,
        model_names: list[str] | None = None,
        cv_splits: int = 5,
        scaler_type: str = "standard",
        label_mode: str = "classification",
        model_params: dict[str, dict] | None = None,
    ):
        self.horizon = horizon
        self.threshold = threshold
        self.model_names = model_names or ["rf", "gb"]
        self.cv_splits = cv_splits
        self.scaler_type = scaler_type
        self.label_mode = label_mode
        self.model_params = model_params or {}

    def train(
        self,
        prices: pd.DataFrame,
        model_dir: str | Path | None = None,
    ) -> TrainResult:
        """Full training pipeline: feature engineering -> scaling -> CV -> fit.

        Parameters
        ----------
        prices : pd.DataFrame
            OHLCV data.
        model_dir : path, optional
            Directory to save the trained model + scaler.

        Returns
        -------
        TrainResult
        """
        # 1. Feature engineering
        fe = FeatureEngineer()
        X = fe.transform(prices)
        feature_names = list(X.columns)

        # 2. Labels
        y = make_labels(prices["close"], self.horizon, self.threshold, self.label_mode)

        # 3. Drop rows with NaN in features or labels
        valid_mask = X.notna().all(axis=1) & y.notna()
        X = X.loc[valid_mask]
        y = y.loc[valid_mask]

        if len(X) < 100:
            raise ValueError(f"Not enough valid samples after cleaning: {len(X)} (need >= 100)")

        logger.info("Training on %d samples, %d features", len(X), len(feature_names))

        # 4. 时序交叉验证：传入原始未缩放 X，每折内独立 fit scaler，杜绝预处理泄漏
        #    （必须先于下面的全量 scaler.fit）。
        cv_scores = self._cross_validate(X, y)

        # 5. Scale features（全量 fit 仅用于最终部署模型——部署时全部历史已知，非泄漏）
        scaler = self._make_scaler()
        X_scaled = pd.DataFrame(
            scaler.fit_transform(X.values),
            index=X.index,
            columns=feature_names,
        )

        # 6. Final fit on all data
        y_arr = y.values.astype(int) if self.label_mode == "classification" else y.values
        ensemble = self._build_ensemble()
        for model in ensemble.models:
            model.fit(X_scaled, y_arr)

        # 8. Stacking if applicable
        if ensemble.strategy == "stacking":
            ensemble.fit_stacking(X_scaled, y_arr)

        # 9. Metrics
        metrics = self._compute_metrics(ensemble, X_scaled, y)

        result = TrainResult(
            model=ensemble,
            scaler=scaler,
            feature_names=feature_names,
            metrics=metrics,
            cv_scores=cv_scores,
        )

        # 10. Save
        if model_dir is not None:
            self._save(result, model_dir)

        logger.info(result.summary())
        return result

    # -- internals ----------------------------------------------------------

    def _make_scaler(self) -> StandardScaler:
        if self.scaler_type == "robust":
            from sklearn.preprocessing import RobustScaler

            return RobustScaler()
        return StandardScaler()

    def _build_ensemble(self) -> ModelEnsemble:
        models = []
        for name in self.model_names:
            params = self.model_params.get(name, {})
            models.append(build_model(name, **params))
        return ModelEnsemble(models=models, strategy="average")

    def _cross_validate(self, X: pd.DataFrame, y: pd.Series) -> list[float]:
        """时序交叉验证：每折内独立 fit scaler，杜绝预处理数据泄漏。

        入参 X 为**原始未缩放**特征。若在折外先对全量 X 做 StandardScaler.fit，
        验证段的均值/方差会提前泄漏进标准化，令 CV 分数乐观偏差——故标准化必须
        在每折内只用训练段拟合、再 transform 验证段。
        """
        from sklearn.metrics import accuracy_score

        tscv = TimeSeriesSplit(n_splits=self.cv_splits)
        scores = []

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_train = X.iloc[train_idx]
            X_val = X.iloc[val_idx]
            y_train = y.iloc[train_idx]
            y_val = y.iloc[val_idx]

            y_train_arr = y_train.values.astype(int) if self.label_mode == "classification" else y_train.values
            y_val_arr = y_val.values.astype(int) if self.label_mode == "classification" else y_val.values

            # 每折独立标准化：只用训练段统计量 fit，验证段仅 transform
            fold_scaler = self._make_scaler()
            X_train_s = fold_scaler.fit_transform(X_train.values)
            X_val_s = fold_scaler.transform(X_val.values)

            fold_ensemble = self._build_ensemble()
            for model in fold_ensemble.models:
                model.fit(X_train_s, y_train_arr)

            preds = fold_ensemble.predict(X_val_s)
            score = accuracy_score(y_val_arr, preds)
            scores.append(score)
            logger.info("  CV fold %d: accuracy=%.4f", fold + 1, score)

        return scores

    def _compute_metrics(self, ensemble: ModelEnsemble, X: pd.DataFrame, y: pd.Series) -> dict:
        from sklearn.metrics import accuracy_score

        y_arr = y.values.astype(int) if self.label_mode == "classification" else y.values
        preds = ensemble.predict(X)
        metrics: dict[str, Any] = {
            "train_accuracy": float(accuracy_score(y_arr, preds)),
            "n_samples": len(X),
            "n_features": X.shape[1],
        }

        # Feature importance from first model that supports it
        for model in ensemble.models:
            imp = model.feature_importance()
            if imp is not None:
                metrics["top_features"] = imp.head(10).to_dict()
                break

        return metrics

    def _save(self, result: TrainResult, model_dir: str | Path) -> None:
        model_dir = Path(model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save ensemble
        result.model.save(model_dir / "ensemble")

        # Save scaler
        import joblib

        joblib.dump(result.scaler, model_dir / "scaler.joblib")

        # Save metadata
        meta = {
            "feature_names": result.feature_names,
            "metrics": result.metrics,
            "cv_scores": result.cv_scores,
            "horizon": self.horizon,
            "threshold": self.threshold,
            "label_mode": self.label_mode,
        }
        # JSON-serializable conversion
        for k, v in meta.items():
            if isinstance(v, (np.floating, np.integer)):
                meta[k] = float(v)
        (model_dir / "train_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Pipeline saved to %s", model_dir)


def load_trained_model(model_dir: str | Path) -> tuple[ModelEnsemble, StandardScaler, list[str]]:
    """Load a saved training pipeline.

    Returns (ensemble, scaler, feature_names).
    """
    import joblib

    model_dir = Path(model_dir)
    ensemble = ModelEnsemble().load(model_dir / "ensemble")
    scaler = joblib.load(model_dir / "scaler.joblib")
    meta = json.loads((model_dir / "train_meta.json").read_text(encoding="utf-8"))
    feature_names = meta["feature_names"]
    return ensemble, scaler, feature_names
