"""模块1: DirectionPredictor — 方向预测适配器。

只读展示: 做多概率、做空概率、中性概率、方向置信度。
方向预测不得覆盖 SymbolFilter 硬规则。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def analyze(prices: pd.DataFrame, symbol: str = "", **kwargs) -> dict:
    """综合多源方向预测，返回概率分布和置信度。

    使用技术指标投票法生成方向概率:
      - RSI (14)
      - MACD 交叉
      - 均线排列 (SMA5/20/60)
      - 布林带位置
      - 动量 (ROC)

    每个指标投一票，汇总为 long/short/neutral 概率。

    Args:
        prices: OHLCV DataFrame
        symbol: 品种代码

    Returns:
        dict: 方向预测展示数据
    """
    if prices is None or len(prices) < 60:
        return _empty(symbol, "数据不足（需至少60根K线）")

    closes = prices["close"].astype(float)
    highs = prices["high"].astype(float) if "high" in prices.columns else closes
    lows = prices["low"].astype(float) if "low" in prices.columns else closes

    # ── 各维度投票 ──
    votes = []

    # 1. RSI (14)
    rsi = _compute_rsi(closes, 14)
    if rsi < 30:
        votes.append(("rsi", 1, 0.7, f"RSI={rsi:.0f} 超卖"))
    elif rsi > 70:
        votes.append(("rsi", -1, 0.7, f"RSI={rsi:.0f} 超买"))
    else:
        votes.append(("rsi", 0, 0.3, f"RSI={rsi:.0f} 中性"))

    # 2. MACD 交叉
    macd_signal = _compute_macd_signal(closes)
    votes.append(("macd", macd_signal["direction"], macd_signal["confidence"], macd_signal["reason"]))

    # 3. 均线排列
    ma_signal = _compute_ma_alignment(closes)
    votes.append(("ma_alignment", ma_signal["direction"], ma_signal["confidence"], ma_signal["reason"]))

    # 4. 布林带位置
    bb_signal = _compute_bb_position(closes)
    votes.append(("bollinger", bb_signal["direction"], bb_signal["confidence"], bb_signal["reason"]))

    # 5. 动量 (ROC 10)
    roc = _compute_roc(closes, 10)
    if roc > 1.0:
        votes.append(("momentum", 1, min(0.8, abs(roc) / 3.0), f"ROC10={roc:.1f}% 上涨动量"))
    elif roc < -1.0:
        votes.append(("momentum", -1, min(0.8, abs(roc) / 3.0), f"ROC10={roc:.1f}% 下跌动量"))
    else:
        votes.append(("momentum", 0, 0.3, f"ROC10={roc:.1f}% 无明显动量"))

    # ── 汇总概率 ──
    total_conf = sum(v[2] for v in votes) or 1.0
    long_score = sum(v[2] for v in votes if v[1] == 1) / total_conf
    short_score = sum(v[2] for v in votes if v[1] == -1) / total_conf
    neutral_score = sum(v[2] for v in votes if v[1] == 0) / total_conf

    # 归一化
    total = long_score + short_score + neutral_score or 1.0
    long_prob = round(long_score / total, 3)
    short_prob = round(short_score / total, 3)
    neutral_prob = round(neutral_score / total, 3)

    # 方向判定
    if long_prob > short_prob and long_prob > neutral_prob and long_prob > 0.4:
        direction = 1
        direction_label = "做多"
    elif short_prob > long_prob and short_prob > neutral_prob and short_prob > 0.4:
        direction = -1
        direction_label = "做空"
    else:
        direction = 0
        direction_label = "观望"

    # 置信度: 最高概率 - 次高概率 的差距
    probs = sorted([long_prob, short_prob, neutral_prob], reverse=True)
    confidence = round(probs[0] - probs[1], 3)

    return {
        "symbol": symbol,
        "probabilities": {
            "long": long_prob,
            "short": short_prob,
            "neutral": neutral_prob,
        },
        "direction": direction,
        "direction_label": direction_label,
        "confidence": confidence,
        "sources": [
            {
                "name": v[0],
                "signal": {1: "LONG", -1: "SHORT", 0: "NEUTRAL"}.get(v[1], "?"),
                "confidence": round(v[2], 3),
                "reason": v[3],
            }
            for v in votes
        ],
        "consensus_method": "technical投票法（5维度加权）",
        "symbol_filter_override": False,  # 铁律: 方向预测不覆盖 SymbolFilter
        "strategy_impact": "none",
    }


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "probabilities": {"long": 0, "short": 0, "neutral": 1},
        "direction": 0,
        "direction_label": "未知",
        "confidence": 0,
        "sources": [],
        "consensus_method": reason,
        "symbol_filter_override": False,
        "strategy_impact": "none",
    }


def _compute_rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0


def _compute_macd_signal(closes: pd.Series) -> dict:
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    hist = macd - signal

    if len(hist) < 3:
        return {"direction": 0, "confidence": 0.3, "reason": "MACD 数据不足"}

    curr = float(hist.iloc[-1])
    prev = float(hist.iloc[-2])

    if curr > 0 and prev <= 0:
        return {"direction": 1, "confidence": 0.65, "reason": "MACD 金叉"}
    elif curr < 0 and prev >= 0:
        return {"direction": -1, "confidence": 0.65, "reason": "MACD 死叉"}
    elif curr > 0 and curr > prev:
        return {"direction": 1, "confidence": 0.5, "reason": "MACD 多头增强"}
    elif curr < 0 and curr < prev:
        return {"direction": -1, "confidence": 0.5, "reason": "MACD 空头增强"}
    else:
        return {"direction": 0, "confidence": 0.3, "reason": "MACD 信号模糊"}


def _compute_ma_alignment(closes: pd.Series) -> dict:
    sma5 = float(closes.tail(5).mean())
    sma20 = float(closes.tail(20).mean())
    sma60 = float(closes.tail(60).mean()) if len(closes) >= 60 else sma20

    if sma5 > sma20 > sma60:
        return {"direction": 1, "confidence": 0.6, "reason": f"多头排列 (SMA5={sma5:.0f}>SMA20={sma20:.0f}>SMA60={sma60:.0f})"}
    elif sma5 < sma20 < sma60:
        return {"direction": -1, "confidence": 0.6, "reason": f"空头排列 (SMA5={sma5:.0f}<SMA20={sma20:.0f}<SMA60={sma60:.0f})"}
    else:
        return {"direction": 0, "confidence": 0.3, "reason": "均线纠缠，无明确排列"}


def _compute_bb_position(closes: pd.Series) -> dict:
    sma20 = closes.rolling(20).mean()
    std20 = closes.rolling(20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20

    if len(closes) < 20:
        return {"direction": 0, "confidence": 0.3, "reason": "布林带数据不足"}

    last_close = float(closes.iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])
    last_mid = float(sma20.iloc[-1])
    band_width = last_upper - last_lower or 1

    pct_b = (last_close - last_lower) / band_width

    if pct_b > 0.95:
        return {"direction": -1, "confidence": 0.55, "reason": f"触及上轨 (%B={pct_b:.2f})"}
    elif pct_b < 0.05:
        return {"direction": 1, "confidence": 0.55, "reason": f"触及下轨 (%B={pct_b:.2f})"}
    elif pct_b > 0.7:
        return {"direction": -1, "confidence": 0.35, "reason": f"偏上轨 (%B={pct_b:.2f})"}
    elif pct_b < 0.3:
        return {"direction": 1, "confidence": 0.35, "reason": f"偏下轨 (%B={pct_b:.2f})"}
    else:
        return {"direction": 0, "confidence": 0.3, "reason": f"中轨附近 (%B={pct_b:.2f})"}


def _compute_roc(closes: pd.Series, period: int = 10) -> float:
    if len(closes) <= period:
        return 0.0
    return float((closes.iloc[-1] / closes.iloc[-period - 1] - 1) * 100)
