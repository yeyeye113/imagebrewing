"""市场状态检测器 — 自动识别趋势/震荡/高波动，选择最优策略。

检测维度:
  1. ADX (趋势强度) > 25 = 趋势市
  2. 波动率 (ATR/价格) > 阈值 = 高波动
  3. 均线排列 (SMA5 > SMA20 > SMA60 = 多头排列)

策略映射:
  趋势市 → momentum (动量跟踪)
  震荡市 → rsi (均值回归)
  高波动 → bollinger (布林带)
  默认   → sma_cross (双均线)

用法:
    from quanttrader.market_regime import detect_regime, regime_to_strategy
    regime = detect_regime(prices)
    strategy_name, params = regime_to_strategy(regime)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class MarketRegime:
    """市场状态。"""

    name: str  # "trending" | "ranging" | "volatile" | "unknown"
    adx: float  # 0-100, 趋势强度
    volatility: float  # ATR/价格 百分比
    trend_direction: int  # 1=多头, -1=空头, 0=中性
    confidence: float  # 0-1, 检测置信度

    def to_text(self) -> str:
        labels = {
            "trending": "趋势市 ↑" if self.trend_direction > 0 else "趋势市 ↓",
            "ranging": "震荡市 ↔",
            "volatile": "高波动 ⚡",
            "unknown": "未知",
        }
        return f"{labels.get(self.name, self.name)} (ADX={self.adx:.0f} 波动={self.volatility:.1f}%)"


def _compute_adx(closes: pd.Series, highs: pd.Series, lows: pd.Series, period: int = 14) -> float:
    """计算 ADX (Average Directional Index)，衡量趋势强度。"""
    if len(closes) < period * 2 + 1:
        return 0.0

    # +DM / -DM
    high_diff = highs.diff()
    low_diff = -lows.diff()

    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)

    # True Range
    tr1 = highs - lows
    tr2 = (highs - closes.shift(1)).abs()
    tr3 = (lows - closes.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Smoothed averages (Wilder's smoothing)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr

    # DX → ADX
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.ewm(alpha=1 / period, min_periods=period).mean()

    return float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0


def _compute_volatility(closes: pd.Series, period: int = 20) -> float:
    """计算近期波动率 (ATR/价格 百分比)。"""
    if len(closes) < period + 1:
        return 0.0
    returns = closes.pct_change().dropna().tail(period)
    return float(returns.std() * np.sqrt(252) * 100)  # 年化波动率百分比


def _compute_trend_direction(closes: pd.Series) -> int:
    """判断趋势方向: 多头/空头/中性。"""
    if len(closes) < 60:
        return 0
    sma5 = float(closes.tail(5).mean())
    sma20 = float(closes.tail(20).mean())
    sma60 = float(closes.tail(60).mean())

    if sma5 > sma20 > sma60:
        return 1  # 多头排列
    elif sma5 < sma20 < sma60:
        return -1  # 空头排列
    return 0  # 中性


def detect_regime(prices: pd.DataFrame) -> MarketRegime:
    """检测市场状态。

    输入: DataFrame 含 close/high/low 列
    输出: MarketRegime (name, adx, volatility, trend_direction, confidence)
    """
    closes = prices["close"].astype(float)
    highs = prices["high"].astype(float) if "high" in prices.columns else closes
    lows = prices["low"].astype(float) if "low" in prices.columns else closes

    adx = _compute_adx(closes, highs, lows, period=14)
    vol = _compute_volatility(closes, period=20)
    trend_dir = _compute_trend_direction(closes)

    # 决策逻辑
    # 1) 高波动优先 (波动率 > 3% 年化)
    if vol > 3.0:
        name = "volatile"
        confidence = min(1.0, vol / 5.0)
    # 2) 趋势市 (ADX > 25)
    elif adx > 25:
        name = "trending"
        confidence = min(1.0, adx / 40.0)
    # 3) 震荡市 (ADX < 20)
    elif adx < 20:
        name = "ranging"
        confidence = min(1.0, (20 - adx) / 15.0)
    # 4) 过渡区
    else:
        # ADX 20-25，用趋势方向辅助
        if trend_dir != 0:
            name = "trending"
            confidence = 0.5
        else:
            name = "ranging"
            confidence = 0.4

    return MarketRegime(
        name=name,
        adx=adx,
        volatility=vol,
        trend_direction=trend_dir,
        confidence=confidence,
    )


def regime_to_strategy(regime: MarketRegime) -> tuple[str, dict]:
    """将市场状态映射到策略名+参数。

    返回: (strategy_name, params_dict)
    """
    if regime.name == "trending":
        if regime.trend_direction > 0:
            return "momentum", {"lookback": 20, "trend_filter": 60}
        else:
            return "momentum", {"lookback": 20, "trend_filter": 60}
    elif regime.name == "ranging":
        return "rsi", {"period": 14, "oversold": 30, "overbought": 70}
    elif regime.name == "volatile":
        return "bollinger", {"period": 20, "num_std": 2.0}
    else:
        return "sma_cross", {"fast": 20, "slow": 60}  # 默认
