"""模块5: MarketRegimeDetector — 市场状态检测适配器。

只读展示: 趋势/震荡/高波动/低波动/异常行情。
不覆盖原策略信号，仅作为风险提示。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def analyze(prices: pd.DataFrame, symbol: str = "", **kwargs) -> dict:
    """检测当前市场状态，返回只读展示数据。

    Args:
        prices: OHLCV DataFrame (需含 close/high/low 列)
        symbol: 品种代码（仅用于标注）

    Returns:
        dict: 市场状态展示数据，strategy_impact 始终为 "none"
    """
    if prices is None or len(prices) < 20:
        return _empty(symbol, "数据不足")

    closes = prices["close"].astype(float)
    highs = prices["high"].astype(float) if "high" in prices.columns else closes
    lows = prices["low"].astype(float) if "low" in prices.columns else closes

    adx = _compute_adx(closes, highs, lows, period=14)
    vol = _compute_volatility(closes, period=20)
    trend_dir = _compute_trend_direction(closes)
    low_vol_threshold = 0.8  # 年化波动率 < 0.8% 视为低波动

    # 状态判定逻辑
    if vol > 3.0:
        regime = "volatile"
        risk_hint = "高波动行情，建议缩小仓位或观望"
        confidence = min(1.0, vol / 5.0)
    elif adx > 25:
        regime = "trending"
        direction_text = "多头" if trend_dir > 0 else "空头" if trend_dir < 0 else "方向不明"
        risk_hint = f"趋势市 ({direction_text})，可顺势跟踪"
        confidence = min(1.0, adx / 40.0)
    elif adx < 15 and vol < low_vol_threshold:
        regime = "low_volatility"
        risk_hint = "低波动横盘，趋势策略可能频繁止损"
        confidence = min(1.0, (15 - adx) / 10.0)
    elif adx < 20:
        regime = "ranging"
        risk_hint = "震荡市，适合均值回归策略"
        confidence = min(1.0, (20 - adx) / 15.0)
    else:
        # ADX 20-25 过渡区
        if trend_dir != 0:
            regime = "trending"
            confidence = 0.5
            risk_hint = "过渡区域，趋势强度中等"
        else:
            regime = "ranging"
            confidence = 0.4
            risk_hint = "过渡区域，方向不明"

    # 异常行情检测: 单日振幅超过 4%
    if len(prices) > 0:
        last_range = float((highs.iloc[-1] - lows.iloc[-1]) / (closes.iloc[-1] or 1) * 100)
        if last_range > 4.0:
            regime = "anomaly"
            risk_hint = f"异常行情！单日振幅 {last_range:.1f}%，建议暂停交易"
            confidence = min(1.0, last_range / 6.0)
    else:
        last_range = 0.0

    # 策略影响: 始终为 none（只读展示）
    return {
        "symbol": symbol,
        "regime": regime,
        "regime_label": _regime_label(regime),
        "adx": round(adx, 2),
        "volatility": round(vol, 2),
        "trend_direction": trend_dir,
        "trend_label": {1: "多头", -1: "空头", 0: "中性"}.get(trend_dir, "未知"),
        "confidence": round(confidence, 3),
        "daily_range_pct": round(last_range, 2),
        "risk_hint": risk_hint,
        "strategy_impact": "none",  # 铁律: 只读，不覆盖策略
    }


def _regime_label(regime: str) -> str:
    labels = {
        "trending": "趋势市",
        "ranging": "震荡市",
        "volatile": "高波动",
        "low_volatility": "低波动",
        "anomaly": "异常行情",
        "unknown": "未知",
    }
    return labels.get(regime, regime)


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "regime": "unknown",
        "regime_label": "未知",
        "adx": 0,
        "volatility": 0,
        "trend_direction": 0,
        "trend_label": "未知",
        "confidence": 0,
        "daily_range_pct": 0,
        "risk_hint": reason,
        "strategy_impact": "none",
    }


def _compute_adx(closes: pd.Series, highs: pd.Series, lows: pd.Series, period: int = 14) -> float:
    """计算 ADX (Average Directional Index)。"""
    if len(closes) < period * 2 + 1:
        return 0.0

    high_diff = highs.diff()
    low_diff = -lows.diff()

    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)

    tr1 = highs - lows
    tr2 = (highs - closes.shift(1)).abs()
    tr3 = (lows - closes.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.ewm(alpha=1 / period, min_periods=period).mean()

    return float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0


def _compute_volatility(closes: pd.Series, period: int = 20) -> float:
    """计算年化波动率 (百分比)。"""
    if len(closes) < period + 1:
        return 0.0
    returns = closes.pct_change().dropna().tail(period)
    return float(returns.std() * np.sqrt(252) * 100)


def _compute_trend_direction(closes: pd.Series) -> int:
    """判断趋势方向: 1=多头, -1=空头, 0=中性。"""
    if len(closes) < 60:
        return 0
    sma5 = float(closes.tail(5).mean())
    sma20 = float(closes.tail(20).mean())
    sma60 = float(closes.tail(60).mean())

    if sma5 > sma20 > sma60:
        return 1
    elif sma5 < sma20 < sma60:
        return -1
    return 0
