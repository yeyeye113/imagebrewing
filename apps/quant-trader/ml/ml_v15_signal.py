"""v15 ML信号适配器 — daemon可直接调用的方向预测模块。

加载训练好的LightGBM模型，对最新K线预测方向概率。
输出格式与LLM信号兼容，可无缝接入daemon决策流。
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)

_MODEL_PATH = Path("logs/ml_v15_GLOBAL.pkl")
_model_cache = None


def invalidate_model_cache() -> None:
    """重训后清除懒加载缓存。"""
    global _model_cache
    _model_cache = None


def _load_model():
    """懒加载模型（只读一次）。"""
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    if not _MODEL_PATH.exists():
        logger.warning("v15模型不存在: %s", _MODEL_PATH)
        return None
    try:
        import joblib
        _model_cache = joblib.load(_MODEL_PATH)
        logger.info("v15模型加载成功 (OOS=%.1f%%)", _model_cache.get("oos_accuracy", 0) * 100)
        return _model_cache
    except Exception as e:
        logger.error("v15模型加载失败: %s", e)
        return None


def predict(prices: pd.DataFrame, symbol: str = "") -> dict:
    """用v15模型预测当前方向。

    Args:
        prices: OHLCV DataFrame (需含 open/high/low/close/volume)
        symbol: 品种代码 (仅用于日志)

    Returns:
        dict: {
            signal: 1涨 / -1跌,
            signal_label: "涨" / "跌",
            confidence: float (0-1),
            probabilities: {long: float, short: float},
            model_version: str,
            oos_accuracy: float,
            source: "ml_v15",
        }
    """
    model_data = _load_model()
    if model_data is None:
        return _empty("v15模型未加载")

    try:
        # 特征构建 (复用v15训练时的特征)
        from scripts.ml_direction_v15 import compute_features
        features = compute_features(prices, horizon=5)
        if features is None or len(features) < 5:
            return _empty(f"{symbol}: 特征不足")

        last_row = features[model_data['feature_cols']].iloc[-1:]
        if last_row.isna().any(axis=1).iloc[0]:
            return _empty(f"{symbol}: 最新数据含NaN")

        model = model_data['model']
        pred_raw = int(model.predict(last_row.values)[0])
        proba = model.predict_proba(last_row.values)[0]

        # 二分类转三分类: 1=涨→1, 0=跌→-1
        pred = 1 if pred_raw == 1 else -1
        pred_label = "涨" if pred == 1 else "跌"
        confidence = round(float(max(proba)), 3)
        long_prob = round(float(proba[1] if len(proba) > 1 else proba[0]), 3)
        short_prob = round(float(1 - long_prob), 3)

        return {
            "signal": pred,
            "signal_label": pred_label,
            "confidence": confidence,
            "probabilities": {"long": long_prob, "short": short_prob},
            "model_version": model_data.get("version", "v15"),
            "oos_accuracy": model_data.get("oos_accuracy", 0),
            "source": "ml_v15",
        }
    except Exception as e:
        logger.error("v15预测失败 [%s]: %s", symbol, e)
        return _empty(f"{symbol}: 预测异常")


def _empty(reason: str) -> dict:
    return {
        "signal": 0,
        "signal_label": "平",
        "confidence": 0,
        "probabilities": {"long": 0, "short": 0},
        "model_version": "none",
        "oos_accuracy": 0,
        "source": "ml_v15",
        "reason": reason,
    }


def is_available() -> bool:
    """检查v15模型是否可用。"""
    return _MODEL_PATH.exists()
