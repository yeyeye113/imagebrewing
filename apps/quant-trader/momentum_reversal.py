"""动量反转策略 — 根据市场状态切换动量和反转策略.

核心原理:
  1. 趋势市场: 使用动量策略 (追涨杀跌)
  2. 震荡市场: 使用反转策略 (高抛低吸)
  3. 自动识别市场状态
  4. 动态切换策略
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .analysis.indicators import calc_adx, calc_ma_alignment, calc_macd, calc_rsi
from .log import get_logger

logger = get_logger("momentum_reversal")


@dataclass
class MomentumReversalSignal:
    """动量反转策略信号."""
    strategy: str           # "momentum" | "reversal" | "neutral"
    direction: int          # +1 看多, -1 看空, 0 中性
    confidence: float       # 0-100 置信度
    reason: str             # 信号原因
    market_regime: str      # "trending" | "ranging" | "volatile"


def detect_market_regime(prices: pd.DataFrame) -> str:
    """检测市场状态.

    Args:
        prices: OHLCV 数据

    Returns:
        str: "trending" | "ranging" | "volatile"
    """
    if prices is None or len(prices) < 60:
        return "unknown"

    close = prices['close']

    # 1. ADX 趋势强度
    adx = calc_adx(prices)
    adx_val = adx['adx']

    # 2. 波动率
    rets = close.pct_change().dropna()
    vol_20 = float(rets.iloc[-20:].std()) if len(rets) >= 20 else 0

    # 3. 价格范围
    high_20 = float(close.iloc[-20:].max())
    low_20 = float(close.iloc[-20:].min())
    price_range = (high_20 - low_20) / low_20 if low_20 > 0 else 0

    # 判断市场状态
    if adx_val >= 25 and price_range > 0.1:
        return "trending"
    elif vol_20 > 0.03 or price_range > 0.15:
        return "volatile"
    else:
        return "ranging"


def momentum_strategy(prices: pd.DataFrame) -> MomentumReversalSignal:
    """动量策略: 追涨杀跌.

    适用场景: 趋势市场
    """
    if prices is None or len(prices) < 60:
        return MomentumReversalSignal(
            strategy="momentum",
            direction=0,
            confidence=0,
            reason="数据不足",
            market_regime="unknown",
        )

    close = prices['close']

    # 计算动量指标
    ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0
    ret_20d = float(close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0

    # 均线排列
    ma = calc_ma_alignment(close)

    # MACD
    macd = calc_macd(close)

    # 评分
    score = 0
    reasons = []

    # 短期动量
    if ret_5d > 0.03:
        score += 2
        reasons.append(f"5日涨{ret_5d*100:.1f}%")
    elif ret_5d < -0.03:
        score -= 2
        reasons.append(f"5日跌{ret_5d*100:.1f}%")

    # 中期动量
    if ret_20d > 0.1:
        score += 3
        reasons.append(f"20日涨{ret_20d*100:.1f}%")
    elif ret_20d < -0.1:
        score -= 3
        reasons.append(f"20日跌{ret_20d*100:.1f}%")

    # 均线排列
    if ma['alignment'] == 'bullish':
        score += 2
        reasons.append("均线多头排列")
    elif ma['alignment'] == 'bearish':
        score -= 2
        reasons.append("均线空头排列")

    # MACD
    if macd['cross'] == 'golden':
        score += 2
        reasons.append("MACD金叉")
    elif macd['cross'] == 'death':
        score -= 2
        reasons.append("MACD死叉")

    # 判断方向
    if score >= 4:
        direction = 1
        confidence = min(90, 50 + score * 5)
    elif score <= -4:
        direction = -1
        confidence = min(90, 50 + abs(score) * 5)
    else:
        direction = 0
        confidence = 30

    return MomentumReversalSignal(
        strategy="momentum",
        direction=direction,
        confidence=confidence,
        reason=" | ".join(reasons) if reasons else "无明显动量",
        market_regime="trending",
    )


def reversal_strategy(prices: pd.DataFrame) -> MomentumReversalSignal:
    """反转策略: 高抛低吸.

    适用场景: 震荡市场
    """
    if prices is None or len(prices) < 30:
        return MomentumReversalSignal(
            strategy="reversal",
            direction=0,
            confidence=0,
            reason="数据不足",
            market_regime="unknown",
        )

    close = prices['close']

    # RSI
    rsi = calc_rsi(close)

    # 布林带
    ma20 = float(close.rolling(20).mean().iloc[-1])
    std20 = float(close.rolling(20).std().iloc[-1])
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    price = float(close.iloc[-1])

    # 评分
    score = 0
    reasons = []

    # RSI 超买超卖
    if rsi['zone'] == 'oversold':
        score += 3
        reasons.append(f"RSI超卖 {rsi['rsi']:.1f}")
    elif rsi['zone'] == 'overbought':
        score -= 3
        reasons.append(f"RSI超买 {rsi['rsi']:.1f}")

    # 布林带位置
    if price < bb_lower:
        score += 2
        reasons.append("价格跌破布林下轨")
    elif price > bb_upper:
        score -= 2
        reasons.append("价格突破布林上轨")

    # 价格偏离度
    deviation = (price - ma20) / ma20 if ma20 > 0 else 0
    if deviation < -0.05:
        score += 2
        reasons.append(f"价格低于MA20 {deviation*100:.1f}%")
    elif deviation > 0.05:
        score -= 2
        reasons.append(f"价格高于MA20 {deviation*100:.1f}%")

    # 判断方向
    if score >= 4:
        direction = 1
        confidence = min(90, 50 + score * 5)
    elif score <= -4:
        direction = -1
        confidence = min(90, 50 + abs(score) * 5)
    else:
        direction = 0
        confidence = 30

    return MomentumReversalSignal(
        strategy="reversal",
        direction=direction,
        confidence=confidence,
        reason=" | ".join(reasons) if reasons else "无明显反转信号",
        market_regime="ranging",
    )


def momentum_reversal_strategy(prices: pd.DataFrame) -> MomentumReversalSignal:
    """动量反转策略: 自动切换.

    Args:
        prices: OHLCV 数据

    Returns:
        MomentumReversalSignal: 策略信号
    """
    # 检测市场状态
    regime = detect_market_regime(prices)

    # 根据市场状态选择策略
    if regime == "trending":
        signal = momentum_strategy(prices)
    elif regime == "ranging":
        signal = reversal_strategy(prices)
    elif regime == "volatile":
        # 高波动时使用反转策略，但降低置信度
        signal = reversal_strategy(prices)
        signal.confidence *= 0.8
    else:
        # 默认使用动量策略
        signal = momentum_strategy(prices)

    signal.market_regime = regime

    return signal


def get_momentum_reversal_signal(prices: pd.DataFrame) -> dict:
    """获取动量反转策略信号.

    Returns:
        dict: {
            "signal": str,           # "BUY" | "SELL" | "HOLD"
            "confidence": float,     # 0-100 置信度
            "strategy": str,         # "momentum" | "reversal"
            "market_regime": str,    # "trending" | "ranging" | "volatile"
            "reason": str,           # 信号原因
        }
    """
    signal = momentum_reversal_strategy(prices)

    return {
        "signal": "BUY" if signal.direction == 1 else ("SELL" if signal.direction == -1 else "HOLD"),
        "confidence": signal.confidence,
        "strategy": signal.strategy,
        "market_regime": signal.market_regime,
        "reason": signal.reason,
    }
