"""Model implementations for ML trading strategies.

Provides:
- XGBoost classifier / regressor wrappers
- Random Forest ensemble
- Model ensemble with weighted averaging and stacking
- Probability calibration

All models share a uniform ``fit / predict / predict_proba`` interface
and support save/load via joblib.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports so the module loads even if xgboost is missing
# ---------------------------------------------------------------------------


def _xgb_available() -> bool:
    try:
        import xgboost  # noqa: F401 — guard import

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Base wrapper
# ---------------------------------------------------------------------------


class _BaseModel:
    """Thin wrapper providing uniform fit/predict/save/load."""

    model_type: str = "base"

    def __init__(self, model: Any | None = None):
        # 包装的底层模型 (sklearn/xgboost 等), 本质动态类型
        self._model: Any = model
        self._feature_names: list[str] = []

    @property
    def model(self):
        return self._model

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray, **kwargs) -> _BaseModel:
        arr = X.values if isinstance(X, pd.DataFrame) else X
        self._feature_names = list(X.columns) if isinstance(X, pd.DataFrame) else []
        self._fit(arr, np.asarray(y), **kwargs)
        return self

    def _fit(self, X: np.ndarray, y: np.ndarray, **kwargs):
        self._model.fit(X, y, **kwargs)

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        arr = X.values if isinstance(X, pd.DataFrame) else X
        return np.asarray(self._model.predict(arr))

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        arr = X.values if isinstance(X, pd.DataFrame) else X
        if hasattr(self._model, "predict_proba"):
            return np.asarray(self._model.predict_proba(arr))
        # Fallback: treat predict output as single column
        preds = np.asarray(self._model.predict(arr))
        return preds.reshape(-1, 1)

    # -- persistence --------------------------------------------------------

    def save(self, path: str | Path) -> None:
        import joblib

        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, path / "model.joblib")
        meta = {"model_type": self.model_type, "feature_names": self._feature_names}
        (path / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        logger.info("Model saved to %s", path)

    def load(self, path: str | Path) -> _BaseModel:
        import joblib

        path = Path(path)
        self._model = joblib.load(path / "model.joblib")
        meta_path = path / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self._feature_names = meta.get("feature_names", [])
        return self

    def feature_importance(self) -> pd.Series | None:
        if hasattr(self._model, "feature_importances_"):
            names = self._feature_names or [f"f{i}" for i in range(len(self._model.feature_importances_))]
            return pd.Series(self._model.feature_importances_, index=names).sort_values(ascending=False)
        return None


# ---------------------------------------------------------------------------
# XGBoost
# ---------------------------------------------------------------------------


class XGBClassifierModel(_BaseModel):
    """XGBoost classifier for buy/sell/hold prediction."""

    model_type = "xgb_classifier"

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_alpha: float = 0.1,
        reg_lambda: float = 1.0,
        random_state: int = 42,
        **kwargs,
    ):
        super().__init__()
        if not _xgb_available():
            raise ImportError("xgboost is required. Install with: pip install xgboost")
        from xgboost import XGBClassifier

        self._model = XGBClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            reg_alpha=reg_alpha,
            reg_lambda=reg_lambda,
            random_state=random_state,
            use_label_encoder=False,
            eval_metric="mlogloss",
            verbosity=0,
            **kwargs,
        )

    def _fit(self, X: np.ndarray, y: np.ndarray, **kwargs):
        # Pass eval_set if provided
        eval_set = kwargs.pop("eval_set", None)
        if eval_set is not None:
            self._model.fit(X, y, eval_set=eval_set, verbose=False, **kwargs)
        else:
            self._model.fit(X, y, verbose=False, **kwargs)


class XGBRegressorModel(_BaseModel):
    """XGBoost regressor for return prediction."""

    model_type = "xgb_regressor"

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        random_state: int = 42,
        **kwargs,
    ):
        super().__init__()
        if not _xgb_available():
            raise ImportError("xgboost is required. Install with: pip install xgboost")
        from xgboost import XGBRegressor

        self._model = XGBRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            random_state=random_state,
            verbosity=0,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Random Forest
# ---------------------------------------------------------------------------


class RandomForestModel(_BaseModel):
    """Random Forest classifier with probability support."""

    model_type = "random_forest"

    def __init__(
        self,
        n_estimators: int = 500,
        max_depth: int = 12,
        min_samples_leaf: int = 10,
        max_features: str = "sqrt",
        random_state: int = 42,
        **kwargs,
    ):
        super().__init__()
        from sklearn.ensemble import RandomForestClassifier

        self._model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            random_state=random_state,
            n_jobs=-1,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Gradient Boosting (sklearn native, no xgboost needed)
# ---------------------------------------------------------------------------


class GradientBoostingModel(_BaseModel):
    """Sklearn GradientBoosting classifier — no extra dependency."""

    model_type = "gradient_boosting"

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int = 5,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        random_state: int = 42,
        **kwargs,
    ):
        super().__init__()
        from sklearn.ensemble import GradientBoostingClassifier

        self._model = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            random_state=random_state,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Model Ensemble
# ---------------------------------------------------------------------------


class ModelEnsemble:
    """Weighted ensemble of multiple models.

    Supports two fusion strategies:
    - ``"average"``: weighted average of predict_proba outputs
    - ``"stacking"``: train a logistic regression meta-learner on base model outputs

    Parameters
    ----------
    models : list of _BaseModel
        Base models to ensemble.
    weights : list of float, optional
        Model weights for averaging. If ``None``, equal weights.
    strategy : str
        ``"average"`` or ``"stacking"``.
    """

    def __init__(
        self,
        models: list[_BaseModel] | None = None,
        weights: list[float] | None = None,
        strategy: str = "average",
    ):
        self.models: list[_BaseModel] = models or []
        self.weights = weights
        self.strategy = strategy
        self._meta_learner: Any = None

    def add(self, model: _BaseModel, weight: float = 1.0) -> None:
        self.models.append(model)
        if self.weights is not None:
            self.weights.append(weight)

    def fit_stacking(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> None:
        """Train the stacking meta-learner on out-of-fold base predictions."""
        from sklearn.linear_model import LogisticRegression

        base_preds = []
        for m in self.models:
            proba = m.predict_proba(X)
            if proba.ndim == 2 and proba.shape[1] >= 2:
                base_preds.append(proba[:, 1])
            else:
                base_preds.append(proba.ravel())
        meta_X = np.column_stack(base_preds)
        self._meta_learner = LogisticRegression(random_state=42, max_iter=1000)
        self._meta_learner.fit(meta_X, np.asarray(y))

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Return ensemble probabilities. Shape (n_samples, n_classes)."""
        if not self.models:
            raise ValueError("No models in ensemble")

        if self.strategy == "stacking" and self._meta_learner is not None:
            return self._predict_stacking(X)
        return self._predict_average(X)

    def _predict_average(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        weights = self.weights or [1.0] * len(self.models)
        total_w = sum(weights)
        weighted_proba = None

        for model, w in zip(self.models, weights):
            proba = model.predict_proba(X)
            # Ensure 2-D
            if proba.ndim == 1:
                proba = proba.reshape(-1, 1)
            contribution = proba * (w / total_w)
            weighted_proba = contribution if weighted_proba is None else weighted_proba + contribution

        return weighted_proba  # type: ignore[return-value]

    def _predict_stacking(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        base_preds = []
        for m in self.models:
            proba = m.predict_proba(X)
            if proba.ndim == 2 and proba.shape[1] >= 2:
                base_preds.append(proba[:, 1])
            else:
                base_preds.append(proba.ravel())
        meta_X = np.column_stack(base_preds)
        return np.asarray(self._meta_learner.predict_proba(meta_X))

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Return class labels via argmax of ensemble probabilities."""
        proba = self.predict_proba(X)
        if proba.shape[1] == 1:
            return (proba.ravel() > 0.5).astype(int)
        return proba.argmax(axis=1)

    def save(self, path: str | Path) -> None:
        """Save all base models + meta-learner."""
        path = Path(path)
        for i, m in enumerate(self.models):
            m.save(path / f"base_{i}_{m.model_type}")
        if self._meta_learner is not None:
            import joblib

            joblib.dump(self._meta_learner, path / "meta_learner.joblib")
        meta = {
            "strategy": self.strategy,
            "weights": self.weights,
            "n_models": len(self.models),
            "model_types": [m.model_type for m in self.models],
        }
        (path / "ensemble_meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def load(self, path: str | Path) -> ModelEnsemble:
        """Load a saved ensemble."""
        import joblib

        path = Path(path)
        meta = json.loads((path / "ensemble_meta.json").read_text(encoding="utf-8"))
        self.strategy = meta["strategy"]
        self.weights = meta.get("weights")
        self.models = []
        model_classes = {
            "xgb_classifier": XGBClassifierModel,
            "xgb_regressor": XGBRegressorModel,
            "random_forest": RandomForestModel,
            "gradient_boosting": GradientBoostingModel,
        }
        for i, mtype in enumerate(meta["model_types"]):
            cls = model_classes.get(mtype, _BaseModel)
            m = cls()
            m.load(path / f"base_{i}_{mtype}")
            self.models.append(m)
        meta_learner_path = path / "meta_learner.joblib"
        if meta_learner_path.exists():
            self._meta_learner = joblib.load(meta_learner_path)
        return self


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_MODEL_REGISTRY: dict[str, type[_BaseModel]] = {
    "xgb": XGBClassifierModel,
    "xgb_classifier": XGBClassifierModel,
    "xgb_regressor": XGBRegressorModel,
    "rf": RandomForestModel,
    "random_forest": RandomForestModel,
    "gb": GradientBoostingModel,
    "gradient_boosting": GradientBoostingModel,
}


def build_model(name: str, **params) -> _BaseModel:
    """Build a model by short name."""
    name = name.lower()
    cls = _MODEL_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown model: {name!r}. Available: {list(_MODEL_REGISTRY)}")
    return cls(**params)


def build_default_ensemble(**params) -> ModelEnsemble:
    """Build the default ensemble: XGB + RF + GradientBoosting."""
    models: list[_BaseModel] = []
    if _xgb_available():
        models.append(XGBClassifierModel(**params))
    models.append(RandomForestModel(**params))
    models.append(GradientBoostingModel(**params))
    return ModelEnsemble(models=models, strategy="average")
