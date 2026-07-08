"""成交量分析模块 — 量比/量价背离/资金流向/OBV斜率.

专注成交量维度的分析, 与技术指标互补.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════
# 量比 (Volume Ratio)
# ═══════════════════════════════════════════════════════════════════════

def calc_volume_ratio(
    volume: pd.Series,
    short: int = 5,
    long: int = 20,
) -> dict:
    """计算量比 = 短期均量 / 长期均量.

    Returns:
        dict: {
            "ratio": float,
            "level": str,     # "缩量" | "温和" | "放量" | "巨量"
            "score": float,   # 0-100
        }
    """
    if len(volume) < long:
        return {"ratio": 1.0, "level": "温和", "score": 50}

    vol_short = volume.iloc[-short:].mean()
    vol_long = volume.iloc[-long:].mean()
    ratio = float(vol_short / vol_long) if vol_long > 0 else 1.0

    if ratio >= 3.0:
        level = "巨量"
    elif ratio >= 1.8:
        level = "放量"
    elif ratio >= 0.8:
        level = "温和"
    else:
        level = "缩量"

    # 温和放量最佳, 极端量需警惕
    if 1.2 <= ratio <= 2.0:
        score = 70 + (ratio - 1.2) * 25
    elif 0.8 <= ratio < 1.2:
        score = 55
    elif ratio > 2.0:
        score = max(40, 70 - (ratio - 2.0) * 15)
    else:
        score = 35

    return {
        "ratio": round(ratio, 2),
        "level": level,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# OBV 斜率 (On-Balance Volume Slope)
# ═══════════════════════════════════════════════════════════════════════

def calc_obv_slope(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> dict:
    """计算 OBV 的线性回归斜率, 判断资金流向趋势.

    Returns:
        dict: {
            "slope": float,      # 标准化斜率
            "direction": str,    # "流入" | "流出" | "持平"
            "strength": str,     # "强" | "中" | "弱"
            "score": float,
        }
    """
    if len(close) < period or len(volume) < period:
        return {"slope": 0, "direction": "持平", "strength": "弱", "score": 50}

    direction = np.sign(close.diff())
    obv = (volume * direction).cumsum()
    obv_window = obv.iloc[-period:].values

    x = np.arange(len(obv_window))
    slope = float(np.polyfit(x, obv_window, 1)[0])
    norm = max(float(obv.iloc[-period:].std()), 1)
    slope_norm = slope / norm

    if slope_norm > 0.5:
        direction = "流入"
        strength = "强"
    elif slope_norm > 0.2:
        direction = "流入"
        strength = "中"
    elif slope_norm > 0.05:
        direction = "流入"
        strength = "弱"
    elif slope_norm < -0.5:
        direction = "流出"
        strength = "强"
    elif slope_norm < -0.2:
        direction = "流出"
        strength = "中"
    elif slope_norm < -0.05:
        direction = "流出"
        strength = "弱"
    else:
        direction = "持平"
        strength = "弱"

    score = 50 + slope_norm * 40
    return {
        "slope": round(slope_norm, 3),
        "direction": direction,
        "strength": strength,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 量价背离 (Volume-Price Divergence)
# ═══════════════════════════════════════════════════════════════════════

def calc_volume_price_divergence(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> dict:
    """检测量价背离.

    Returns:
        dict: {
            "divergence": str,   # "none" | "bearish" | "bullish"
            "detail": str,       # 描述
            "score": float,
        }
    """
    if len(close) < period or len(volume) < period:
        return {"divergence": "none", "detail": "数据不足", "score": 50}

    price_ret = float(close.iloc[-1] / close.iloc[-period] - 1)
    vol_ret = float(volume.iloc[-5:].mean() / volume.iloc[-period:-5].mean() - 1) if volume.iloc[-period:-5].mean() > 0 else 0

    divergence = "none"
    detail = "量价配合"

    # 价涨量缩 → 顶背离
    if price_ret > 0.03 and vol_ret < -0.2:
        divergence = "bearish"
        detail = f"价涨{price_ret*100:.1f}%但量缩{vol_ret*100:.0f}%，上攻乏力"
    # 价跌量增 → 底背离 (可能恐慌出尽)
    elif price_ret < -0.03 and vol_ret > 0.5:
        divergence = "bullish"
        detail = f"价跌{price_ret*100:.1f}%但量增{vol_ret*100:.0f}%，可能恐慌出尽"
    # 价涨量增 → 健康
    elif price_ret > 0.03 and vol_ret > 0.2:
        detail = f"量价齐升，趋势健康"
    # 价跌量缩 → 缩量调整
    elif price_ret < -0.03 and vol_ret < -0.2:
        detail = f"缩量调整，等待企稳"

    score = 50
    if divergence == "bullish":
        score = 65
    elif divergence == "bearish":
        score = 35
    elif price_ret > 0 and vol_ret > 0:
        score = 60
    elif price_ret < 0 and vol_ret < 0:
        score = 45

    return {
        "divergence": divergence,
        "detail": detail,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 资金流向估算 (Money Flow Estimation)
# ═══════════════════════════════════════════════════════════════════════

def estimate_money_flow(
    df: pd.DataFrame,
    period: int = 20,
) -> dict:
    """估算主力/散户资金流向 (基于量价关系的简化模型).

    Returns:
        dict: {
            "net_flow": float,       # 净流向 (正=流入, 负=流出)
            "flow_pct": float,       # 净流向占总成交比
            "direction": str,        # "主力流入" | "主力流出" | "均衡"
            "consecutive": int,      # 连续流入/流出天数
            "score": float,
        }
    """
    if len(df) < period or "volume" not in df.columns:
        return {"net_flow": 0, "flow_pct": 0, "direction": "均衡",
                "consecutive": 0, "score": 50}

    close = df["close"]
    volume = df["volume"]
    high = df["high"]
    low = df["low"]

    # MFI 思路: 上涨日成交额视为流入, 下跌日视为流出
    typical = (high + low + close) / 3
    money_flow = typical * volume
    direction = close.diff()

    positive_flow = money_flow.where(direction > 0, 0).rolling(period).sum()
    negative_flow = money_flow.where(direction < 0, 0).rolling(period).sum()
    net = positive_flow - negative_flow
    total = positive_flow + negative_flow

    net_val = float(net.iloc[-1])
    total_val = float(total.iloc[-1])
    flow_pct = net_val / total_val if total_val > 0 else 0

    if flow_pct > 0.15:
        direction = "主力流入"
    elif flow_pct < -0.15:
        direction = "主力流出"
    else:
        direction = "均衡"

    # 连续流入/流出天数
    daily_net = money_flow.where(close.diff() > 0, 0) - money_flow.where(close.diff() < 0, 0)
    consecutive = 0
    sign = 1 if float(daily_net.iloc[-1]) > 0 else -1
    for v in daily_net.iloc[::-1]:
        if (v > 0 and sign > 0) or (v < 0 and sign < 0):
            consecutive += 1
        else:
            break

    score = 50 + flow_pct * 100
    return {
        "net_flow": round(net_val, 0),
        "flow_pct": round(flow_pct, 4),
        "direction": direction,
        "consecutive": consecutive,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 成交量综合摘要
# ═══════════════════════════════════════════════════════════════════════

def volume_summary(df: pd.DataFrame) -> dict:
    """一次性计算所有成交量指标, 返回综合摘要."""
    if df is None or len(df) < 20 or "volume" not in df.columns:
        return {"error": "数据不足", "composite_score": 50}

    close = df["close"]
    volume = df["volume"]

    vol_ratio = calc_volume_ratio(volume)
    obv_slope = calc_obv_slope(close, volume)
    vp_div = calc_volume_price_divergence(close, volume)
    money_flow = estimate_money_flow(df)

    scores = [
        vol_ratio["score"] * 0.25,
        obv_slope["score"] * 0.30,
        vp_div["score"] * 0.20,
        money_flow["score"] * 0.25,
    ]
    composite = sum(scores)

    return {
        "volume_ratio": vol_ratio,
        "obv_slope": obv_slope,
        "vp_divergence": vp_div,
        "money_flow": money_flow,
        "composite_score": round(composite, 1),
    }
