"""情绪面数据层 — RSI极端值+市场情绪+散户逆向行为。

核心原理: 散户行为可预测，极端情绪是反向信号。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from quanttrader.engine.voter import DimensionVote

log = logging.getLogger(__name__)


def get_rsi_extreme(prices: pd.DataFrame) -> dict:
    """RSI极端检测 — 逆向信号核心。

    返回:
        {"rsi": float, "zone": str, "contrarian_signal": int, "strength": float}
        contrarian_signal: 1=逆向做多, -1=逆向做空, 0=中性
        strength: 0~1, 极端程度
    """
    if prices is None or len(prices) < 20:
        return {"rsi": 50.0, "zone": "neutral", "contrarian_signal": 0, "strength": 0.0}

    closes = prices["close"].astype(float)

    # RSI(14) 计算 (Wilder 平滑)
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))

    # 用 EWM 模拟 Wilder 平滑 (alpha=1/14)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0

    # 极端区域判定 (逆向逻辑)
    if rsi >= 80:
        zone = "极度贪婪"
        contrarian_signal = -1  # 极度贪婪 → 逆向做空
        strength = min(1.0, (rsi - 80) / 20 * 0.8 + 0.2)  # 80→0.2, 100→1.0
    elif rsi >= 70:
        zone = "贪婪"
        contrarian_signal = -1
        strength = (rsi - 70) / 10 * 0.19 + 0.01  # 70→0.01, 80→0.2
    elif rsi <= 20:
        zone = "极度恐惧"
        contrarian_signal = 1   # 极度恐惧 → 逆向做多
        strength = min(1.0, (20 - rsi) / 20 * 0.8 + 0.2)
    elif rsi <= 30:
        zone = "恐惧"
        contrarian_signal = 1
        strength = (30 - rsi) / 10 * 0.19 + 0.01
    else:
        zone = "中性"
        contrarian_signal = 0
        strength = 0.0

    return {
        "rsi": round(rsi, 2),
        "zone": zone,
        "contrarian_signal": contrarian_signal,
        "strength": round(strength, 3),
    }


def get_market_breadth(prices_dict: dict[str, pd.DataFrame]) -> dict:
    """市场广度 — 多品种涨跌比。

    返回:
        {"up_count": int, "down_count": int, "breadth_pct": float, "signal": str}
        breadth_pct: 上涨品种占比 (0~1)
        signal: "strong_bull" / "bull" / "neutral" / "bear" / "strong_bear"
    """
    if not prices_dict or len(prices_dict) <= 1:
        return {"up_count": 0, "down_count": 0, "breadth_pct": 0.5, "signal": "neutral"}

    up = 0
    down = 0

    for code, df in prices_dict.items():
        if df is None or len(df) < 5:
            continue
        closes = df["close"].astype(float)
        if len(closes) < 2:
            continue
        # 5日涨跌
        ret5 = float(closes.iloc[-1] / closes.iloc[-5] - 1) if len(closes) >= 5 else float(closes.iloc[-1] / closes.iloc[0] - 1)
        if ret5 > 0.005:
            up += 1
        elif ret5 < -0.005:
            down += 1

    total = up + down
    if total == 0:
        return {"up_count": 0, "down_count": 0, "breadth_pct": 0.5, "signal": "neutral"}

    breadth_pct = up / total

    if breadth_pct >= 0.8:
        signal = "strong_bull"
    elif breadth_pct >= 0.6:
        signal = "bull"
    elif breadth_pct <= 0.2:
        signal = "strong_bear"
    elif breadth_pct <= 0.4:
        signal = "bear"
    else:
        signal = "neutral"

    return {
        "up_count": up,
        "down_count": down,
        "breadth_pct": round(breadth_pct, 3),
        "signal": signal,
    }


def score_sentiment(prices: pd.DataFrame, code: str = "") -> DimensionVote:
    """情绪面综合评分 — 逆向信号核心维度。

    核心逻辑: RSI极端值作为逆向信号
    - RSI>80 极度贪婪 → 做空 (散户追高必被套)
    - RSI<20 极度恐惧 → 做多 (散户恐慌割肉是底部)
    - 中性区域 → 不操作

    weight=0.1, 逆向交易核心维度
    """
    if prices is None or len(prices) < 20:
        return DimensionVote(
            name="情绪面", direction=0, confidence=0.0,
            weight=0.1, reason="数据不足",
        )

    # 1. RSI极端检测 (主信号)
    rsi_info = get_rsi_extreme(prices)

    # 2. 价格位置辅助 (近期高低点位置)
    closes = prices["close"].astype(float)
    price = float(closes.iloc[-1])
    high_20 = float(closes.tail(20).max())
    low_20 = float(closes.tail(20).min())
    pos_20 = (price - low_20) / (high_20 - low_20) if high_20 != low_20 else 0.5

    # 3. 情绪极端加成 (连涨/连跌天数)
    consecutive = 0
    for i in range(len(closes) - 1, 0, -1):
        if i == len(closes) - 1:
            consecutive = 1 if closes.iloc[i] > closes.iloc[i - 1] else -1
        else:
            if consecutive > 0 and closes.iloc[i] > closes.iloc[i - 1]:
                consecutive += 1
            elif consecutive < 0 and closes.iloc[i] < closes.iloc[i - 1]:
                consecutive -= 1
            else:
                break

    streak_bonus = 0.0
    if abs(consecutive) >= 7:
        streak_bonus = 0.15  # 连涨/跌7天以上，情绪极端加成
    elif abs(consecutive) >= 5:
        streak_bonus = 0.08

    # 4. 综合逆向信号
    rsi_signal = rsi_info["contrarian_signal"]
    rsi_strength = rsi_info["strength"]

    if rsi_signal != 0:
        # 逆向信号: RSI极端 → 反向操作
        direction = rsi_signal
        confidence = min(0.9, rsi_strength * 0.7 + streak_bonus)
        reasons = [
            f"RSI={rsi_info['rsi']:.0f}",
            rsi_info["zone"],
            f"逆向{'多' if rsi_signal > 0 else '空'}",
        ]
        if abs(consecutive) >= 5:
            reasons.append(f"连{'涨' if consecutive > 0 else '跌'}{abs(consecutive)}天")
    else:
        # 中性区域: 无明显情绪极端
        direction = 0
        confidence = 0.2
        reasons = [f"RSI={rsi_info['rsi']:.0f}", "中性区域"]

    # 位置辅助: 价格在近期高位+RSI偏高 → 加强空信号
    if pos_20 > 0.85 and rsi_info["rsi"] > 65:
        confidence = min(0.9, confidence + 0.1)
        reasons.append("高位")
    elif pos_20 < 0.15 and rsi_info["rsi"] < 35:
        confidence = min(0.9, confidence + 0.1)
        reasons.append("低位")

    return DimensionVote(
        name="情绪面", direction=direction, confidence=confidence,
        weight=0.1, reason=" ".join(reasons),
    )
