"""资金面数据层 — 持仓量变化+主力资金方向+保证金变化。

核心原理: 资金是价格的燃料，持仓变化领先价格变化。

四大模式:
  增仓上涨 → 多头主动入场，趋势延续（强多）
  增仓下跌 → 空头主动入场，趋势延续（强空）
  减仓上涨 → 多头获利了结，上涨乏力（弱多）
  减仓下跌 → 空头平仓离场，下跌见底（弱空/反弹信号）
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from quanttrader.engine.voter import DimensionVote

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 1. 持仓量变化分析
# ══════════════════════════════════════════════════════════════════

def get_holding_change(
    code: str,
    prices: Optional[pd.DataFrame] = None,
) -> dict:
    """持仓量变化分析。

    从 prices DataFrame 的 'hold' 列读取持仓量，计算变化和模式。

    Args:
        code: 合约代码（如 'IF2406'），用于日志。
        prices: 包含 'hold' 列的行情数据，可选。

    Returns:
        dict: {
            hold_change:   int   — 最新持仓量 vs 前日，正增负减
            hold_change_pct: float — 变化百分比
            avg_5d_change:  float — 近5日平均持仓变化
            pattern:       str   — 四大模式之一
            signal:        int   — 1=bullish, -1=bearish, 0=neutral
            confidence:    float — 置信度 0~1
        }
    """
    default = {
        "hold_change": 0,
        "hold_change_pct": 0.0,
        "avg_5d_change": 0.0,
        "pattern": "无数据",
        "signal": 0,
        "confidence": 0.0,
    }

    try:
        if prices is None or "hold" not in prices.columns:
            return default

        holds = prices["hold"].astype(float).dropna()
        if len(holds) < 6:
            return {**default, "pattern": "数据不足"}

        # 当前 vs 前日持仓量
        hold_now = float(holds.iloc[-1])
        hold_prev = float(holds.iloc[-2])
        hold_change = int(hold_now - hold_prev)
        hold_change_pct = (hold_change / hold_prev * 100) if hold_prev != 0 else 0.0

        # 近5日平均变化
        changes = holds.diff().dropna().tail(5)
        avg_5d_change = float(changes.mean()) if len(changes) > 0 else 0.0

        # 价格方向（最近一根K线收盘 vs 前一根）
        closes = prices["close"].astype(float).dropna()
        if len(closes) < 2:
            return {**default, "hold_change": hold_change, "hold_change_pct": hold_change_pct}

        price_now = float(closes.iloc[-1])
        price_prev = float(closes.iloc[-2])
        price_up = price_now > price_prev

        # 四大模式判定
        hold_increasing = hold_change > 0
        confidence = 0.0

        if hold_increasing and price_up:
            pattern = "增仓上涨"
            signal = 1
            # 多头主动开仓推动上涨，趋势延续信号强
            confidence = min(0.85, 0.50 + min(abs(hold_change_pct), 30) * 0.012)
        elif hold_increasing and not price_up:
            pattern = "增仓下跌"
            signal = -1
            # 空头主动开仓打压价格，下跌趋势延续
            confidence = min(0.85, 0.50 + min(abs(hold_change_pct), 30) * 0.012)
        elif not hold_increasing and price_up:
            pattern = "减仓上涨"
            signal = 0  # 中性偏弱，上涨缺乏新资金支撑
            confidence = min(0.60, 0.30 + min(abs(hold_change_pct), 30) * 0.01)
        elif not hold_increasing and not price_up:
            pattern = "减仓下跌"
            signal = 0  # 空头平仓主导，可能接近底部
            confidence = min(0.55, 0.25 + min(abs(hold_change_pct), 30) * 0.01)
        else:
            pattern = "持仓不变"
            signal = 0
            confidence = 0.1

        # 如果5日均变化方向与当日一致，增加置信度
        if avg_5d_change != 0:
            trend_aligned = (avg_5d_change > 0) == hold_increasing
            if trend_aligned and abs(signal) == 1:
                confidence = min(0.90, confidence + 0.10)

        return {
            "hold_change": hold_change,
            "hold_change_pct": round(hold_change_pct, 2),
            "avg_5d_change": round(avg_5d_change, 0),
            "pattern": pattern,
            "signal": signal,
            "confidence": round(confidence, 3),
        }

    except Exception as e:
        logger.warning("持仓量分析异常 [%s]: %s", code, e)
        return default


# ══════════════════════════════════════════════════════════════════
# 2. 量价背离检测
# ══════════════════════════════════════════════════════════════════

def get_volume_price_divergence(prices: pd.DataFrame) -> dict:
    """量价背离检测 — 比较近5根K线的价格方向与成交量方向。

    底背离: 价格下跌但成交量放大 → 抄底信号
    顶背离: 价格上涨但成交量萎缩 → 见顶信号

    Args:
        prices: 至少含 'close' + 'volume' 列的行情数据。

    Returns:
        dict: {
            type:        str  — "底背离" / "顶背离" / "量价配合" / "无数据"
            signal:      int  — 1=bullish, -1=bearish, 0=neutral
            confidence:  float — 置信度 0~1
            description: str  — 人类可读描述
        }
    """
    default = {
        "type": "无数据",
        "signal": 0,
        "confidence": 0.0,
        "description": "缺少成交量或价格数据",
    }

    try:
        if prices is None or "volume" not in prices.columns or "close" not in prices.columns:
            return default

        closes = prices["close"].astype(float).dropna()
        volumes = prices["volume"].astype(float).dropna()

        min_len = min(len(closes), len(volumes))
        if min_len < 6:
            return {**default, "description": f"数据不足(仅{min_len}条)"}

        # 取最近5根K线
        tail_n = 5
        c = closes.tail(tail_n).values
        v = volumes.tail(tail_n).values

        # 价格方向: 线性回归斜率符号
        x = np.arange(tail_n, dtype=float)
        price_slope = np.polyfit(x, c, 1)[0]
        price_falling = price_slope < 0

        # 成交量方向: 线性回归斜率符号
        vol_slope = np.polyfit(x, v, 1)[0]
        vol_rising = vol_slope > 0

        # 平均量用于归一化
        vol_avg = float(np.mean(v)) if np.mean(v) > 0 else 1.0
        vol_slope_pct = vol_slope / vol_avg * 100  # 量变化率

        # 价格变化幅度
        price_range = float(c[-1] - c[0])
        price_pct = abs(price_range / c[0] * 100) if c[0] != 0 else 0.0

        # 背离判定
        if price_falling and vol_rising:
            # 底背离: 价格跌但量放大，可能是恐慌抛售尾声，抄底机会
            strength = min(abs(vol_slope_pct), 20) / 20
            confidence = min(0.80, 0.40 + strength * 0.35)
            return {
                "type": "底背离",
                "signal": 1,
                "confidence": round(confidence, 3),
                "description": f"价格跌{price_pct:.1f}%但量增{vol_slope_pct:.1f}%，底部放量",
            }
        elif not price_falling and not vol_rising:
            # 顶背离: 价格涨但量萎缩，上涨缺乏资金支撑
            strength = min(abs(vol_slope_pct), 20) / 20
            confidence = min(0.80, 0.40 + strength * 0.35)
            return {
                "type": "顶背离",
                "signal": -1,
                "confidence": round(confidence, 3),
                "description": f"价格涨{price_pct:.1f}%但量缩{vol_slope_pct:.1f}%，上涨乏力",
            }
        elif not price_falling and vol_rising:
            # 量价齐升: 健康上涨
            return {
                "type": "量价配合",
                "signal": 1,
                "confidence": round(min(0.70, 0.40 + price_pct * 0.02), 3),
                "description": f"价涨{price_pct:.1f}%量增{vol_slope_pct:.1f}%，趋势健康",
            }
        elif price_falling and not vol_rising:
            # 缩量下跌: 抛压减轻，可能企稳
            return {
                "type": "量价配合",
                "signal": 0,
                "confidence": round(min(0.55, 0.25 + abs(vol_slope_pct) * 0.01), 3),
                "description": f"价跌{price_pct:.1f}%量缩{vol_slope_pct:.1f}%，抛压减轻",
            }
        else:
            return {
                "type": "量价配合",
                "signal": 0,
                "confidence": 0.3,
                "description": "量价变化不显著",
            }

    except Exception as e:
        logger.warning("量价背离检测异常: %s", e)
        return default


# ══════════════════════════════════════════════════════════════════
# 3. 资金面综合评分
# ══════════════════════════════════════════════════════════════════

def score_capital_flow(
    code: str,
    prices: Optional[pd.DataFrame] = None,
) -> DimensionVote:
    """资金面维度评分 — 持仓变化(60%) + 量价背离(40%)。

    Args:
        code: 合约代码。
        prices: 行情数据。

    Returns:
        DimensionVote: name="资金面", weight=0.25
    """
    empty_vote = DimensionVote(
        name="资金面", direction=0, confidence=0.0,
        weight=0.25, reason="无数据",
    )

    try:
        if prices is None or len(prices) < 6:
            return empty_vote

        # 子评分1: 持仓量变化 (60%)
        hold = get_holding_change(code, prices)
        hold_signal = hold["signal"]
        hold_conf = hold["confidence"]

        # 子评分2: 量价背离 (40%)
        div = get_volume_price_divergence(prices)
        div_signal = div["signal"]
        div_conf = div["confidence"]

        # 加权综合
        combined_score = hold_signal * hold_conf * 0.60 + div_signal * div_conf * 0.40

        # 方向判定
        if combined_score > 0.12:
            direction = 1
        elif combined_score < -0.12:
            direction = -1
        else:
            direction = 0

        confidence = min(0.90, abs(combined_score))

        # 拼接理由
        parts = []
        if hold["pattern"] not in ("无数据", "持仓不变", "数据不足"):
            parts.append(f"{hold['pattern']}({hold['hold_change_pct']:+.1f}%)")
        if div["type"] not in ("无数据", "量价配合"):
            parts.append(div["type"])
        if not parts:
            parts.append("资金面无明显信号")

        return DimensionVote(
            name="资金面",
            direction=direction,
            confidence=round(confidence, 3),
            weight=0.25,
            reason=" ".join(parts),
        )

    except Exception as e:
        logger.warning("资金面评分异常 [%s]: %s", code, e)
        return empty_vote
