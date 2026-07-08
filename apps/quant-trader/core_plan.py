"""核心预测计划系统 — 以高低点为最高预测单位.

核心逻辑:
  价格走势 = 高点和低点的交替序列
  预测目标 = 预测下一个高点/低点的位置和时间
  交易计划 = 从当前位置到预测目标的路径

时间收束:
  1. 识别当前所处阶段 (上升/下降/震荡)
  2. 计算到达目标所需时间
  3. 设定确认条件 (价格+时间)
  4. 生成执行计划
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from .log import get_logger

logger = get_logger("core_plan")


@dataclass
class PivotPoint:
    """高低点."""
    index: int
    price: float
    point_type: str      # "high" | "low"
    strength: float = 0
    bars_ago: int = 0
    date: str = ""


@dataclass
class PricePhase:
    """价格阶段."""
    phase_type: str      # "上升" | "下降" | "震荡"
    start_price: float
    current_price: float
    target_price: float
    progress: float      # 0-1 进度
    bars_elapsed: int
    bars_remaining: int  # 预计剩余K线数


@dataclass
class TradePlan:
    """交易计划."""
    # 核心预测
    current_price: float
    current_phase: str       # "上升中" | "下降中" | "震荡"
    # 目标
    target_type: str         # "高点" | "低点"
    target_price: float
    target_bars: int         # 预计到达时间
    # 交易
    direction: str           # "BUY" | "SELL" | "HOLD"
    # 以下有默认值
    target_date: str = ""
    entry_price: float = 0
    stop_loss: float = 0
    take_profit: float = 0
    confidence: float = 0
    confirm_conditions: list = field(default_factory=list)
    path: list = field(default_factory=list)
    risk_reward: float = 0


# ═══════════════════════════════════════════════════════════════════════
# 高低点识别
# ═══════════════════════════════════════════════════════════════════════

def find_pivots(prices: pd.DataFrame, left: int = 3, right: int = 3) -> list[PivotPoint]:
    """识别高低点."""
    high = prices['high'].values
    low = prices['low'].values
    n = len(high)
    pivots = []

    for i in range(left, n - right):
        # 高点
        is_high = all(high[i] > high[i-j] for j in range(1, left+1)) and \
                  all(high[i] > high[i+j] for j in range(1, right+1))
        if is_high:
            min_l = min(high[i-j] for j in range(1, left+1))
            min_r = min(high[i+j] for j in range(1, right+1))
            strength = (high[i] - min(min_l, min_r)) / high[i] * 100
            pivots.append(PivotPoint(
                index=i, price=float(high[i]), point_type="high",
                strength=min(1.0, strength), bars_ago=n-1-i,
            ))

        # 低点
        is_low = all(low[i] < low[i-j] for j in range(1, left+1)) and \
                 all(low[i] < low[i+j] for j in range(1, right+1))
        if is_low:
            max_l = max(low[i-j] for j in range(1, left+1))
            max_r = max(low[i+j] for j in range(1, right+1))
            strength = (max(max_l, max_r) - low[i]) / low[i] * 100
            pivots.append(PivotPoint(
                index=i, price=float(low[i]), point_type="low",
                strength=min(1.0, strength), bars_ago=n-1-i,
            ))

    pivots.sort(key=lambda p: p.index)
    return pivots


# ═══════════════════════════════════════════════════════════════════════
# 趋势判断
# ═══════════════════════════════════════════════════════════════════════

def get_trend(prices: pd.DataFrame) -> str:
    """判断趋势."""
    close = prices['close']
    n = len(close)
    if n < 60:
        return "sideways"

    price = float(close.iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])

    if price > ma20 > ma60:
        return "up"
    elif price < ma20 < ma60:
        return "down"
    return "sideways"


def get_pivot_trend(pivots: list[PivotPoint]) -> str:
    """用高低点判断趋势."""
    highs = [p for p in pivots if p.point_type == "high"][-3:]
    lows = [p for p in pivots if p.point_type == "low"][-3:]

    if len(highs) < 2 or len(lows) < 2:
        return "sideways"

    high_up = highs[-1].price > highs[-2].price
    low_up = lows[-1].price > lows[-2].price

    if high_up and low_up:
        return "up"
    elif not high_up and not low_up:
        return "down"
    return "sideways"


# ═══════════════════════════════════════════════════════════════════════
# 核心预测: 下一个目标
# ═══════════════════════════════════════════════════════════════════════

def predict_next_target(
    pivots: list[PivotPoint],
    current_price: float,
    trend: str,
    atr: float,
) -> tuple[float, str, int, float]:
    """预测下一个目标.

    Returns:
        (target_price, target_type, target_bars, confidence)
    """
    if len(pivots) < 4:
        return 0, "", 0, 0

    recent_highs = [p for p in pivots[-8:] if p.point_type == "high"]
    recent_lows = [p for p in pivots[-8:] if p.point_type == "low"]

    if not recent_highs or not recent_lows:
        return 0, "", 0, 0

    last_high = recent_highs[-1]
    last_low = recent_lows[-1]

    # 平均波动幅度
    avg_range = float(np.mean([
        abs(h.price - l.price)
        for h in recent_highs[-3:]
        for l in recent_lows[-3:]
        if abs(h.index - l.index) <= 30
    ])) if len(recent_highs) >= 2 and len(recent_lows) >= 2 else atr * 10

    # 当前位置判断
    mid = (last_high.price + last_low.price) / 2
    near_high = abs(current_price - last_high.price) < avg_range * 0.3
    near_low = abs(current_price - last_low.price) < avg_range * 0.3

    if trend == "up":
        if near_low:
            # 在低点附近 → 预测到新高
            target_price = last_high.price + avg_range * 0.2
            target_type = "high"
            target_bars = int((target_price - current_price) / atr) if atr > 0 else 10
            confidence = 0.7
        elif near_high:
            # 在高点附近 → 预测回调到支撑
            target_price = current_price - avg_range * 0.382
            target_type = "low"
            target_bars = int(avg_range * 0.382 / atr) if atr > 0 else 5
            confidence = 0.5
        else:
            # 中间位置 → 预测到高点
            target_price = last_high.price
            target_type = "high"
            target_bars = int((target_price - current_price) / atr) if atr > 0 else 5
            confidence = 0.6

    elif trend == "down":
        if near_high:
            # 在高点附近 → 预测到新低
            target_price = last_low.price - avg_range * 0.2
            target_type = "low"
            target_bars = int((current_price - target_price) / atr) if atr > 0 else 10
            confidence = 0.7
        elif near_low:
            # 在低点附近 → 预测反弹
            target_price = current_price + avg_range * 0.382
            target_type = "high"
            target_bars = int(avg_range * 0.382 / atr) if atr > 0 else 5
            confidence = 0.5
        else:
            target_price = last_low.price
            target_type = "low"
            target_bars = int((current_price - target_price) / atr) if atr > 0 else 5
            confidence = 0.6

    else:  # sideways
        if current_price > mid:
            target_price = last_low.price + avg_range * 0.1
            target_type = "low"
            confidence = 0.4
        else:
            target_price = last_high.price - avg_range * 0.1
            target_type = "high"
            confidence = 0.4
        target_bars = int(abs(target_price - current_price) / atr) if atr > 0 else 5

    # 限制范围
    max_move = atr * 20
    if abs(target_price - current_price) > max_move:
        target_price = current_price + max_move * (1 if target_price > current_price else -1)

    return round(target_price, 2), target_type, max(3, min(30, target_bars)), confidence


# ═══════════════════════════════════════════════════════════════════════
# 生成完整计划
# ═══════════════════════════════════════════════════════════════════════

def generate_plan(prices: pd.DataFrame, require_edge: bool = False) -> TradePlan | None:
    """生成完整交易计划.

    默认渐进融合：枢轴逻辑为主，edge 存在时加权提升置信度与方向一致性。
    require_edge=True 则退回严格模式（仅 edge 达标时输出）。
    """
    if prices is None or len(prices) < 60:
        return None

    from .direction_edge import MIN_EDGE_SCORE, edge_contradicts, find_best_edge_setup

    edge = find_best_edge_setup(prices)
    if require_edge and edge is None:
        return None

    close = prices['close']
    high = prices['high']
    low = prices['low']
    current_price = float(close.iloc[-1])

    # 1. 高低点
    pivots = find_pivots(prices, left=3, right=3)
    if len(pivots) < 4:
        return None

    # 2. 趋势
    ma_trend = get_trend(prices)
    pivot_trend = get_pivot_trend(pivots)

    # 综合趋势
    if ma_trend == pivot_trend:
        trend = ma_trend
    elif ma_trend == "up" or pivot_trend == "up":
        trend = "up"
    elif ma_trend == "down" or pivot_trend == "down":
        trend = "down"
    else:
        trend = "sideways"

    # 3. ATR
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])

    # 4. 预测目标
    target_price, target_type, target_bars, pivot_conf = predict_next_target(
        pivots, current_price, trend, atr
    )

    if target_price == 0:
        return None

    # 5. 方向与阶段 — 枢轴为主，edge 存在时融合加权
    if target_type == "high":
        current_phase = "上升中"
        direction = "BUY"
        stop_loss = current_price - atr * 2
        take_profit = target_price
        confidence = pivot_conf * 100
    else:
        current_phase = "下降中"
        direction = "SELL"
        stop_loss = current_price + atr * 2
        take_profit = target_price
        confidence = pivot_conf * 100

    plan_dir = 1 if direction == "BUY" else -1
    if edge is not None:
        if edge_contradicts(prices, plan_dir):
            return None
        if edge.direction == plan_dir:
            confidence = max(confidence, edge.score)
        elif edge.score >= 78 and pivot_conf < 0.6:
            # edge 更强时温和修正方向（仅低枢轴置信时）
            if edge.direction == 1:
                direction, current_phase = "BUY", "上升中"
                target_type = "high"
                target_price = max(target_price, current_price + atr * 2)
            else:
                direction, current_phase = "SELL", "下降中"
                target_type = "low"
                target_price = min(target_price, current_price - atr * 2)
            stop_loss = current_price - atr * 2 if direction == "BUY" else current_price + atr * 2
            take_profit = target_price
            confidence = edge.score

    # 震荡低置信且无 edge 背书 → 不输出（减少 ~48% 随机单）
    if edge is None and trend == "sideways" and pivot_conf < 0.55:
        return None
    if require_edge and confidence < MIN_EDGE_SCORE:
        return None

    # 6. 确认条件
    confirm_conditions: list[str] = []
    if edge is not None:
        confirm_conditions.append(f"Edge: {edge.name} ({edge.score:.0f}分)")
        confirm_conditions.extend(edge.reasons)
    if target_type == "high":
        confirm_conditions.extend([
            f"价格突破 {current_price + atr:.2f} (+1 ATR)",
            "成交量放大 > 1.3 倍",
            "RSI > 50 且上升",
            "MACD 柱状图为正",
        ])
    else:
        confirm_conditions.extend([
            f"价格跌破 {current_price - atr:.2f} (-1 ATR)",
            "成交量放大 > 1.3 倍",
            "RSI < 50 且下降",
            "MACD 柱状图为负",
        ])

    # 7. 路径
    path = []
    for p in pivots[-6:]:
        path.append({
            "index": p.index, "price": p.price, "type": p.point_type,
            "bars_ago": p.bars_ago, "predicted": False,
        })
    path.append({
        "index": len(prices) + target_bars, "price": target_price,
        "type": target_type, "bars_ago": -target_bars, "predicted": True,
    })

    # 8. 风险回报
    risk = abs(current_price - stop_loss)
    reward = abs(take_profit - current_price)
    risk_reward = reward / risk if risk > 0 else 0

    # 9. 预计日期
    last_date = prices.index[-1]
    if hasattr(last_date, 'date'):
        target_date = (last_date + timedelta(days=target_bars * 1.5)).strftime('%Y-%m-%d')
    else:
        target_date = f"+{target_bars} bars"

    return TradePlan(
        current_price=current_price,
        current_phase=current_phase,
        target_type=target_type,
        target_price=target_price,
        target_bars=target_bars,
        target_date=target_date,
        direction=direction,
        entry_price=current_price,
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        confidence=round(confidence, 1),
        confirm_conditions=confirm_conditions,
        path=path,
        risk_reward=round(risk_reward, 2),
    )


# ═══════════════════════════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════════════════════════

def format_plan(plan: TradePlan) -> str:
    """格式化计划."""
    if plan is None:
        return "无法生成计划"

    lines = [
        f"{'='*55}",
        f"核心预测计划",
        f"{'='*55}",
        f"",
        f"【当前状态】",
        f"  价格: {plan.current_price:.2f}",
        f"  阶段: {plan.current_phase}",
        f"",
        f"【预测目标】",
        f"  类型: {plan.target_type}",
        f"  价格: {plan.target_price:.2f}",
        f"  时间: {plan.target_bars} 根K线 (约 {plan.target_date})",
        f"",
        f"【交易计划】",
        f"  方向: {plan.direction}",
        f"  入场: {plan.entry_price:.2f}",
        f"  止损: {plan.stop_loss:.2f}",
        f"  止盈: {plan.take_profit:.2f}",
        f"  风险回报比: 1:{plan.risk_reward}",
        f"  置信度: {plan.confidence:.1f}%",
        f"",
        f"【确认条件】",
    ]

    for cond in plan.confirm_conditions:
        lines.append(f"  ✓ {cond}")

    lines.extend([
        f"",
        f"【计划线路径】",
    ])

    for p in plan.path:
        marker = "→" if p.get("predicted") else " "
        label = "预测" if p.get("predicted") else f"{p['bars_ago']}根前"
        lines.append(f"  {marker} {p['type']}: {p['price']:.2f} ({label})")

    lines.append(f"{'='*55}")
    return "\n".join(lines)
