"""A股高手策略整合模块.

整合 A 股市场中被验证有效的策略思路:
  1. 北向资金策略 - 跟踪聪明钱流向
  2. 机构持仓策略 - 跟踪主力动向
  3. 涨停板策略 - 打板/追板
  4. 龙头战法 - 板块龙头带动效应
  5. 量价关系策略 - A股特色量价分析
  6. 均线多头排列 - 经典趋势跟踪

这些策略经过 A 股市场长期验证, 适合中国市场特点。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ExpertSignal:
    """高手策略信号."""
    strategy: str       # 策略名称
    direction: int      # +1 看多, -1 看空, 0 中性
    strength: float     # 信号强度 0-1
    confidence: float   # 置信度 0-1
    signal: str         # "BUY" | "SELL" | "HOLD"
    reason: str         # 信号理由
    details: dict       # 详细数据


# ═══════════════════════════════════════════════════════════════════════
# 策略 1: 北向资金策略 (聪明钱跟踪)
# ═══════════════════════════════════════════════════════════════════════

def northbound_strategy(prices: pd.DataFrame) -> ExpertSignal:
    """北向资金策略 - 用成交量和价格关系模拟聪明钱流向.

    原理:
      - 北向资金(外资)被称为"聪明钱"
      - 放量上涨 = 外资流入
      - 放量下跌 = 外资流出
      - 缩量回调 = 洗盘, 外资未走

    注意: 真正的北向资金数据需要 akshare 的 stock_hsgt_north_net_flow_in
    这里用价格和成交量关系模拟。
    """
    if len(prices) < 20:
        return ExpertSignal("北向资金", 0, 0, 0.3, "HOLD", "数据不足", {})

    close = prices["close"]
    volume = prices["volume"]

    # 近5日 vs 近20日的量价关系
    ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1)
    vol_5 = float(volume.iloc[-5:].mean())
    vol_20 = float(volume.iloc[-20:].mean())
    vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 1.0

    # 近10日的资金流向模拟
    # 上涨日成交量 vs 下跌日成交量
    returns = close.pct_change().dropna().iloc[-10:]
    up_vol = float(volume.iloc[-10:][returns > 0].mean()) if (returns > 0).any() else 0
    down_vol = float(volume.iloc[-10:][returns < 0].mean()) if (returns < 0).any() else 0

    # 资金流入比
    flow_ratio = up_vol / down_vol if down_vol > 0 else 2.0

    direction = 0
    strength = 0.0
    signal = "HOLD"
    reason = ""

    if ret_5d > 0.02 and vol_ratio > 1.2 and flow_ratio > 1.5:
        # 放量上涨 + 资金流入 → 强烈看多
        direction = 1
        strength = min(flow_ratio / 3, 1.0)
        signal = "BUY"
        reason = f"资金净流入, 5日涨{ret_5d*100:.1f}%, 量比{vol_ratio:.1f}, 流入比{flow_ratio:.1f}"
    elif ret_5d < -0.02 and vol_ratio > 1.3:
        # 放量下跌 → 资金流出
        direction = -1
        strength = min(vol_ratio / 3, 1.0)
        signal = "SELL"
        reason = f"资金净流出, 5日跌{ret_5d*100:.1f}%, 量比{vol_ratio:.1f}"
    elif ret_5d < -0.01 and vol_ratio < 0.8:
        # 缩量回调 → 洗盘, 可能是买点
        direction = 1
        strength = 0.4
        signal = "BUY"
        reason = f"缩量回调, 可能是洗盘, 量比{vol_ratio:.1f}"
    else:
        reason = f"资金中性, 5日{ret_5d*100:+.1f}%, 量比{vol_ratio:.1f}"

    return ExpertSignal(
        strategy="北向资金",
        direction=direction,
        strength=strength,
        confidence=0.6 + strength * 0.2,
        signal=signal,
        reason=reason,
        details={"ret_5d": ret_5d, "vol_ratio": vol_ratio, "flow_ratio": flow_ratio},
    )


# ═══════════════════════════════════════════════════════════════════════
# 策略 2: 涨停板策略 (打板/追板)
# ═══════════════════════════════════════════════════════════════════════

def limit_up_strategy(prices: pd.DataFrame) -> ExpertSignal:
    """涨停板策略 - A股特色.

    原理:
      - 涨停后次日高开 → 连板可能
      - 涨停后缩量 → 惜售, 可能继续涨
      - 涨停后放量 → 换手, 需要观察
      - 跌停 → 极度看空
    """
    if len(prices) < 10:
        return ExpertSignal("涨停板", 0, 0, 0.3, "HOLD", "数据不足", {})

    close = prices["close"]
    high = prices["high"]
    low = prices["low"]

    # 近5日涨跌幅
    ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1)
    # 今日涨跌幅
    ret_1d = float(close.iloc[-1] / close.iloc[-2] - 1) if len(close) >= 2 else 0
    # 昨日涨跌幅
    ret_1d_prev = float(close.iloc[-2] / close.iloc[-3] - 1) if len(close) >= 3 else 0

    # 涨停判断 (A股涨跌停 10%, 创业板/科创板 20%)
    is_limit_up = ret_1d >= 0.095
    is_limit_up_prev = ret_1d_prev >= 0.095
    is_limit_down = ret_1d <= -0.095

    direction = 0
    strength = 0.0
    signal = "HOLD"
    reason = ""

    if is_limit_up:
        # 今日涨停
        if is_limit_up_prev:
            # 连板
            direction = 1
            strength = 0.9
            signal = "BUY"
            reason = f"连板涨停, 5日涨{ret_5d*100:.1f}%"
        else:
            # 首板
            direction = 1
            strength = 0.7
            signal = "BUY"
            reason = f"涨停, 5日涨{ret_5d*100:.1f}%"
    elif is_limit_down:
        # 跌停
        direction = -1
        strength = 0.9
        signal = "SELL"
        reason = f"跌停, 5日跌{ret_5d*100:.1f}%"
    elif is_limit_up_prev and ret_1d > 0.03:
        # 昨日涨停, 今日继续涨
        direction = 1
        strength = 0.6
        signal = "BUY"
        reason = f"昨日涨停, 今日续涨{ret_1d*100:.1f}%"
    elif is_limit_up_prev and ret_1d < -0.03:
        # 昨日涨停, 今日回落
        direction = -1
        strength = 0.5
        signal = "SELL"
        reason = f"昨日涨停, 今日回落{ret_1d*100:.1f}%"
    elif ret_5d > 0.15:
        # 5日涨超15%, 可能追高
        direction = -1
        strength = 0.4
        signal = "SELL"
        reason = f"5日涨{ret_5d*100:.1f}%, 追高风险"
    else:
        reason = f"无涨停信号, 5日{ret_5d*100:+.1f}%"

    return ExpertSignal(
        strategy="涨停板",
        direction=direction,
        strength=strength,
        confidence=0.5 + strength * 0.3,
        signal=signal,
        reason=reason,
        details={"ret_1d": ret_1d, "ret_5d": ret_5d, "limit_up": is_limit_up},
    )


# ═══════════════════════════════════════════════════════════════════════
# 策略 3: 龙头战法 (板块效应)
# ═══════════════════════════════════════════════════════════════════════

def leader_strategy(prices: pd.DataFrame) -> ExpertSignal:
    """龙头战法 - 板块龙头带动效应.

    原理:
      - 龙头股带动板块
      - 龙头涨停 → 板块其他股可能跟涨
      - 龙头见顶 → 板块可能回调
      - 判断是否为龙头: 近期涨幅领先

    注意: 真正的龙头判断需要板块内比较,
    这里用个股自身特征模拟。
    """
    if len(prices) < 20:
        return ExpertSignal("龙头战法", 0, 0, 0.3, "HOLD", "数据不足", {})

    close = prices["close"]
    volume = prices["volume"]

    # 近期涨幅
    ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1)
    ret_10d = float(close.iloc[-1] / close.iloc[-10] - 1)
    ret_20d = float(close.iloc[-1] / close.iloc[-20] - 1)

    # 成交量活跃度
    vol_5 = float(volume.iloc[-5:].mean())
    vol_20 = float(volume.iloc[-20:].mean())
    vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 1.0

    # 龙头特征:
    # 1. 近期涨幅大 (5日>10%, 10日>20%)
    # 2. 成交量放大 (量比>1.5)
    # 3. 连续上涨 (5日中4日上涨)

    returns_5d = close.pct_change().dropna().iloc[-5:]
    up_days = int((returns_5d > 0).sum())

    is_leader = (ret_5d > 0.10 and vol_ratio > 1.5 and up_days >= 3)
    is_exhausted = (ret_10d > 0.20 and ret_5d < 0.02)

    direction = 0
    strength = 0.0
    signal = "HOLD"
    reason = ""

    if is_leader:
        # 龙头特征明显
        direction = 1
        strength = 0.8
        signal = "BUY"
        reason = f"龙头特征: 5日涨{ret_5d*100:.1f}%, 量比{vol_ratio:.1f}, {up_days}/5上涨"
    elif is_exhausted:
        # 龙头见顶
        direction = -1
        strength = 0.6
        signal = "SELL"
        reason = f"龙头见顶: 10日涨{ret_10d*100:.1f}%, 近5日放缓"
    elif ret_5d > 0.05 and vol_ratio > 1.2:
        # 强势股
        direction = 1
        strength = 0.5
        signal = "BUY"
        reason = f"强势股: 5日涨{ret_5d*100:.1f}%, 量比{vol_ratio:.1f}"
    else:
        reason = f"非龙头, 5日{ret_5d*100:+.1f}%, 10日{ret_10d*100:+.1f}%"

    return ExpertSignal(
        strategy="龙头战法",
        direction=direction,
        strength=strength,
        confidence=0.5 + strength * 0.3,
        signal=signal,
        reason=reason,
        details={"ret_5d": ret_5d, "ret_10d": ret_10d, "vol_ratio": vol_ratio, "up_days": up_days},
    )


# ═══════════════════════════════════════════════════════════════════════
# 策略 4: 量价关系策略 (A股特色)
# ═══════════════════════════════════════════════════════════════════════

def volume_price_strategy(prices: pd.DataFrame) -> ExpertSignal:
    """A股特色量价关系策略.

    原理:
      - 量增价升 → 健康上涨
      - 量缩价升 → 动力不足
      - 量增价跌 → 主力出货
      - 量缩价跌 → 阴跌
      - 地量 → 可能见底
      - 天量 → 可能见顶
    """
    if len(prices) < 20:
        return ExpertSignal("量价关系", 0, 0, 0.3, "HOLD", "数据不足", {})

    close = prices["close"]
    volume = prices["volume"]

    # 近5日涨跌幅
    ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1)
    # 量比
    vol_5 = float(volume.iloc[-5:].mean())
    vol_20 = float(volume.iloc[-20:].mean())
    vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 1.0

    # 地量判断 (近20日最低量的1.2倍以内)
    vol_min_20 = float(volume.iloc[-20:].min())
    is_low_vol = vol_5 < vol_min_20 * 1.2

    # 天量判断 (近20日最高量的0.8倍以上)
    vol_max_20 = float(volume.iloc[-20:].max())
    is_high_vol = vol_5 > vol_max_20 * 0.8

    direction = 0
    strength = 0.0
    signal = "HOLD"
    reason = ""

    if ret_5d > 0.02 and vol_ratio > 1.3:
        # 量增价升 → 健康上涨
        direction = 1
        strength = 0.7
        signal = "BUY"
        reason = f"量增价升, 5日涨{ret_5d*100:.1f}%, 量比{vol_ratio:.1f}"
    elif ret_5d > 0.02 and vol_ratio < 0.8:
        # 量缩价升 → 动力不足
        direction = -1
        strength = 0.4
        signal = "SELL"
        reason = f"量缩价升, 动力不足, 量比{vol_ratio:.1f}"
    elif ret_5d < -0.02 and vol_ratio > 1.5:
        # 量增价跌 → 主力出货
        direction = -1
        strength = 0.8
        signal = "SELL"
        reason = f"量增价跌, 可能出货, 5日跌{ret_5d*100:.1f}%, 量比{vol_ratio:.1f}"
    elif ret_5d < -0.02 and vol_ratio < 0.7:
        # 量缩价跌 → 阴跌
        direction = -1
        strength = 0.5
        signal = "SELL"
        reason = f"量缩价跌, 阴跌, 量比{vol_ratio:.1f}"
    elif is_low_vol and ret_5d < -0.01:
        # 地量下跌 → 可能见底
        direction = 1
        strength = 0.6
        signal = "BUY"
        reason = f"地量下跌, 可能见底, 量比{vol_ratio:.1f}"
    elif is_high_vol and ret_5d > 0.05:
        # 天量上涨 → 可能见顶
        direction = -1
        strength = 0.5
        signal = "SELL"
        reason = f"天量上涨, 可能见顶, 量比{vol_ratio:.1f}"
    else:
        reason = f"量价中性, 5日{ret_5d*100:+.1f}%, 量比{vol_ratio:.1f}"

    return ExpertSignal(
        strategy="量价关系",
        direction=direction,
        strength=strength,
        confidence=0.5 + strength * 0.3,
        signal=signal,
        reason=reason,
        details={"ret_5d": ret_5d, "vol_ratio": vol_ratio, "low_vol": is_low_vol, "high_vol": is_high_vol},
    )


# ═══════════════════════════════════════════════════════════════════════
# 策略 5: 均线多头排列 (经典趋势)
# ═══════════════════════════════════════════════════════════════════════

def ma_alignment_strategy(prices: pd.DataFrame) -> ExpertSignal:
    """均线多头排列策略 - 经典趋势跟踪.

    原理:
      - MA5 > MA10 > MA20 > MA60 → 多头排列, 强势
      - MA5 < MA10 < MA20 < MA60 → 空头排列, 弱势
      - 均线粘合 → 变盘信号
      - 金叉/死叉 → 买卖信号
    """
    if len(prices) < 60:
        return ExpertSignal("均线排列", 0, 0, 0.3, "HOLD", "数据不足", {})

    close = prices["close"]

    # 计算均线
    ma5 = float(close.rolling(5).mean().iloc[-1])
    ma10 = float(close.rolling(10).mean().iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])

    price = float(close.iloc[-1])

    # 多头排列判断
    is_bullish = ma5 > ma10 > ma20 > ma60
    is_bearish = ma5 < ma10 < ma20 < ma60

    # 价格在均线上方/下方
    above_count = sum(1 for ma in [ma5, ma10, ma20, ma60] if price > ma)

    # 金叉/死叉 (MA5 穿越 MA20)
    ma5_prev = float(close.rolling(5).mean().iloc[-2])
    ma20_prev = float(close.rolling(20).mean().iloc[-2])
    golden_cross = ma5 > ma20 and ma5_prev <= ma20_prev
    death_cross = ma5 < ma20 and ma5_prev >= ma20_prev

    # 均线粘合 (各均线差距很小)
    ma_range = max(ma5, ma10, ma20, ma60) - min(ma5, ma10, ma20, ma60)
    is_converged = ma_range / price < 0.02

    direction = 0
    strength = 0.0
    signal = "HOLD"
    reason = ""

    if is_bullish:
        direction = 1
        strength = 0.8
        signal = "BUY"
        reason = f"多头排列, 价格在{above_count}条均线上方"
    elif is_bearish:
        direction = -1
        strength = 0.8
        signal = "SELL"
        reason = f"空头排列, 价格在{above_count}条均线上方"
    elif golden_cross:
        direction = 1
        strength = 0.7
        signal = "BUY"
        reason = f"MA5金叉MA20, 价格在{above_count}条均线上方"
    elif death_cross:
        direction = -1
        strength = 0.7
        signal = "SELL"
        reason = f"MA5死叉MA20, 价格在{above_count}条均线上方"
    elif is_converged:
        # 均线粘合 → 变盘信号
        if price > ma20:
            direction = 1
            strength = 0.5
            signal = "BUY"
            reason = f"均线粘合, 价格在MA20上方, 可能向上突破"
        else:
            direction = -1
            strength = 0.5
            signal = "SELL"
            reason = f"均线粘合, 价格在MA20下方, 可能向下突破"
    elif above_count >= 3:
        direction = 1
        strength = 0.4
        signal = "BUY"
        reason = f"偏多, 价格在{above_count}/4条均线上方"
    elif above_count <= 1:
        direction = -1
        strength = 0.4
        signal = "SELL"
        reason = f"偏空, 价格在{above_count}/4条均线上方"
    else:
        reason = f"中性, 价格在{above_count}/4条均线上方"

    return ExpertSignal(
        strategy="均线排列",
        direction=direction,
        strength=strength,
        confidence=0.5 + strength * 0.3,
        signal=signal,
        reason=reason,
        details={
            "ma5": round(ma5, 2), "ma10": round(ma10, 2),
            "ma20": round(ma20, 2), "ma60": round(ma60, 2),
            "above_count": above_count, "golden_cross": golden_cross,
            "death_cross": death_cross, "converged": is_converged,
        },
    )


# ═══════════════════════════════════════════════════════════════════════
# 综合高手策略
# ═══════════════════════════════════════════════════════════════════════

def expert_consensus(prices: pd.DataFrame) -> dict:
    """综合所有高手策略, 返回共识信号.

    Returns:
        dict: {
            "direction": int,      # 共识方向
            "confidence": float,   # 共识置信度
            "signal": str,         # BUY/SELL/HOLD
            "reason": str,         # 综合理由
            "strategies": list,    # 各策略详情
        }
    """
    strategies = [
        northbound_strategy(prices),
        limit_up_strategy(prices),
        leader_strategy(prices),
        volume_price_strategy(prices),
        ma_alignment_strategy(prices),
    ]

    # 统计方向
    buy_signals = [s for s in strategies if s.direction == 1]
    sell_signals = [s for s in strategies if s.direction == -1]

    buy_strength = sum(s.strength for s in buy_signals)
    sell_strength = sum(s.strength for s in sell_signals)

    # 共识判断
    if len(buy_signals) >= 3 and buy_strength > sell_strength * 1.5:
        direction = 1
        confidence = min(0.9, 0.5 + buy_strength * 0.3)
        signal = "BUY"
        reasons = [s.reason for s in buy_signals]
        reason = "; ".join(reasons[:3])
    elif len(sell_signals) >= 3 and sell_strength > buy_strength * 1.5:
        direction = -1
        confidence = min(0.9, 0.5 + sell_strength * 0.3)
        signal = "SELL"
        reasons = [s.reason for s in sell_signals]
        reason = "; ".join(reasons[:3])
    elif len(buy_signals) >= 2 and buy_strength > sell_strength:
        direction = 1
        confidence = 0.5 + buy_strength * 0.2
        signal = "BUY"
        reason = f"{len(buy_signals)}/5 策略看多"
    elif len(sell_signals) >= 2 and sell_strength > buy_strength:
        direction = -1
        confidence = 0.5 + sell_strength * 0.2
        signal = "SELL"
        reason = f"{len(sell_signals)}/5 策略看空"
    else:
        direction = 0
        confidence = 0.4
        signal = "HOLD"
        reason = f"分歧: {len(buy_signals)}买/{len(sell_signals)}卖"

    return {
        "direction": direction,
        "confidence": round(confidence, 2),
        "signal": signal,
        "reason": reason,
        "strategies": [
            {"name": s.strategy, "direction": s.direction, "signal": s.signal, "reason": s.reason}
            for s in strategies
        ],
        "buy_count": len(buy_signals),
        "sell_count": len(sell_signals),
    }
