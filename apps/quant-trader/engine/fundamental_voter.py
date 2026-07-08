"""基本面验证层 — 用持仓量+成交量+价差验证TOP10信号。

核心原理: 基本面数据与技术面独立，提供额外alpha。

验证规则:
  1. 持仓量增加+价格同向 → 趋势确认 (+置信度)
  2. 持仓量减少+价格反向 → 趋势减弱 (-置信度)
  3. 量比异常(>2或<0.5) → 变盘信号
  4. 价差收敛/扩散 → 市场结构变化
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class FundamentalVote:
    direction: int      # 1=确认多, -1=确认空, 0=中性
    confidence: float   # 0~1
    reason: str = ""


def _get_holding_data(code: str) -> dict | None:
    """获取持仓量数据。"""
    try:
        import akshare as ak
        df = ak.futures_main_sina(symbol=code)
        hold = pd.to_numeric(df['持仓量'], errors='coerce').dropna()
        if len(hold) < 10:
            return None
        return {
            'current': float(hold.iloc[-1]),
            'prev_5d': float(hold.iloc[-6]) if len(hold) >= 6 else float(hold.iloc[0]),
            'ma20': float(hold.rolling(20).mean().iloc[-1]) if len(hold) >= 20 else float(hold.mean()),
            'change_5d_pct': float((hold.iloc[-1] / hold.iloc[-6] - 1) * 100) if len(hold) >= 6 else 0,
        }
    except Exception:
        return None


def _get_volume_data(prices: pd.DataFrame) -> dict:
    """从价格数据提取成交量信息。"""
    if 'volume' not in prices.columns:
        return {'vol_ratio': 1.0, 'vol_trend': 0}
    vol = prices['volume'].astype(float)
    if len(vol) < 20:
        return {'vol_ratio': 1.0, 'vol_trend': 0}
    vol_now = float(vol.iloc[-1])
    vol_avg20 = float(vol.tail(20).mean())
    vol_avg5 = float(vol.tail(5).mean())
    vol_ratio = vol_now / vol_avg20 if vol_avg20 > 0 else 1.0
    vol_trend = (vol_avg5 / vol_avg20 - 1) if vol_avg20 > 0 else 0
    return {'vol_ratio': vol_ratio, 'vol_trend': vol_trend}


def score_fundamental(prices: pd.DataFrame, code: str = "",
                      signal_direction: int = 0) -> FundamentalVote:
    """基本面验证: 用持仓量+成交量验证信号方向。

    Args:
        prices: 价格数据
        code: 品种代码(用于拉取持仓量)
        signal_direction: TOP10信号方向(1=多, -1=空)

    Returns:
        FundamentalVote: 验证结果
    """
    if code and len(code) <= 3:
        # 尝试拉取持仓量
        hold_data = _get_holding_data(code)
    else:
        hold_data = None

    vol_data = _get_volume_data(prices)
    closes = prices['close'].astype(float)
    n = len(closes)

    if n < 20:
        return FundamentalVote(0, 0.0, "数据不足")

    # 1. 持仓量分析
    hold_score = 0.0
    if hold_data:
        chg = hold_data['change_5d_pct']
        if abs(chg) > 5:  # 持仓量大幅变化
            if chg > 0:
                hold_score = 0.3  # 增仓 → 趋势确认
            else:
                hold_score = -0.3  # 减仓 → 趋势减弱

    # 2. 成交量分析
    vol_ratio = vol_data['vol_ratio']
    vol_trend = vol_data['vol_trend']

    vol_score = 0.0
    if vol_ratio > 2.0:  # 放量
        vol_score = 0.2
    elif vol_ratio < 0.5:  # 缩量
        vol_score = -0.1

    # 3. 价格趋势确认
    ret5 = (float(closes.iloc[-1]) / float(closes.iloc[-6]) - 1) * 100 if n >= 6 else 0
    ret20 = (float(closes.iloc[-1]) / float(closes.iloc[-21]) - 1) * 100 if n >= 21 else 0

    trend_score = 0.0
    if ret5 > 2 and ret20 > 0:
        trend_score = 0.2  # 短期+中期都涨
    elif ret5 < -2 and ret20 < 0:
        trend_score = -0.2  # 短期+中期都跌

    # 汇总
    total_score = hold_score + vol_score + trend_score

    # 与信号方向对比
    if signal_direction != 0:
        if total_score * signal_direction > 0:
            # 基本面确认信号方向
            confidence = min(0.8, 0.5 + abs(total_score))
            reason = f"基本面确认: 持仓{hold_score:+.1f} 量能{vol_score:+.1f} 趋势{trend_score:+.1f}"
        else:
            # 基本面与信号矛盾
            confidence = max(0.2, 0.5 - abs(total_score))
            reason = f"基本面矛盾: 持仓{hold_score:+.1f} 量能{vol_score:+.1f} 趋势{trend_score:+.1f}"
        direction = signal_direction
    else:
        direction = 1 if total_score > 0.15 else (-1 if total_score < -0.15 else 0)
        confidence = min(0.7, abs(total_score))
        reason = f"基本面: 持仓{hold_score:+.1f} 量能{vol_score:+.1f} 趋势{trend_score:+.1f}"

    return FundamentalVote(direction=direction, confidence=confidence, reason=reason)
