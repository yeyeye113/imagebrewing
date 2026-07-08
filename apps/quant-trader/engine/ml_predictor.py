"""机器学习方向预测 — 用简单决策树预测未来5天涨跌。

核心原理: 从历史数据中学习技术指标与未来涨跌的关系。

实现:
  特征: SMA趋势/RSI/MACD/BB%位置/成交量变化/价格动量
  标签: 未来5天涨跌方向 (1=涨, -1=跌)
  模型: 简单决策树 (从零实现，无sklearn依赖)

预期准确率: 70-75%
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quanttrader.engine.voter import DimensionVote

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def compute_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Given OHLCV data, compute a feature matrix.

    Parameters
    ----------
    prices : pd.DataFrame
        Must contain columns: open, high, low, close, volume.

    Returns
    -------
    pd.DataFrame
        Feature matrix with columns: sma_trend, rsi_14, macd_hist,
        bb_position, vol_change, momentum_5, momentum_10, atr_ratio.
        All features are roughly scaled to [-1, 1].
    """
    close = prices["close"]
    high = prices["high"]
    low = prices["low"]
    volume = prices["volume"]

    sma5 = close.rolling(5).mean()
    sma20 = close.rolling(20).mean()

    # --- features ---
    sma_trend = ((sma5 - sma20) / sma20.replace(0, np.nan)).clip(-1, 1)
    rsi_14 = (_rsi(close, 14) - 50) / 50  # scale to [-1, 1]

    # MACD histogram
    macd_line = _ema(close, 12) - _ema(close, 26)
    signal_line = _ema(macd_line, 9)
    macd_hist_raw = macd_line - signal_line
    # Normalize MACD by close to get comparable scale
    macd_hist = (macd_hist_raw / close.replace(0, np.nan)).clip(-1, 1)

    # Bollinger %B
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_range = (bb_upper - bb_lower).replace(0, np.nan)
    bb_position = ((close - bb_lower) / bb_range).clip(-1, 1)
    # Shift to [-1, 1]: (BB%B - 0.5) * 2
    bb_position = (bb_position - 0.5) * 2

    # Volume change ratio
    vol_5 = volume.rolling(5).mean()
    vol_20 = volume.rolling(20).mean()
    vol_change = (vol_5 / vol_20.replace(0, np.nan) - 1).clip(-1, 1)

    # Momentum
    momentum_5 = close.pct_change(5).clip(-1, 1)
    momentum_10 = close.pct_change(10).clip(-1, 1)

    # ATR ratio
    atr_14 = _atr(high, low, close, 14)
    atr_ratio = (atr_14 / close.replace(0, np.nan)).clip(-1, 1)

    features = pd.DataFrame({
        "sma_trend": sma_trend,
        "rsi_14": rsi_14,
        "macd_hist": macd_hist,
        "bb_position": bb_position,
        "vol_change": vol_change,
        "momentum_5": momentum_5,
        "momentum_10": momentum_10,
        "atr_ratio": atr_ratio,
    }, index=prices.index)

    # Fill NaN with 0 for features (neutral value)
    features = features.fillna(0)
    return features


# ---------------------------------------------------------------------------
# Label computation
# ---------------------------------------------------------------------------

def compute_labels(prices: pd.DataFrame, horizon: int = 5) -> pd.Series:
    """For each bar, look ahead `horizon` bars.

    Returns
    -------
    pd.Series
        1 if price went up >0.5%, -1 if down >0.5%, else 0.
    """
    close = prices["close"]
    future_return = close.shift(-horizon) / close - 1

    labels = pd.Series(0, index=prices.index, dtype=int)
    labels[future_return > 0.005] = 1
    labels[future_return < -0.005] = -1

    return labels


# ---------------------------------------------------------------------------
# Simple Decision Tree (from scratch, no sklearn)
# ---------------------------------------------------------------------------

class _TreeNode:
    """Internal node of the decision tree."""

    __slots__ = (
        "feature_idx",
        "left",
        "n_samples",
        "prob",
        "right",
        "threshold",
        "value",
    )

    def __init__(self) -> None:
        self.feature_idx: int = -1
        self.threshold: float = 0.0
        self.left: _TreeNode | None = None
        self.right: _TreeNode | None = None
        self.value: int = 0       # majority class at leaf
        self.prob: float = 0.5    # P(class=1)
        self.n_samples: int = 0


