"""v530 高低点预测模块 — 接入daemon用。

读取 hl_method_weights.json，用 historical_vol + pivot + atr 三个方法
加权预测未来N天的最高价/最低价范围。

daemon用法:
    from quanttrader.predictor.hl_predict import predict_range
    pred = predict_range("AG", closes, highs, lows)
    # pred = {"high": 8500, "low": 8200, "range_pct": 3.6, "volatility": "high"}
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Prediction:
    predicted_high: float
    predicted_low: float
    current_price: float
    range_pct: float  # (high - low) / current * 100
    volatility: str   # "low" (<2%), "normal" (2-5%), "high" (>5%)

    @property
    def stop_distance_pct(self) -> float:
        """建议止损距离（基于预测低点）。"""
        return max(1.0, (self.current_price - self.predicted_low) / self.current_price * 100)

    @property
    def target_distance_pct(self) -> float:
        """建议止盈距离（基于预测高点）。"""
        return max(1.0, (self.predicted_high - self.current_price) / self.current_price * 100)

    @property
    def is_tradeable(self) -> bool:
        """波动是否足够大，值得交易。"""
        return self.range_pct >= 1.5  # 至少1.5%波动才值得做


def predict_range(
    symbol: str,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    horizon: int = 2,
) -> Prediction | None:
    """预测未来 N 天的高低点范围（统一委托 HighLowPredictor 实现）。

    Args:
        symbol: 品种代码 (如 "AG", "M", "BU")
        closes/highs/lows: 价格数组
        horizon: 预测天数 (默认2天)

    Returns:
        Prediction；数据不足(<30 根)时返回 None。

    历史上本函数与 analysis.highlow_predictor.HighLowPredictor 是两套重复实现，
    公式(是否 ×√horizon)、默认权重均不一致；且本函数在缺少 hl_method_weights.json
    或品种未配置时会静默返回 None、令 daemon 高低点预测失效。现统一委托类实现：
    单一事实来源，无权重文件时回退默认参数仍可给出预测。
    """
    if closes is None or len(closes) < 30:
        return None

    import pandas as pd
    from quanttrader.analysis.highlow_predictor import HighLowPredictor

    df = pd.DataFrame({
        "close": np.asarray(closes, dtype=float),
        "high": np.asarray(highs, dtype=float),
        "low": np.asarray(lows, dtype=float),
    })
    hp = HighLowPredictor().predict(df, symbol=symbol, horizon=horizon)
    current = hp.current_price
    range_pct = (hp.predicted_high - hp.predicted_low) / current * 100 if current > 0 else 0.0

    if range_pct < 2.0:
        vol_label = "low"
    elif range_pct < 5.0:
        vol_label = "normal"
    else:
        vol_label = "high"

    return Prediction(
        predicted_high=round(hp.predicted_high, 2),
        predicted_low=round(hp.predicted_low, 2),
        current_price=current,
        range_pct=round(range_pct, 2),
        volatility=vol_label,
    )
