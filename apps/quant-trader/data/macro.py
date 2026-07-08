"""宏观面数据层 — 美元指数+PMI+政策方向。

核心原理: 宏观环境决定商品大方向。
"""
from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from quanttrader.engine.voter import DimensionVote

log = logging.getLogger(__name__)

# 历史月度宏观体制参考 (简化版: 月份→体制+分数)
# 分数: -1(极度紧缩) ~ +1(极度宽松)
_MACRO_CALENDAR = {
    1:  ("easy_stable",    0.3),   # 年初: 财政扩张预期
    2:  ("easy_stable",    0.2),
    3:  ("tight_stable",  -0.1),   # 两会后政策落地
    4:  ("tight_stable",  -0.2),
    5:  ("tight_easing",  -0.3),   # 经济数据走弱
    6:  ("tight_easing",  -0.2),   # 年中宽松预期
    7:  ("easy_tightening", 0.1),  # 下半年政策收紧
    8:  ("easy_tightening", 0.0),
    9:  ("tight_stable",  -0.1),   # 传统旺季
    10: ("tight_stable",   0.0),
    11: ("easy_stable",    0.2),   # 年末宽松
    12: ("easy_stable",    0.3),   # 跨年行情
}


def get_dxy_trend() -> dict:
    """美元指数趋势分析。

    返回:
        {"dxy": float, "trend": str, "impact": str}
        trend: "up" / "down" / "flat"
        impact: "bullish_commodity" / "bearish_commodity" / "neutral"
    """
    # 尝试 akshare 获取美元指数
    try:
        import akshare as ak
        # 美元指数历史数据
        df = ak.currency_boc_safe(symbol="美元")
        if df is not None and len(df) >= 20:
            # 取最近20个交易日
            df = df.sort_index().tail(20)
            dxy_now = float(df["收盘"].iloc[-1])
            dxy_20d_ago = float(df["收盘"].iloc[0])
            pct_change = (dxy_now / dxy_20d_ago - 1) * 100

            if pct_change > 1.5:
                trend = "up"
                impact = "bearish_commodity"
            elif pct_change < -1.5:
                trend = "down"
                impact = "bullish_commodity"
            else:
                trend = "flat"
                impact = "neutral"

            return {
                "dxy": round(dxy_now, 2),
                "trend": trend,
                "impact": impact,
                "pct_change_20d": round(pct_change, 2),
            }
    except Exception as e:
        log.debug(f"akshare DXY fetch failed: {e}")

    # Fallback: 使用默认值 (基于当前月份估算)
    month = datetime.now().month
    if month in (11, 12, 1, 2):
        # 年末/年初通常美元偏弱
        return {"dxy": 103.5, "trend": "flat", "impact": "neutral", "pct_change_20d": 0.0}
    elif month in (6, 7, 8):
        # 年中通常美元偏强
        return {"dxy": 104.5, "trend": "flat", "impact": "neutral", "pct_change_20d": 0.0}
    else:
        return {"dxy": 104.0, "trend": "flat", "impact": "neutral", "pct_change_20d": 0.0}


def get_macro_regime() -> dict:
    """宏观体制判断 — 基于当前月份+历史周期。

    返回:
        {"regime": str, "score": float}
        regime: "easy_tightening" / "easy_stable" / "tight_stable" / "tight_easing"
        score: -1(极度紧缩) ~ +1(极度宽松)
    """
    month = datetime.now().month
    regime, score = _MACRO_CALENDAR.get(month, ("tight_stable", 0.0))

    return {
        "regime": regime,
        "score": round(score, 2),
        "month": month,
        "description": _regime_description(regime),
    }


def _regime_description(regime: str) -> str:
    """体制中文描述。"""
    descriptions = {
        "easy_tightening": "宽松转紧缩 (政策收紧初期)",
        "easy_stable": "宽松稳定 (流动性充裕)",
        "tight_stable": "紧缩稳定 (政策观察期)",
        "tight_easing": "紧缩转宽松 (政策放松预期)",
    }
    return descriptions.get(regime, "未知体制")


def score_macro(code: str = "") -> DimensionVote:
    """宏观面综合评分 — DXY趋势(60%) + 宏观体制(40%)。

    核心逻辑:
    - DXY下行 → 商品牛市 (美元贬值推升商品价格)
    - DXY上行 → 商品熊市 (美元升值压制商品)
    - 宽松体制 → 利好商品
    - 紧缩体制 → 利空商品

    weight=0.1, 宏观方向维度
    """
    # 1. DXY趋势 (60%)
    dxy_info = get_dxy_trend()

    dxy_score = 0.0
    if dxy_info["trend"] == "down":
        dxy_score = 0.8  # DXY下行 → 商品利多
    elif dxy_info["trend"] == "up":
        dxy_score = -0.8  # DXY上行 → 商品利空
    else:
        dxy_score = 0.0

    # 2. 宏观体制 (40%)
    macro_info = get_macro_regime()
    macro_score = macro_info["score"]  # -1 ~ +1

    # 3. 加权综合
    combined = dxy_score * 0.6 + macro_score * 0.4

    # 方向判定
    if combined > 0.2:
        direction = 1   # 宏观利多商品
    elif combined < -0.2:
        direction = -1  # 宏观利空商品
    else:
        direction = 0

    confidence = min(0.8, abs(combined) * 0.7 + 0.1)

    # 构造理由
    reasons = []
    if dxy_info["trend"] != "flat":
        reasons.append(f"DXY {dxy_info['trend']} ({dxy_info.get('pct_change_20d', 0):+.1f}%)")
    else:
        reasons.append("DXY平")

    reasons.append(f"{macro_info['regime']}({macro_info['score']:+.1f})")

    if combined > 0.3:
        reasons.append("宏观利多")
    elif combined < -0.3:
        reasons.append("宏观利空")

    return DimensionVote(
        name="宏观面", direction=direction, confidence=confidence,
        weight=0.1, reason=" ".join(reasons),
    )
