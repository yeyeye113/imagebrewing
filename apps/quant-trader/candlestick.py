"""K线形态识别模块 — 自动识别经典K线形态.

支持形态:
  1. 锤子线/倒锤子线 (Hammer/Inverted Hammer)
  2. 吞没形态 (Engulfing)
  3. 启明星/黄昏星 (Morning Star/Evening Star)
  4. 十字星 (Doji)
  5. 三只乌鸦/三白兵 (Three Black Crows/Three White Soldiers)
  6. 乌云盖顶/刺透形态 (Dark Cloud Cover/Piercing Line)
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .log import get_logger

logger = get_logger("candlestick")


@dataclass
class CandlePattern:
    """K线形态."""
    name: str               # 形态名称
    direction: int          # +1 看多, -1 看空, 0 中性
    strength: float         # 强度 (0-1)
    description: str        # 描述


def _body_size(open_price: float, close_price: float) -> float:
    """计算实体大小."""
    return abs(close_price - open_price)


def _upper_shadow(open_price: float, close_price: float, high: float) -> float:
    """计算上影线长度."""
    return high - max(open_price, close_price)


def _lower_shadow(open_price: float, close_price: float, low: float) -> float:
    """计算下影线长度."""
    return min(open_price, close_price) - low


def _is_bullish(open_price: float, close_price: float) -> bool:
    """判断是否阳线."""
    return close_price > open_price


def _is_bearish(open_price: float, close_price: float) -> bool:
    """判断是否阴线."""
    return close_price < open_price


def detect_hammer(open_price: float, close_price: float, high: float, low: float) -> CandlePattern | None:
    """识别锤子线/倒锤子线.

    锤子线: 下影线长，实体小，上影线短或无
    倒锤子线: 上影线长，实体小，下影线短或无
    """
    body = _body_size(open_price, close_price)
    upper = _upper_shadow(open_price, close_price, high)
    lower = _lower_shadow(open_price, close_price, low)
    total_range = high - low

    if total_range == 0:
        return None

    # 锤子线: 下影线 >= 2倍实体，上影线 <= 实体的 30%
    if lower >= body * 2 and upper <= body * 0.3:
        return CandlePattern(
            name="锤子线",
            direction=1,
            strength=0.7,
            description="下影线长，看多信号",
        )

    # 倒锤子线: 上影线 >= 2倍实体，下影线 <= 实体的 30%
    if upper >= body * 2 and lower <= body * 0.3:
        return CandlePattern(
            name="倒锤子线",
            direction=1,
            strength=0.6,
            description="上影线长，潜在反转",
        )

    return None


def detect_engulfing(
    open1: float, close1: float,
    open2: float, close2: float,
) -> CandlePattern | None:
    """识别吞没形态.

    看多吞没: 第二根阳线完全吞没第一根阴线
    看空吞没: 第二根阴线完全吞没第一根阳线
    """
    # 看多吞没
    if (_is_bearish(open1, close1) and _is_bullish(open2, close2) and
        open2 <= close1 and close2 >= open1):
        return CandlePattern(
            name="看多吞没",
            direction=1,
            strength=0.8,
            description="阳线吞没阴线，强烈看多",
        )

    # 看空吞没
    if (_is_bullish(open1, close1) and _is_bearish(open2, close2) and
        open2 >= close1 and close2 <= open1):
        return CandlePattern(
            name="看空吞没",
            direction=-1,
            strength=0.8,
            description="阴线吞没阳线，强烈看空",
        )

    return None


def detect_morning_evening_star(
    open1: float, close1: float, high1: float, low1: float,
    open2: float, close2: float, high2: float, low2: float,
    open3: float, close3: float, high3: float, low3: float,
) -> CandlePattern | None:
    """识别启明星/黄昏星.

    启明星: 第一根阴线 + 第二根小实体 + 第三根阳线
    黄昏星: 第一根阳线 + 第二根小实体 + 第三根阴线
    """
    body1 = _body_size(open1, close1)
    body2 = _body_size(open2, close2)
    body3 = _body_size(open3, close3)

    # 启明星
    if (_is_bearish(open1, close1) and
        body2 < body1 * 0.3 and body2 < body3 * 0.3 and
        _is_bullish(open3, close3) and
        close3 > (open1 + close1) / 2):
        return CandlePattern(
            name="启明星",
            direction=1,
            strength=0.85,
            description="三根K线反转形态，强烈看多",
        )

    # 黄昏星
    if (_is_bullish(open1, close1) and
        body2 < body1 * 0.3 and body2 < body3 * 0.3 and
        _is_bearish(open3, close3) and
        close3 < (open1 + close1) / 2):
        return CandlePattern(
            name="黄昏星",
            direction=-1,
            strength=0.85,
            description="三根K线反转形态，强烈看空",
        )

    return None


def detect_doji(open_price: float, close_price: float, high: float, low: float) -> CandlePattern | None:
    """识别十字星.

    十字星: 实体极小，上下影线相近
    """
    body = _body_size(open_price, close_price)
    total_range = high - low

    if total_range == 0:
        return None

    # 十字星: 实体 <= 总范围的 10%
    if body <= total_range * 0.1:
        return CandlePattern(
            name="十字星",
            direction=0,
            strength=0.5,
            description="多空平衡，等待方向确认",
        )

    return None


def detect_three_soldiers_crows(
    opens: list[float], closes: list[float],
) -> CandlePattern | None:
    """识别三白兵/三只乌鸦.

    三白兵: 连续三根阳线，每根收盘价高于前一根
    三只乌鸦: 连续三根阴线，每根收盘价低于前一根
    """
    if len(opens) < 3 or len(closes) < 3:
        return None

    # 三白兵
    if (_is_bullish(opens[-3], closes[-3]) and
        _is_bullish(opens[-2], closes[-2]) and
        _is_bullish(opens[-1], closes[-1]) and
        closes[-2] > closes[-3] and closes[-1] > closes[-2]):
        return CandlePattern(
            name="三白兵",
            direction=1,
            strength=0.8,
            description="连续三根阳线，强烈看多",
        )

    # 三只乌鸦
    if (_is_bearish(opens[-3], closes[-3]) and
        _is_bearish(opens[-2], closes[-2]) and
        _is_bearish(opens[-1], closes[-1]) and
        closes[-2] < closes[-3] and closes[-1] < closes[-2]):
        return CandlePattern(
            name="三只乌鸦",
            direction=-1,
            strength=0.8,
            description="连续三根阴线，强烈看空",
        )

    return None


def detect_dark_cloud_piercing(
    open1: float, close1: float, high1: float,
    open2: float, close2: float, high2: float,
) -> CandlePattern | None:
    """识别乌云盖顶/刺透形态.

    乌云盖顶: 第一根阳线 + 第二根阴线开盘高于前高，收盘低于前实体中点
    刺透形态: 第一根阴线 + 第二根阳线开盘低于前低，收盘高于前实体中点
    """
    mid1 = (open1 + close1) / 2

    # 乌云盖顶
    if (_is_bullish(open1, close1) and _is_bearish(open2, close2) and
        open2 > high1 and close2 < mid1):
        return CandlePattern(
            name="乌云盖顶",
            direction=-1,
            strength=0.75,
            description="看空反转形态",
        )

    # 刺透形态
    if (_is_bearish(open1, close1) and _is_bullish(open2, close2) and
        open2 < close1 and close2 > mid1):
        return CandlePattern(
            name="刺透形态",
            direction=1,
            strength=0.75,
            description="看多反转形态",
        )

    return None


def analyze_candle_patterns(prices: pd.DataFrame) -> list[CandlePattern]:
    """分析K线形态.

    Args:
        prices: OHLCV 数据

    Returns:
        list[CandlePattern]: 识别到的形态列表
    """
    if prices is None or len(prices) < 5:
        return []

    patterns = []

    # 获取最近 5 根 K 线
    recent = prices.iloc[-5:]

    opens = recent['open'].values
    closes = recent['close'].values
    highs = recent['high'].values
    lows = recent['low'].values

    # 1. 锤子线/倒锤子线
    hammer = detect_hammer(opens[-1], closes[-1], highs[-1], lows[-1])
    if hammer:
        patterns.append(hammer)

    # 2. 吞没形态
    engulfing = detect_engulfing(
        opens[-2], closes[-2],
        opens[-1], closes[-1],
    )
    if engulfing:
        patterns.append(engulfing)

    # 3. 启明星/黄昏星
    star = detect_morning_evening_star(
        opens[-3], closes[-3], highs[-3], lows[-3],
        opens[-2], closes[-2], highs[-2], lows[-2],
        opens[-1], closes[-1], highs[-1], lows[-1],
    )
    if star:
        patterns.append(star)

    # 4. 十字星
    doji = detect_doji(opens[-1], closes[-1], highs[-1], lows[-1])
    if doji:
        patterns.append(doji)

    # 5. 三白兵/三只乌鸦
    soldiers = detect_three_soldiers_crows(opens[-3:], closes[-3:])
    if soldiers:
        patterns.append(soldiers)

    # 6. 乌云盖顶/刺透形态
    dark_cloud = detect_dark_cloud_piercing(
        opens[-2], closes[-2], highs[-2],
        opens[-1], closes[-1], highs[-1],
    )
    if dark_cloud:
        patterns.append(dark_cloud)

    return patterns


def get_candle_pattern_signal(prices: pd.DataFrame) -> dict:
    """获取K线形态信号.

    Returns:
        dict: {
            "signal": str,           # "BUY" | "SELL" | "HOLD"
            "confidence": float,     # 0-100 置信度
            "patterns": list[str],   # 识别到的形态
            "reason": str,           # 信号原因
        }
    """
    patterns = analyze_candle_patterns(prices)

    if not patterns:
        return {
            "signal": "HOLD",
            "confidence": 0,
            "patterns": [],
            "reason": "无明显形态",
        }

    # 统计方向
    bullish = sum(1 for p in patterns if p.direction == 1)
    bearish = sum(1 for p in patterns if p.direction == -1)

    # 计算平均强度
    avg_strength = sum(p.strength for p in patterns) / len(patterns)

    # 判断信号
    if bullish > bearish:
        signal = "BUY"
        confidence = avg_strength * 100
        reason = f"看多形态: {', '.join(p.name for p in patterns if p.direction == 1)}"
    elif bearish > bullish:
        signal = "SELL"
        confidence = avg_strength * 100
        reason = f"看空形态: {', '.join(p.name for p in patterns if p.direction == -1)}"
    else:
        signal = "HOLD"
        confidence = 50
        reason = f"多空平衡: {', '.join(p.name for p in patterns)}"

    return {
        "signal": signal,
        "confidence": round(confidence, 1),
        "patterns": [p.name for p in patterns],
        "reason": reason,
    }
