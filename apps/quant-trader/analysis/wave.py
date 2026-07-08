"""波浪理论分析模块 (Elliott Wave Analysis).

核心原理:
  - 市场以 5-3 浪结构运行 (5浪推动 + 3浪调整)
  - 每浪有特定比例关系 (斐波那契)
  - 识别当前所处浪型 → 预测下一浪方向

简化实现:
  - 用 zigzag 算法识别波峰波谷
  - 计算浪间比例关系
  - 判断当前浪型 (推动浪/调整浪)
  - 输出方向预测 + 置信度
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class WavePoint:
    """波浪节点."""
    index: int
    price: float
    type: str  # "high" | "low"
    date: str = ""


@dataclass
class WaveAnalysis:
    """波浪分析结果."""
    # 当前浪型
    current_wave: str        # "impulse_1"~"impulse_5" | "corrective_a"~"corrective_c"
    wave_direction: int      # +1 看多, -1 看空, 0 中性
    confidence: float        # 0-1 置信度
    # 波浪结构
    swing_points: list       # 波峰波谷列表
    wave_count: int          # 已完成浪数
    # 斐波那契关系
    fib_ratio: float         # 当前浪与前浪的比例
    fib_target: float        # 下一浪的目标价位
    # 信号
    signal: str              # "BUY" | "SELL" | "HOLD"
    reason: str              # 预测理由


def _zigzag(prices: pd.Series, threshold: float = 0.05) -> list[WavePoint]:
    """Zigzag 算法识别波峰波谷.

    Args:
        prices: 收盘价序列
        threshold: 最小波动阈值 (5% = 0.05)

    Returns:
        波峰波谷列表
    """
    if len(prices) < 20:
        return []

    points = []
    direction = 0  # 0=未定, 1=上, -1=下
    last_extreme_idx = 0
    last_extreme_price = float(prices.iloc[0])

    for i in range(1, len(prices)):
        price = float(prices.iloc[i])
        change = price / last_extreme_price - 1

        if direction == 0:
            # 初始化方向
            if change > threshold:
                direction = 1
                points.append(WavePoint(last_extreme_idx, last_extreme_price, "low"))
                last_extreme_idx = i
                last_extreme_price = price
            elif change < -threshold:
                direction = -1
                points.append(WavePoint(last_extreme_idx, last_extreme_price, "high"))
                last_extreme_idx = i
                last_extreme_price = price
        elif direction == 1:
            # 上升趋势
            if price > last_extreme_price:
                last_extreme_idx = i
                last_extreme_price = price
            elif price < last_extreme_price * (1 - threshold):
                # 转折向下
                points.append(WavePoint(last_extreme_idx, last_extreme_price, "high"))
                direction = -1
                last_extreme_idx = i
                last_extreme_price = price
        else:
            # 下降趋势
            if price < last_extreme_price:
                last_extreme_idx = i
                last_extreme_price = price
            elif price > last_extreme_price * (1 + threshold):
                # 转折向上
                points.append(WavePoint(last_extreme_idx, last_extreme_price, "low"))
                direction = 1
                last_extreme_idx = i
                last_extreme_price = price

    # 添加最后一个点
    if points:
        last_price = float(prices.iloc[-1])
        if points[-1].type == "low" and last_price > points[-1].price:
            points.append(WavePoint(len(prices) - 1, last_price, "high"))
        elif points[-1].type == "high" and last_price < points[-1].price:
            points.append(WavePoint(len(prices) - 1, last_price, "low"))

    return points


def _identify_wave_structure(points: list[WavePoint]) -> tuple[str, int]:
    """识别波浪结构.

    Returns:
        (当前浪型, 已完成浪数)
    """
    if len(points) < 3:
        return "unknown", 0

    # 计算每个浪的方向和幅度
    waves = []
    for i in range(1, len(points)):
        prev = points[i - 1]
        curr = points[i]
        direction = 1 if curr.price > prev.price else -1
        amplitude = abs(curr.price / prev.price - 1)
        waves.append({
            "direction": direction,
            "amplitude": amplitude,
            "start": prev,
            "end": curr,
        })

    if len(waves) < 2:
        return "unknown", len(waves)

    # 判断推动浪 vs 调整浪
    # 推动浪: 3个同向浪 (1, 3, 5) + 2个反向浪 (2, 4)
    # 调整浪: 3个浪 (A, B, C)

    # 简化判断: 看最近几个浪的方向模式
    recent = waves[-3:] if len(waves) >= 3 else waves

    # 检查是否为推动浪 (1-2-3-4-5)
    if len(waves) >= 5:
        # 检查 1-3-5 同向, 2-4 反向
        wave1 = waves[0]
        wave2 = waves[1]
        wave3 = waves[2]
        wave4 = waves[3]
        wave5 = waves[4]

        if (wave1["direction"] == wave3["direction"] == wave5["direction"] and
            wave2["direction"] == wave4["direction"] and
            wave1["direction"] != wave2["direction"]):
            return "impulse_complete", 5

    # 检查是否为调整浪 (A-B-C)
    if len(waves) >= 3:
        wave_a = waves[-3]
        wave_b = waves[-2]
        wave_c = waves[-1]

        if (wave_a["direction"] == wave_c["direction"] and
            wave_b["direction"] != wave_a["direction"]):
            return "corrective_complete", 3

    # 判断当前所处位置
    if len(waves) >= 2:
        last_wave = waves[-1]
        prev_wave = waves[-2]

        if last_wave["direction"] == prev_wave["direction"]:
            # 同向: 可能是推动浪的 3 或 5
            if len(waves) % 2 == 1:
                return "impulse_3", len(waves)
            else:
                return "impulse_5", len(waves)
        else:
            # 反向: 可能是调整浪的 B 或推动浪的 2/4
            if len(waves) % 2 == 0:
                return "corrective_b", len(waves)
            else:
                return "impulse_2", len(waves)

    return "unknown", len(waves)


def _fibonacci_analysis(points: list[WavePoint]) -> tuple[float, float]:
    """斐波那契比例分析.

    Returns:
        (当前浪与前浪比例, 下一浪目标价位)
    """
    if len(points) < 3:
        return 1.0, 0.0

    # 最近两浪
    wave1_start = points[-3].price
    wave1_end = points[-2].price
    wave2_start = points[-2].price
    wave2_end = points[-1].price

    wave1_amp = abs(wave1_end - wave1_start)
    wave2_amp = abs(wave2_end - wave2_start)

    # 当前浪与前浪比例
    ratio = wave2_amp / wave1_amp if wave1_amp > 0 else 1.0

    # 下一浪目标 (基于斐波那契比例)
    # 常见比例: 0.382, 0.5, 0.618, 1.0, 1.618
    if wave2_end > wave2_start:
        # 当前上升浪, 下一浪可能是回调
        target = wave2_end - wave2_amp * 0.618
    else:
        # 当前下降浪, 下一浪可能是反弹
        target = wave2_end + wave2_amp * 0.618

    return ratio, target


def analyze_wave(prices: pd.DataFrame, threshold: float = 0.05) -> WaveAnalysis:
    """波浪理论分析主函数.

    Args:
        prices: OHLCV 数据
        threshold: zigzag 阈值 (5% = 0.05, 提高阈值减少噪声)

    Returns:
        WaveAnalysis 分析结果
    """
    close = prices["close"]

    # 1. 识别波峰波谷 (提高阈值到5%减少噪声)
    points = _zigzag(close, threshold)

    if len(points) < 5:  # 需要至少5个点才能判断浪型
        return WaveAnalysis(
            current_wave="unknown",
            wave_direction=0,
            confidence=0.3,
            swing_points=points,
            wave_count=0,
            fib_ratio=1.0,
            fib_target=0.0,
            signal="HOLD",
            reason="波浪数据不足",
        )

    # 2. 识别波浪结构
    wave_type, wave_count = _identify_wave_structure(points)

    # 3. 斐波那契分析
    fib_ratio, fib_target = _fibonacci_analysis(points)

    # 4. 判断方向和置信度
    current_price = float(close.iloc[-1])
    last_point = points[-1]

    # 根据浪型判断方向 (更严格的条件)
    if wave_type == "impulse_complete":
        # 推动浪完成 → 可能开始调整
        direction = -1
        confidence = 0.65
        signal = "SELL"
        reason = f"推动浪完成, 可能开始调整"
    elif wave_type == "corrective_complete":
        # 调整浪完成 → 可能开始推动浪
        direction = 1
        confidence = 0.65
        signal = "BUY"
        reason = f"调整浪完成, 可能开始上升"
    elif wave_type.startswith("impulse"):
        if last_point.type == "low" and wave_count >= 4:
            # 推动浪的低点, 且已有4浪以上 → 看多
            direction = 1
            confidence = 0.6
            signal = "BUY"
            reason = f"推动浪低点 ({wave_type}, {wave_count}浪)"
        elif last_point.type == "high" and wave_count >= 3:
            # 推动浪的高点 → 看空
            direction = -1
            confidence = 0.55
            signal = "SELL"
            reason = f"推动浪高点 ({wave_type}, {wave_count}浪)"
        else:
            direction = 0
            confidence = 0.4
            signal = "HOLD"
            reason = f"推动浪中 ({wave_type}, {wave_count}浪)"
    elif wave_type.startswith("corrective"):
        if last_point.type == "low" and wave_count >= 3:
            # 调整浪低点 → 看多
            direction = 1
            confidence = 0.6
            signal = "BUY"
            reason = f"调整浪低点 ({wave_type}, {wave_count}浪)"
        elif last_point.type == "high" and wave_count >= 2:
            # 调整浪高点 → 看空
            direction = -1
            confidence = 0.55
            signal = "SELL"
            reason = f"调整浪高点 ({wave_type}, {wave_count}浪)"
        else:
            direction = 0
            confidence = 0.4
            signal = "HOLD"
            reason = f"调整浪中 ({wave_type}, {wave_count}浪)"
    else:
        direction = 0
        confidence = 0.35
        signal = "HOLD"
        reason = f"浪型不明 ({wave_type})"

    # 5. 斐波那契比例修正
    if 0.5 < fib_ratio < 0.7:
        # 黄金比例区间, 信号更强
        confidence *= 1.1
    elif fib_ratio > 1.618:
        # 扩展浪, 可能反转
        confidence *= 0.9

    confidence = min(1.0, max(0.0, confidence))

    return WaveAnalysis(
        current_wave=wave_type,
        wave_direction=direction,
        confidence=confidence,
        swing_points=points,
        wave_count=wave_count,
        fib_ratio=round(fib_ratio, 3),
        fib_target=round(fib_target, 2),
        signal=signal,
        reason=reason,
    )


def wave_summary(prices: pd.DataFrame) -> dict:
    """波浪分析摘要 (用于集成到预测引擎)."""
    analysis = analyze_wave(prices)

    return {
        "wave_type": analysis.current_wave,
        "direction": analysis.wave_direction,
        "confidence": analysis.confidence,
        "signal": analysis.signal,
        "reason": analysis.reason,
        "fib_ratio": analysis.fib_ratio,
        "fib_target": analysis.fib_target,
        "swing_count": len(analysis.swing_points),
    }
