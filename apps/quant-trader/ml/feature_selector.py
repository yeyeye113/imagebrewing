"""Feature selection and dimensionality reduction.

Implements multiple feature selection strategies:
1. Statistical: variance threshold, correlation filtering
2. Model-based: feature importance from RandomForest
3. Information-theoretic: mutual information
4. Recursive Feature Elimination (RFE)

All selection is done on training data only to avoid leakage.
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FeatureSelector:
    """Multi-strategy feature selector.

    Strategies:
    - variance: Remove low-variance features
    - correlation: Remove highly correlated features
    - importance: Use RandomForest importance
    - mutual_info: Use mutual information with target
    - hybrid: Combine multiple strategies

    Usage:
        selector = FeatureSelector(strategy="hybrid", k=15)
        X_train_selected = selector.fit_transform(X_train, y_train)
        X_test_selected = selector.transform(X_test)
    """

    def __init__(
        self,
        strategy: Literal["variance", "correlation", "importance", "mutual_info", "hybrid"] = "hybrid",
        k: int = 15,
        variance_thresh: float = 0.01,
        correlation_thresh: float = 0.9,
        importance_thresh: float = 0.01,
        random_state: int = 42,
    ):
        """
        Args:
            strategy: Selection strategy
            k: Target number of features (for importance/mutual_info)
            variance_thresh: Minimum variance ratio for variance strategy
            correlation_thresh: Maximum allowed correlation between features
            importance_thresh: Minimum importance score
            random_state: Random seed for reproducibility
        """
        self.strategy = strategy
        self.k = k
        self.variance_thresh = variance_thresh
        self.correlation_thresh = correlation_thresh
        self.importance_thresh = importance_thresh
        self.random_state = random_state
        self.selected_features: list[str] = []
        self._importance_scores: dict[str, float] = {}

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "FeatureSelector":
        """Fit feature selector on training data.

        Args:
            X: Feature DataFrame (n_samples, n_features)
            y: Target Series (n_samples,)

        Returns:
            self
        """
        if self.strategy == "variance":
            self._fit_variance(X)
        elif self.strategy == "correlation":
            self._fit_correlation(X)
        elif self.strategy == "importance":
            self._fit_importance(X, y)
        elif self.strategy == "mutual_info":
            self._fit_mutual_info(X, y)
        elif self.strategy == "hybrid":
            self._fit_hybrid(X, y)

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Transform X by keeping only selected features."""
        if not self.selected_features:
            return X
        missing = set(self.selected_features) - set(X.columns)
        if missing:
            logger.warning(f"Selected features not in X: {missing}")
            return X[[f for f in self.selected_features if f in X.columns]]
        return X[self.selected_features]

    def fit_transform(self, X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
        """Fit and transform in one call."""
        return self.fit(X, y).transform(X)

    def _fit_variance(self, X: pd.DataFrame) -> None:
        """Select features with variance above threshold."""
        variances = X.var()
        max_var = variances.max()
        if max_var > 0:
            variance_ratios = variances / max_var
            self.selected_features = variance_ratios[variance_ratios >= self.variance_thresh].index.tolist()
        else:
            self.selected_features = X.columns.tolist()
        logger.info(f"Variance selection: {len(self.selected_features)}/{len(X.columns)} features")

    def _fit_correlation(self, X: pd.DataFrame) -> None:
        """Remove highly correlated features."""
        corr_matrix = X.corr().abs()

        # Find pairs with high correlation
        upper_tri = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
        to_drop = set()
        for col in upper_tri.columns:
            high_corr = upper_tri[col] > self.correlation_thresh
            if high_corr.any():
                # Drop the feature with lower variance
                col_var = X[col].var()
                for correlated_col in upper_tri.index[high_corr]:
                    if X[correlated_col].var() < col_var:
                        to_drop.add(correlated_col)
                    else:
                        to_drop.add(col)

        self.selected_features = [c for c in X.columns if c not in to_drop]
        logger.info(f"Correlation selection: {len(self.selected_features)}/{len(X.columns)} features")

    def _fit_importance(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Select features using RandomForest importance."""
        from sklearn.ensemble import RandomForestRegressor

        rf = RandomForestRegressor(
            n_estimators=100, max_depth=6, random_state=self.random_state, n_jobs=-1
        )
        rf.fit(X, y)

        importances = dict(zip(X.columns, rf.feature_importances_))
        self._importance_scores = importances

        # Sort by importance and take top k
        sorted_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)
        self.selected_features = [f for f, score in sorted_features[: self.k] if score >= self.importance_thresh]

        logger.info(f"Importance selection: {len(self.selected_features)}/{len(X.columns)} features")

    def _fit_mutual_info(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Select features using mutual information."""
        from sklearn.feature_selection import mutual_info_regression

        # Handle non-numeric columns
        X_num = X.select_dtypes(include=[np.number])

        mi_scores = mutual_info_regression(X_num, y, random_state=self.random_state)
        mi_dict = dict(zip(X_num.columns, mi_scores))
        self._importance_scores = mi_dict

        # Sort by MI and take top k
        sorted_features = sorted(mi_dict.items(), key=lambda x: x[1], reverse=True)
        self.selected_features = [f for f, score in sorted_features[: self.k] if score > 0]

        logger.info(f"Mutual info selection: {len(self.selected_features)}/{len(X.columns)} features")

    def _fit_hybrid(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Combine multiple strategies."""
        # Step 1: Remove low variance
        self._fit_variance(X)
        if len(self.selected_features) <= self.k:
            return
        X_variance = X[self.selected_features]

        # Step 2: Remove highly correlated
        self._fit_correlation(X_variance)
        if len(self.selected_features) <= self.k:
            return
        X_corr = X_variance[self.selected_features] if self.strategy != "variance" else X_variance

        # Re-apply correlation on variance-filtered data
        if len(self.selected_features) > self.k:
            corr_matrix = X_corr.corr().abs()
            upper_tri = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
            to_drop = set()
            for col in upper_tri.columns:
                high_corr = upper_tri[col] > self.correlation_thresh
                if high_corr.any():
                    col_var = X_corr[col].var()
                    for correlated_col in upper_tri.index[high_corr]:
                        if X_corr[correlated_col].var() < col_var:
                            to_drop.add(correlated_col)
                        else:
                            to_drop.add(col)
            self.selected_features = [c for c in self.selected_features if c not in to_drop]

        if len(self.selected_features) <= self.k:
            return

        # Step 3: Use importance to pick final k
        self._fit_importance(X_corr, y)
        if len(self.selected_features) > self.k:
            # Fall back to top-k
            sorted_features = sorted(self._importance_scores.items(), key=lambda x: x[1], reverse=True)
            self.selected_features = [f for f, _ in sorted_features[: self.k]]

        logger.info(f"Hybrid selection: {len(self.selected_features)}/{len(X.columns)} features")

    def get_importance_scores(self) -> dict[str, float]:
        """Get feature importance scores (after fit)."""
        return self._importance_scores.copy()

    def get_selected_features(self) -> list[str]:
        """Get list of selected feature names."""
        return self.selected_features.copy()


class RecursiveFeatureEliminator:
    """Recursive Feature Elimination (RFE) wrapper.

    Repeatedly trains model and removes weakest features until
    target number is reached.
    """

    def __init__(
        self,
        estimator=None,
        n_features_to_select: int = 15,
        step: int = 1,
        verbose: int = 0,
    ):
        from sklearn.ensemble import RandomForestClassifier

        self.estimator = estimator or RandomForestClassifier(
            n_estimators=50, max_depth=5, random_state=42, n_jobs=-1
        )
        self.n_features_to_select = n_features_to_select
        self.step = step
        self.verbose = verbose
        self.selected_features: list[str] = []
        self.ranking_: dict[str, int] = {}

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RecursiveFeatureEliminator":
        """Fit RFE on training data."""
        from sklearn.feature_selection import RFE

        rfe = RFE(self.estimator, n_features_to_select=self.n_features_to_select, step=self.step, verbose=self.verbose)
        rfe.fit(X, y)

        self.ranking_ = dict(zip(X.columns, rfe.ranking_))
        self.selected_features = X.columns[rfe.support_].tolist()

        if self.verbose:
            logger.info(f"RFE selected {len(self.selected_features)} features")
            logger.info(f"Feature rankings: {dict(sorted(self.ranking_.items(), key=lambda x: x[1])[:10])}")

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Transform X by keeping only selected features."""
        return X[self.selected_features]

    def fit_transform(self, X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
        """Fit and transform in one call."""
        return self.fit(X, y).transform(X)
