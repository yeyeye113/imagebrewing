"""ML预测层 — 用43269条历史数据训练决策树预测方向。

核心原理: 从历史数据中学习技术指标与未来涨跌的非线性关系。

特征:
  1. RSI(14)
  2. BB%B
  3. MACD柱状图
  4. 5日/10日/20日动量
  5. 成交量比
  6. ATR波动率
  7. SMA趋势

标签: 未来10天涨跌方向 (1=涨, -1=跌)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class MLPrediction:
    direction: int      # 1=多, -1=空, 0=中性
    confidence: float   # 0~1
    reason: str = ""


def _compute_features(prices: pd.DataFrame) -> pd.DataFrame:
    """计算ML特征矩阵。"""
    closes = prices['close'].astype(float)
    highs = prices['high'].astype(float) if 'high' in prices.columns else closes
    lows = prices['low'].astype(float) if 'low' in prices.columns else closes
    n = len(closes)

    features = pd.DataFrame(index=prices.index)

    # RSI(14)
    returns = closes.pct_change()
    rsi_list = []
    for i in range(14, n):
        gains = [float(returns.iloc[j]) for j in range(i-13, i+1)
                 if not np.isnan(returns.iloc[j]) and returns.iloc[j] > 0]
        losses = [abs(float(returns.iloc[j])) for j in range(i-13, i+1)
                  if not np.isnan(returns.iloc[j]) and returns.iloc[j] < 0]
        avg_g = np.mean(gains) if gains else 0.001
        avg_l = np.mean(losses) if losses else 0.001
        rsi_list.append(100 - (100 / (1 + avg_g / avg_l)))
    features['rsi'] = np.nan
    features.iloc[14:, features.columns.get_loc('rsi')] = rsi_list[:n-14]

    # BB%B
    bb_mid = closes.rolling(20).mean()
    bb_std = closes.rolling(20).std()
    bb_upper = bb_mid + 2*bb_std
    bb_lower = bb_mid - 2*bb_std
    features['bb_pct'] = (closes - bb_lower) / (bb_upper - bb_lower)

    # MACD
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    features['macd_hist'] = (macd_line - signal_line) / closes * 100  # 标准化

    # 动量
    features['mom_5'] = closes.pct_change(5)
    features['mom_10'] = closes.pct_change(10)
    features['mom_20'] = closes.pct_change(20)

    # 成交量比
    if 'volume' in prices.columns:
        vol = prices['volume'].astype(float)
        vol_ma20 = vol.rolling(20).mean()
        features['vol_ratio'] = vol / vol_ma20
    else:
        features['vol_ratio'] = 1.0

    # ATR波动率
    trs = []
    for i in range(1, n):
        h, l, pc = float(highs.iloc[i]), float(lows.iloc[i]), float(closes.iloc[i-1])
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    tr = pd.Series(trs, index=closes.index[1:])
    atr14 = tr.rolling(14).mean()
    features['atr_ratio'] = atr14 / closes

    # SMA趋势
    sma5 = closes.rolling(5).mean()
    sma20 = closes.rolling(20).mean()
    features['sma_trend'] = (sma5 - sma20) / sma20

    return features


def _compute_labels(prices: pd.DataFrame, horizon: int = 10) -> pd.Series:
    """计算标签: 未来horizon天涨跌方向。"""
    closes = prices['close'].astype(float)
    future_return = closes.shift(-horizon) / closes - 1
    labels = pd.Series(0, index=prices.index)
    labels[future_return > 0.005] = 1   # 涨>0.5% → 1
    labels[future_return < -0.005] = -1  # 跌>0.5% → -1
    return labels


class SimpleDecisionTree:
    """简单决策树(从零实现，无sklearn依赖)。"""

    def __init__(self, max_depth: int = 4):
        self.max_depth = max_depth
        self.tree = None

    def _gini(self, y: np.ndarray) -> float:
        """计算基尼不纯度。"""
        if len(y) == 0:
            return 0.0
        classes, counts = np.unique(y, return_counts=True)
        probs = counts / len(y)
        return 1.0 - np.sum(probs ** 2)

    def _best_split(self, X: np.ndarray, y: np.ndarray):
        """找最佳分裂点。"""
        n_samples, n_features = X.shape
        best_gini = float('inf')
        best_feature = -1
        best_threshold = 0.0

        for feature in range(n_features):
            thresholds = np.unique(X[:, feature])
            # 采样阈值(加速)
            if len(thresholds) > 20:
                thresholds = np.percentile(thresholds, np.linspace(0, 100, 20))

            for threshold in thresholds:
                left_mask = X[:, feature] <= threshold
                right_mask = ~left_mask
                if left_mask.sum() == 0 or right_mask.sum() == 0:
                    continue

                left_gini = self._gini(y[left_mask])
                right_gini = self._gini(y[right_mask])
                weighted_gini = (left_mask.sum() * left_gini + right_mask.sum() * right_gini) / n_samples

                if weighted_gini < best_gini:
                    best_gini = weighted_gini
                    best_feature = feature
                    best_threshold = threshold

        return best_feature, best_threshold, best_gini

    def _build_tree(self, X: np.ndarray, y: np.ndarray, depth: int = 0):
        """递归构建决策树。"""
        # 终止条件
        if depth >= self.max_depth or len(np.unique(y)) <= 1 or len(y) < 5:
            classes, counts = np.unique(y, return_counts=True)
            majority = classes[np.argmax(counts)]
            prob_1 = np.sum(y == 1) / len(y) if len(y) > 0 else 0.5
            return {'leaf': True, 'class': majority, 'prob_1': prob_1, 'n': len(y)}

        feature, threshold, gini = self._best_split(X, y)
        if feature == -1 or gini >= self._gini(y):
            classes, counts = np.unique(y, return_counts=True)
            majority = classes[np.argmax(counts)]
            prob_1 = np.sum(y == 1) / len(y) if len(y) > 0 else 0.5
            return {'leaf': True, 'class': majority, 'prob_1': prob_1, 'n': len(y)}

        left_mask = X[:, feature] <= threshold
        right_mask = ~left_mask

        return {
            'leaf': False,
            'feature': feature,
            'threshold': threshold,
            'left': self._build_tree(X[left_mask], y[left_mask], depth + 1),
            'right': self._build_tree(X[right_mask], y[right_mask], depth + 1),
        }

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """训练决策树。"""
        self.tree = self._build_tree(X, y)

    def _predict_one(self, x: np.ndarray, node: dict) -> float:
        """预测单个样本的类别1概率。"""
        if node['leaf']:
            return node['prob_1']
        if x[node['feature']] <= node['threshold']:
            return self._predict_one(x, node['left'])
        else:
            return self._predict_one(x, node['right'])

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率。"""
        return np.array([self._predict_one(x, self.tree) for x in X])

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别。"""
        proba = self.predict_proba(X)
        result = np.zeros(len(X), dtype=int)
        result[proba > 0.55] = 1
        result[proba < 0.45] = -1
        return result


class MLPredictor:
    """ML预测器: 训练+预测一体化。"""

    def __init__(self, horizon: int = 10, train_window: int = 500):
        self.horizon = horizon
        self.train_window = train_window
        self.model = SimpleDecisionTree(max_depth=4)
        self.feature_names = ['rsi', 'bb_pct', 'macd_hist', 'mom_5', 'mom_10',
                              'mom_20', 'vol_ratio', 'atr_ratio', 'sma_trend']
        self.is_trained = False

    def train(self, prices: pd.DataFrame) -> dict:
        """训练模型。"""
        features = _compute_features(prices)
        labels = _compute_labels(prices, self.horizon)

        # 对齐并去NaN
        valid = features.dropna().index.intersection(labels.dropna().index)
        X = features.loc[valid].values
        y = labels.loc[valid].values

        if len(X) < 50:
            return {'accuracy': 0, 'n_samples': len(X), 'error': 'insufficient data'}

        # 用最近train_window个样本训练
        X_train = X[-self.train_window:]
        y_train = y[-self.train_window:]

        self.model.fit(X_train, y_train)
        self.is_trained = True

        # 训练集准确率
        pred = self.model.predict(X_train)
        accuracy = np.mean(pred == y_train)

        return {
            'accuracy': float(accuracy),
            'n_samples': len(X_train),
            'n_features': len(self.feature_names),
        }

    def predict(self, prices: pd.DataFrame) -> MLPrediction:
        """预测最新一根K线的方向。"""
        if not self.is_trained:
            self.train(prices)

        features = _compute_features(prices)
        latest = features.iloc[-1:].values

        if np.any(np.isnan(latest)):
            return MLPrediction(0, 0.0, "特征包含NaN")

        proba = self.model.predict_proba(latest)[0]
        direction = 1 if proba > 0.55 else (-1 if proba < 0.45 else 0)
        confidence = abs(proba - 0.5) * 2  # 0~1

        reason = f"ML概率={proba:.2f} RSI={latest[0][0]:.0f} BB%B={latest[0][1]:.2f}"
        return MLPrediction(direction=direction, confidence=confidence, reason=reason)


def score_ml(prices: pd.DataFrame, code: str = "") -> MLPrediction:
    """ML预测入口。"""
    predictor = MLPredictor(horizon=10, train_window=min(500, len(prices)-50))
    return predictor.predict(prices)