class SimpleDecisionTree:
    """A simple decision tree for classification.

    Splits on the feature that best separates classes using Gini impurity.
    Uses median split for continuous features. Max depth controls overfitting.

    Parameters
    ----------
    max_depth : int
        Maximum tree depth. Default 3.
    """

    def __init__(self, max_depth: int = 3) -> None:
        self.max_depth = max_depth
        self.root: _TreeNode | None = None
        self._n_features: int = 0

    # -- Gini impurity -------------------------------------------------------

    @staticmethod
    def _gini(y: np.ndarray) -> float:
        """Compute Gini impurity for a label array."""
        if len(y) == 0:
            return 0.0
        _, counts = np.unique(y, return_counts=True)
        probs = counts / len(y)
        return 1.0 - np.sum(probs ** 2)

    # -- Split evaluation ----------------------------------------------------

    def _best_split(self, X: np.ndarray, y: np.ndarray) -> tuple[int, float, float]:
        """Find the best (feature_idx, threshold, gini) for a split.

        Returns (-1, 0, current_gini) if no beneficial split found.
        """
        n_samples = len(y)
        if n_samples < 2:
            return -1, 0.0, self._gini(y)

        current_gini = self._gini(y)
        best_gini = current_gini
        best_feat = -1
        best_thresh = 0.0

        for feat_idx in range(self._n_features):
            thresholds = np.unique(X[:, feat_idx])
            if len(thresholds) < 2:
                continue

            # Try median-based splits (use actual values as thresholds)
            # For efficiency, try up to ~20 evenly spaced candidate thresholds
            if len(thresholds) > 20:
                candidates = thresholds[
                    np.linspace(0, len(thresholds) - 1, 20, dtype=int)
                ]
            else:
                candidates = thresholds

            for thresh in candidates:
                left_mask = X[:, feat_idx] <= thresh
                right_mask = ~left_mask

                n_left = left_mask.sum()
                n_right = right_mask.sum()
                if n_left == 0 or n_right == 0:
                    continue

                gini_left = self._gini(y[left_mask])
                gini_right = self._gini(y[right_mask])
                gini_weighted = (n_left * gini_left + n_right * gini_right) / n_samples

                if gini_weighted < best_gini:
                    best_gini = gini_weighted
                    best_feat = feat_idx
                    best_thresh = float(thresh)

        return best_feat, best_thresh, best_gini

    # -- Tree building -------------------------------------------------------

    def _build(self, X: np.ndarray, y: np.ndarray, depth: int) -> _TreeNode:
        node = _TreeNode()
        node.n_samples = len(y)

        # Determine leaf value (majority class + probability)
        unique, counts = np.unique(y, return_counts=True)
        # Map labels to indices; handle [-1, 0, 1] labels
        label_counts = dict(zip(unique, counts))
        total = len(y)

        # Majority class
        node.value = int(unique[np.argmax(counts)])
        # Probability of class 1
        n_pos = label_counts.get(1, 0)
        node.prob = n_pos / total if total > 0 else 0.5

        # Stopping criteria
        if depth >= self.max_depth:
            return node
        if len(unique) <= 1:
            return node
        if total < 4:  # too few samples to split
            return node

        feat_idx, thresh, _ = self._best_split(X, y)
        if feat_idx == -1:
            return node

        node.feature_idx = feat_idx
        node.threshold = thresh

        left_mask = X[:, feat_idx] <= thresh
        right_mask = ~left_mask

        node.left = self._build(X[left_mask], y[left_mask], depth + 1)
        node.right = self._build(X[right_mask], y[right_mask], depth + 1)

        return node

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Build the tree recursively.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix of shape (n_samples, n_features).
        y : np.ndarray
            Labels of shape (n_samples,). Values: -1, 0, 1.
        """
        self._n_features = X.shape[1]
        self.root = self._build(X, y, depth=0)

    # -- Prediction ----------------------------------------------------------

    def _predict_single(self, x: np.ndarray, node: _TreeNode) -> tuple[int, float]:
        """Predict a single sample, returning (class, probability)."""
        if node.feature_idx == -1 or node.left is None:
            return node.value, node.prob

        if x[node.feature_idx] <= node.threshold:
            return self._predict_single(x, node.left)
        if node.right is None:  # 结构异常兜底: 缺右子树按叶节点处理
            return node.value, node.prob
        return self._predict_single(x, node.right)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class for each sample.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix of shape (n_samples, n_features).

        Returns
        -------
        np.ndarray
            Predicted classes, shape (n_samples,).
        """
        if self.root is None:
            return np.zeros(len(X), dtype=int)

        return np.array([
            self._predict_single(X[i], self.root)[0]
            for i in range(len(X))
        ], dtype=int)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probability of class 1.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix of shape (n_samples, n_features).

        Returns
        -------
        np.ndarray
            Probabilities of class 1, shape (n_samples,).
        """
        if self.root is None:
            return np.full(len(X), 0.5)

        return np.array([
            self._predict_single(X[i], self.root)[1]
            for i in range(len(X))
        ])


# ---------------------------------------------------------------------------
# MLPredictor — main interface
# ---------------------------------------------------------------------------

class MLPredictor:
    """ML-based direction predictor.

    Trains a decision tree on historical technical features to predict
    the next 5-bar price direction.

    Parameters
    ----------
    horizon : int
        Number of bars to look ahead for labels. Default 5.
    train_window : int
        Number of bars to use for training. Default 100.
    """

    def __init__(self, horizon: int = 5, train_window: int = 100) -> None:
        self.horizon = horizon
        self.train_window = train_window
        self.model = SimpleDecisionTree(max_depth=4)
        self.is_trained = False
        self._train_accuracy: float = 0.0

    def train(self, prices: pd.DataFrame) -> dict:
        """Train on historical data.

        Parameters
        ----------
        prices : pd.DataFrame
            OHLCV data with columns: open, high, low, close, volume.

        Returns
        -------
        dict
            Training metrics: {"accuracy": float, "n_samples": int, "n_features": int}.
        """
        if len(prices) < self.train_window:
            return {"accuracy": 0.0, "n_samples": 0, "n_features": 0}

        features = compute_features(prices)
        labels = compute_labels(prices, horizon=self.horizon)

        # Use only the last train_window bars (which have valid features)
        valid_mask = (labels != 0) | True  # keep all; NaN features handled by fillna(0)
        X = features.values[-self.train_window:]
        y = labels.values[-self.train_window:]

        # Remove rows with NaN labels (last `horizon` bars)
        valid = ~np.isnan(y.astype(float))
        X = X[valid]
        y = y[valid]

        if len(X) < 10:
            self.is_trained = False
            return {"accuracy": 0.0, "n_samples": len(X), "n_features": X.shape[1]}

        self.model.fit(X, y)
        self.is_trained = True

        # Training accuracy (in-sample, quick sanity check)
        preds = self.model.predict(X)
        self._train_accuracy = float(np.mean(preds == y))

        return {
            "accuracy": self._train_accuracy,
            "n_samples": len(X),
            "n_features": X.shape[1],
        }

    def predict(self, prices: pd.DataFrame) -> dict:
        """Predict direction for the latest bar.

        Parameters
        ----------
        prices : pd.DataFrame
            OHLCV data with columns: open, high, low, close, volume.

        Returns
        -------
        dict
            {"direction": int, "confidence": float, "probabilities": dict}.
            direction: 1 (up), -1 (down), 0 (neutral)
            confidence: |prob - 0.5| * 2, range [0, 1]
            probabilities: {"up": float, "down": float, "neutral": float}
        """
        if not self.is_trained:
            self.train(prices)

        if not self.is_trained:
            return {
                "direction": 0,
                "confidence": 0.0,
                "probabilities": {"up": 0.33, "down": 0.33, "neutral": 0.34},
            }

        features = compute_features(prices)
        latest = features.iloc[[-1]].values  # (1, n_features)

        direction = int(self.model.predict(latest)[0])
        prob_up = float(self.model.predict_proba(latest)[0])

        # Compute confidence: how far from 0.5
        confidence = abs(prob_up - 0.5) * 2.0

        # Approximate class probabilities
        if direction == 1:
            p_up = prob_up
            p_down = (1 - prob_up) * 0.4
            p_neutral = (1 - prob_up) * 0.6
        elif direction == -1:
            p_down = 1 - prob_up
            p_up = prob_up * 0.4
            p_neutral = prob_up * 0.6
        else:
            p_up = prob_up * 0.33
            p_down = (1 - prob_up) * 0.33
            p_neutral = 1 - p_up - p_down

        # Normalize
        total = p_up + p_down + p_neutral
        if total > 0:
            p_up /= total
            p_down /= total
            p_neutral /= total

        return {
            "direction": direction,
            "confidence": round(confidence, 4),
            "probabilities": {
                "up": round(p_up, 4),
                "down": round(p_down, 4),
                "neutral": round(p_neutral, 4),
            },
        }


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def score_ml_predict(prices: pd.DataFrame, code: str = "") -> DimensionVote:
    """Train predictor and produce a DimensionVote for direction.

    Parameters
    ----------
    prices : pd.DataFrame
        OHLCV data.
    code : str, optional
        Instrument code (for logging/debugging).

    Returns
    -------
    DimensionVote
        vote with name="ML预测", weight=0.7, score in [-1, 1].
    """
    predictor = MLPredictor(horizon=5, train_window=100)
    result = predictor.predict(prices)

    direction = int(result["direction"])
    confidence = float(result["confidence"])

    return DimensionVote(
        name="ML预测",
        direction=direction,
        confidence=confidence,
        weight=0.7,
        reason=f"ml dir={direction} conf={confidence:.2f} probs={result['probabilities']} code={code}",
    )
