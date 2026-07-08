"""v14 ML高低点预测适配器 — 接入daemon用。

加载v14训练好的LightGBM高低点回归模型，预测未来N天的最高价/最低价。
输出格式与v530 Prediction兼容，可无缝接入daemon决策流。

用法:
    from quanttrader.ml.ml_v14_hl import predict_hl
    pred = predict_hl("AG", closes, highs, lows)
    # pred = {"predicted_high": 8500, "predicted_low": 8200, "range_pct": 3.6, ...}
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)

_MODEL_PATH = Path("logs/ml_final.pkl")
_model_cache = None


@dataclass
class MLPrediction:
    """v14 ML高低点预测结果。"""
    predicted_high: float
    predicted_low: float
    current_price: float
    range_pct: float
    volatility: str
    method: str = "ml_v14"
    model_version: str = "v14"

    @property
    def stop_distance_pct(self) -> float:
        return max(1.0, (self.current_price - self.predicted_low) / self.current_price * 100)

    @property
    def target_distance_pct(self) -> float:
        return max(1.0, (self.predicted_high - self.current_price) / self.current_price * 100)

    @property
    def is_tradeable(self) -> bool:
        return self.range_pct >= 1.5

    def to_v530(self):
        """转换为v530 Prediction格式，兼容现有daemon。"""
        from quanttrader.predictor.hl_predict import Prediction
        return Prediction(
            predicted_high=self.predicted_high,
            predicted_low=self.predicted_low,
            current_price=self.current_price,
            range_pct=self.range_pct,
            volatility=self.volatility,
        )


def _load_model():
    """懒加载v14模型。"""
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    if not _MODEL_PATH.exists():
        logger.warning("v14模型不存在: %s", _MODEL_PATH)
        return None
    try:
        import joblib
        _model_cache = joblib.load(_MODEL_PATH)
        logger.info("v14模型加载成功 (特征=%d)", len(_model_cache.get("feature_cols", [])))
        return _model_cache
    except Exception as e:
        logger.error("v14模型加载失败: %s", e)
        return None


def _compute_features(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> pd.DataFrame | None:
    """计算v14模型所需的特征向量 (与训练时 ml_highlow_v14.py 完全一致)。"""
    c = pd.Series(closes)
    h = pd.Series(highs)
    lo = pd.Series(lows)
    vols = pd.Series(np.ones(len(closes)))  # 无真实成交量，用占位

    features = {}
    features['close'] = c
    features['close_pct'] = c.pct_change()

    for w in [5, 10, 20, 60]:
        features[f'sma_{w}'] = c.rolling(w).mean()
        features[f'close_sma_{w}_ratio'] = c / c.rolling(w).mean()

    features['high_5d'] = h.rolling(5).max()
    features['low_5d'] = lo.rolling(5).min()
    features['high_20d'] = h.rolling(20).max()
    features['low_20d'] = lo.rolling(20).min()
    features['close_position'] = (c - features['low_20d']) / (features['high_20d'] - features['low_20d'] + 1e-10)

    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    features['rsi_14'] = 100 - (100 / (1 + rs))

    ema12 = c.ewm(span=12).mean()
    ema26 = c.ewm(span=26).mean()
    features['macd'] = ema12 - ema26
    features['macd_signal'] = features['macd'].ewm(span=9).mean()
    features['macd_hist'] = features['macd'] - features['macd_signal']

    for w in [5, 10, 20]:
        features[f'roc_{w}'] = (c / c.shift(w) - 1) * 100

    tr = pd.concat([h-lo, (h-c.shift(1)).abs(), (lo-c.shift(1)).abs()], axis=1).max(axis=1)
    for w in [10, 14, 20]:
        features[f'atr_{w}'] = tr.rolling(w).mean()
    features['atr_ratio'] = features['atr_10'] / (features['atr_20'] + 1e-10)

    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    features['bb_pct'] = (c - (sma20 - 2*std20)) / (4*std20 + 1e-10)
    features['bb_width'] = (4*std20) / (sma20 + 1e-10)

    returns = c.pct_change()
    features['vol_5'] = returns.rolling(5).std() * np.sqrt(252)
    features['vol_20'] = returns.rolling(20).std() * np.sqrt(252)
    features['vol_ratio'] = features['vol_5'] / (features['vol_20'] + 1e-10)
    features['vol_sma5'] = vols.rolling(5).mean()
    features['vol_sma5_ratio'] = vols / (features['vol_sma5'] + 1e-10)

    obv = (np.sign(c.diff()) * vols).cumsum()
    features['obv_slope'] = obv.rolling(5).apply(lambda x: np.polyfit(range(5), x, 1)[0] if len(x) == 5 else 0, raw=True)

    plus_dm = h.diff().clip(lower=0)
    minus_dm = (-lo.diff()).clip(lower=0)
    plus_di = plus_dm.rolling(14).mean() / (tr.rolling(14).mean() + 1e-10) * 100
    minus_di = minus_dm.rolling(14).mean() / (tr.rolling(14).mean() + 1e-10) * 100
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10) * 100
    features['adx'] = dx.rolling(14).mean()

    features['sma5_20_cross'] = (features['sma_5'] - features['sma_20']) / (features['sma_20'] + 1e-10)
    features['sma10_60_cross'] = (features['sma_10'] - features['sma_60']) / (features['sma_60'] + 1e-10)

    prev_high = h.shift(1); prev_low = lo.shift(1); prev_close = c.shift(1)
    pivot = (prev_high + prev_low + prev_close) / 3
    features['pivot_dist'] = (c - pivot) / (pivot + 1e-10)
    features['donchian_pct'] = (c - lo.rolling(20).min()) / (h.rolling(20).max() - lo.rolling(20).min() + 1e-10)

    # 移除不需要的列
    for k in ['close']:
        features.pop(k, None)

    feat_df = pd.DataFrame(features)
    last_valid = feat_df.dropna().iloc[-1:] if not feat_df.dropna().empty else None
    return last_valid


def predict_hl(
    symbol: str,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    horizon: int = 2,
) -> MLPrediction | None:
    """用v14 ML模型预测未来N天高低点。

    Args:
        symbol: 品种代码
        closes: 收盘价数组
        highs: 最高价数组
        lows: 最低价数组
        horizon: 预测天数

    Returns:
        MLPrediction or None
    """
    if len(closes) < 60:
        return None

    model_data = _load_model()
    if model_data is None:
        return None

    try:
        # 计算特征
        features = _compute_features(closes, highs, lows)
        if features is None or len(features) == 0:
            return None

        # 对齐特征列
        model_cols = model_data.get("feature_cols", [])
        if not model_cols:
            return None

        # 确保特征列顺序一致
        X = np.zeros((1, len(model_cols)))
        for i, col in enumerate(model_cols):
            if col in features.columns:
                X[0, i] = features[col].iloc[0]

        # 预测
        lgb_high = model_data.get("lgb_high")
        lgb_low = model_data.get("lgb_low")

        if lgb_high is None or lgb_low is None:
            return None

        pred_high_pct = float(lgb_high.predict(X)[0])
        pred_low_pct = float(lgb_low.predict(X)[0])

        current = float(closes[-1])
        predicted_high = current * (1 + pred_high_pct)
        predicted_low = current * (1 + pred_low_pct)

        range_pct = (predicted_high - predicted_low) / current * 100

        # 波动率分类
        if range_pct < 2:
            vol = "low"
        elif range_pct < 5:
            vol = "normal"
        else:
            vol = "high"

        return MLPrediction(
            predicted_high=predicted_high,
            predicted_low=predicted_low,
            current_price=current,
            range_pct=range_pct,
            volatility=vol,
            method="ml_v14",
            model_version="v14",
        )
    except Exception as e:
        logger.error("v14预测失败 [%s]: %s", symbol, e)
        return None


def is_available() -> bool:
    """检查v14模型是否可用。"""
    return _MODEL_PATH.exists()
