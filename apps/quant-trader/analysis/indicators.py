"""扩展技术指标库 — MACD/ATR/KDJ/OBV/VWAP/均线排列/一目均衡表.

所有函数接受 pd.DataFrame (需含 open/high/low/close/volume 列) 或 pd.Series.
返回 dict 或 pd.Series/DataFrame, 便于管线集成.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════
# MACD (Moving Average Convergence Divergence)
# ═══════════════════════════════════════════════════════════════════════

def calc_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """计算 MACD 指标.

    Returns:
        dict: {
            "macd": float,       # MACD 线 (DIF)
            "signal": float,     # 信号线 (DEA)
            "histogram": float,  # 柱状图 (MACD - Signal)
            "histogram_prev": float,  # 前一日柱状图
            "cross": str,        # "golden" | "death" | "none"
            "divergence": str,   # "bullish" | "bearish" | "none"
            "score": float,      # 0-100 评分
        }
    """
    if len(close) < slow + signal:
        return {"macd": 0, "signal": 0, "histogram": 0, "histogram_prev": 0,
                "cross": "none", "divergence": "none", "score": 50}

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    m = float(macd_line.iloc[-1])
    s = float(signal_line.iloc[-1])
    h = float(histogram.iloc[-1])
    h_prev = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0

    # 金叉/死叉
    cross = "none"
    if h > 0 and h_prev <= 0:
        cross = "golden"
    elif h < 0 and h_prev >= 0:
        cross = "death"

    # 背离检测 (简化版: 价格新高但 MACD 未新高 → 顶背离)
    divergence = "none"
    lookback = min(20, len(close) - 1)
    if lookback >= 10:
        price_high = float(close.iloc[-lookback:].max())
        macd_high = float(macd_line.iloc[-lookback:].max())
        price_low = float(close.iloc[-lookback:].min())
        macd_low = float(macd_line.iloc[-lookback:].min())
        if float(close.iloc[-1]) >= price_high * 0.98 and m < macd_high * 0.8:
            divergence = "bearish"
        elif float(close.iloc[-1]) <= price_low * 1.02 and m > macd_low * 0.8:
            divergence = "bullish"

    # 评分
    score = 50.0
    if cross == "golden":
        score += 20
    elif cross == "death":
        score -= 20
    if h > 0:
        score += min(h / max(abs(m), 0.01) * 15, 15)
    else:
        score -= min(abs(h) / max(abs(m), 0.01) * 15, 15)
    if divergence == "bullish":
        score += 10
    elif divergence == "bearish":
        score -= 10
    if m > 0 and s > 0:
        score += 5
    elif m < 0 and s < 0:
        score -= 5

    return {
        "macd": round(m, 4),
        "signal": round(s, 4),
        "histogram": round(h, 4),
        "histogram_prev": round(h_prev, 4),
        "cross": cross,
        "divergence": divergence,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# ATR (Average True Range)
# ═══════════════════════════════════════════════════════════════════════

def calc_atr(
    df: pd.DataFrame,
    period: int = 14,
) -> dict:
    """计算 ATR 及波动率分位.

    Returns:
        dict: {
            "atr": float,          # 当前 ATR
            "atr_pct": float,      # ATR / close 百分比
            "atr_percentile": float, # ATR 在近 120 日的分位数 (0-100)
            "volatility_regime": str, # "low" | "normal" | "high" | "extreme"
            "score": float,        # 0-100 (低波动得分高)
        }
    """
    if len(df) < period + 1:
        return {"atr": 0, "atr_pct": 0, "atr_percentile": 50,
                "volatility_regime": "normal", "score": 50}

    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    atr_val = float(atr.iloc[-1])
    price = float(close.iloc[-1])
    atr_pct = atr_val / price if price > 0 else 0

    # 波动率分位 (近 120 日)
    lookback = min(120, len(atr) - 1)
    atr_window = atr.iloc[-lookback:].dropna()
    if len(atr_window) >= 20:
        percentile = float((atr_window < atr_val).sum() / len(atr_window) * 100)
    else:
        percentile = 50

    # 波动率区间
    if percentile >= 90:
        regime = "extreme"
    elif percentile >= 70:
        regime = "high"
    elif percentile >= 30:
        regime = "normal"
    else:
        regime = "low"

    # 评分: 低波动得分高 (适合入场)
    score = 50.0
    if regime == "low":
        score = 70 + (30 - percentile) * 0.5
    elif regime == "normal":
        score = 55 + (70 - percentile) * 0.3
    elif regime == "high":
        score = 40 + (70 - percentile) * 0.3
    else:
        score = 25

    return {
        "atr": round(atr_val, 4),
        "atr_pct": round(atr_pct, 4),
        "atr_percentile": round(percentile, 1),
        "volatility_regime": regime,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# KDJ (Stochastic Oscillator)
# ═══════════════════════════════════════════════════════════════════════

def calc_kdj(
    df: pd.DataFrame,
    period: int = 9,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> dict:
    """计算 KDJ 指标.

    Returns:
        dict: {
            "k": float, "d": float, "j": float,
            "cross": str,       # "golden" | "death" | "none"
            "zone": str,        # "oversold" | "neutral" | "overbought"
            "score": float,     # 0-100
        }
    """
    if len(df) < period + k_smooth + d_smooth:
        return {"k": 50, "d": 50, "j": 50, "cross": "none",
                "zone": "neutral", "score": 50}

    high = df["high"]
    low = df["low"]
    close = df["close"]

    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(span=k_smooth, adjust=False).mean()
    d = k.ewm(span=d_smooth, adjust=False).mean()
    j = 3 * k - 2 * d

    k_val = float(k.iloc[-1])
    d_val = float(d.iloc[-1])
    j_val = float(j.iloc[-1])
    k_prev = float(k.iloc[-2]) if len(k) >= 2 else k_val
    d_prev = float(d.iloc[-2]) if len(d) >= 2 else d_val

    # 金叉/死叉
    cross = "none"
    if k_val > d_val and k_prev <= d_prev:
        cross = "golden"
    elif k_val < d_val and k_prev >= d_prev:
        cross = "death"

    # 区间
    if k_val < 20 and d_val < 20:
        zone = "oversold"
    elif k_val > 80 and d_val > 80:
        zone = "overbought"
    else:
        zone = "neutral"

    # 评分
    score = 50.0
    if cross == "golden" and zone == "oversold":
        score = 80
    elif cross == "golden":
        score = 65
    elif cross == "death" and zone == "overbought":
        score = 20
    elif cross == "death":
        score = 35
    elif zone == "oversold":
        score = 60
    elif zone == "overbought":
        score = 40.0

    return {
        "k": round(k_val, 2),
        "d": round(d_val, 2),
        "j": round(j_val, 2),
        "cross": cross,
        "zone": zone,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# OBV (On-Balance Volume)
# ═══════════════════════════════════════════════════════════════════════

def calc_obv(df: pd.DataFrame) -> dict:
    """计算 OBV 及其斜率.

    Returns:
        dict: {
            "obv": float,
            "obv_sma20": float,
            "slope": float,       # 20 日标准化斜率
            "trend": str,         # "up" | "down" | "flat"
            "score": float,
        }
    """
    if len(df) < 20 or "volume" not in df.columns:
        return {"obv": 0, "obv_sma20": 0, "slope": 0, "trend": "flat", "score": 50}

    close = df["close"]
    volume = df["volume"]
    direction = np.sign(close.diff())
    obv = (volume * direction).cumsum()

    obv_val = float(obv.iloc[-1])
    obv_sma = float(obv.rolling(20).mean().iloc[-1])

    # 斜率: 最近 20 日 OBV 变化 / 标准化
    obv_20 = obv.iloc[-20:]
    if len(obv_20) >= 10:
        x = np.arange(len(obv_20))
        slope = float(np.polyfit(x, obv_20.values, 1)[0])
        norm = max(abs(obv_20.std()), 1)
        slope_norm = slope / norm
    else:
        slope_norm = 0

    if slope_norm > 0.3:
        trend = "up"
    elif slope_norm < -0.3:
        trend = "down"
    else:
        trend = "flat"

    score = 50 + slope_norm * 30
    return {
        "obv": round(obv_val, 0),
        "obv_sma20": round(obv_sma, 0),
        "slope": round(slope_norm, 3),
        "trend": trend,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# VWAP (Volume Weighted Average Price)
# ═══════════════════════════════════════════════════════════════════════

def calc_vwap(df: pd.DataFrame, period: int = 20) -> dict:
    """计算滚动 VWAP 及价格相对位置.

    Returns:
        dict: {
            "vwap": float,
            "price_vs_vwap": float,  # (close - vwap) / vwap %
            "position": str,         # "above" | "below" | "at"
            "score": float,
        }
    """
    if len(df) < period or "volume" not in df.columns:
        return {"vwap": 0, "price_vs_vwap": 0, "position": "at", "score": 50}

    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].clip(lower=1)
    cum_tp_vol = (typical * vol).rolling(period).sum()
    cum_vol = vol.rolling(period).sum()
    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)

    vwap_val = float(vwap.iloc[-1])
    price = float(df["close"].iloc[-1])
    diff_pct = (price - vwap_val) / vwap_val if vwap_val > 0 else 0

    if diff_pct > 0.01:
        position = "above"
    elif diff_pct < -0.01:
        position = "below"
    else:
        position = "at"

    # 价格在 VWAP 之上偏多, 但偏离过大可能回调
    score = 50.0
    if position == "above":
        score = min(65, 55 + diff_pct * 500)
    elif position == "below":
        score = max(35, 45 + diff_pct * 500)

    return {
        "vwap": round(vwap_val, 2),
        "price_vs_vwap": round(diff_pct, 4),
        "position": position,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 均线排列 (MA Alignment)
# ═══════════════════════════════════════════════════════════════════════

def calc_ma_alignment(
    close: pd.Series,
    periods: list[int] | None = None,
) -> dict:
    """计算均线排列 (多头/空头/缠绕).

    Returns:
        dict: {
            "alignment": str,    # "bullish" | "bearish" | "tangled"
            "above_count": int,  # 价格在多少根均线之上
            "total": int,        # 均线总数
            "ma_values": dict,   # 各均线值
            "score": float,
        }
    """
    if periods is None:
        periods = [5, 10, 20, 60, 120]

    if len(close) < max(periods):
        return {"alignment": "tangled", "above_count": 0, "total": len(periods),
                "ma_values": {}, "score": 50}

    price = float(close.iloc[-1])
    mas = {}
    above = 0
    values = []

    for p in periods:
        if len(close) >= p:
            ma = float(close.rolling(p).mean().iloc[-1])
            mas[f"ma{p}"] = round(ma, 2)
            values.append(ma)
            if price > ma:
                above += 1

    # 判断排列
    if len(values) >= 3:
        sorted_desc = all(values[i] >= values[i+1] for i in range(len(values)-1))
        sorted_asc = all(values[i] <= values[i+1] for i in range(len(values)-1))
        if sorted_desc and above >= len(values) - 1:
            alignment = "bullish"
        elif sorted_asc and above <= 1:
            alignment = "bearish"
        else:
            alignment = "tangled"
    else:
        alignment = "tangled"

    total = len(periods)
    score = 50.0
    if alignment == "bullish":
        score = 65 + (above / total) * 20
    elif alignment == "bearish":
        score = 35 - (above / total) * 20
    else:
        score = 45 + (above / total) * 15

    return {
        "alignment": alignment,
        "above_count": above,
        "total": total,
        "ma_values": mas,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 一目均衡表 (Ichimoku Cloud)
# ═══════════════════════════════════════════════════════════════════════

def calc_ichimoku(
    df: pd.DataFrame,
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
) -> dict:
    """计算一目均衡表关键信号.

    Returns:
        dict: {
            "tenkan": float,     # 转换线
            "kijun": float,      # 基准线
            "senkou_a": float,   # 先行 A
            "senkou_b": float,   # 先行 B
            "price_vs_cloud": str, # "above" | "in" | "below"
            "tk_cross": str,     # "golden" | "death" | "none"
            "score": float,
        }
    """
    if len(df) < senkou_b:
        return {"tenkan": 0, "kijun": 0, "senkou_a": 0, "senkou_b": 0,
                "price_vs_cloud": "in", "tk_cross": "none", "score": 50}

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tenkan_val = float((high.rolling(tenkan).max() + low.rolling(tenkan).min()).iloc[-1] / 2)
    kijun_val = float((high.rolling(kijun).max() + low.rolling(kijun).min()).iloc[-1] / 2)
    senkou_a_val = float((tenkan_val + kijun_val) / 2)
    senkou_b_val = float((high.rolling(senkou_b).max() + low.rolling(senkou_b).min()).iloc[-1] / 2)

    price = float(close.iloc[-1])
    cloud_top = max(senkou_a_val, senkou_b_val)
    cloud_bottom = min(senkou_a_val, senkou_b_val)

    if price > cloud_top:
        position = "above"
    elif price < cloud_bottom:
        position = "below"
    else:
        position = "in"

    # TK 交叉
    tenkan_prev = float((high.rolling(tenkan).max() + low.rolling(tenkan).min()).iloc[-2] / 2)
    kijun_prev = float((high.rolling(kijun).max() + low.rolling(kijun).min()).iloc[-2] / 2)
    tk_cross = "none"
    if tenkan_val > kijun_val and tenkan_prev <= kijun_prev:
        tk_cross = "golden"
    elif tenkan_val < kijun_val and tenkan_prev >= kijun_prev:
        tk_cross = "death"

    score = 50
    if position == "above":
        score += 15
    elif position == "below":
        score -= 15
    if tk_cross == "golden":
        score += 15
    elif tk_cross == "death":
        score -= 15
    if tenkan_val > kijun_val:
        score += 5

    return {
        "tenkan": round(tenkan_val, 2),
        "kijun": round(kijun_val, 2),
        "senkou_a": round(senkou_a_val, 2),
        "senkou_b": round(senkou_b_val, 2),
        "price_vs_cloud": position,
        "tk_cross": tk_cross,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 综合指标摘要
# ═══════════════════════════════════════════════════════════════════════

def indicator_summary(df: pd.DataFrame) -> dict:
    """一次性计算所有扩展指标, 返回综合摘要."""
    if df is None or len(df) < 30:
        return {"error": "数据不足", "composite_score": 50}

    close = df["close"]
    macd = calc_macd(close)
    atr = calc_atr(df)
    kdj = calc_kdj(df)
    obv = calc_obv(df)
    vwap = calc_vwap(df)
    ma = calc_ma_alignment(close)
    ichimoku = calc_ichimoku(df)

    scores = [
        macd["score"] * 0.20,
        atr["score"] * 0.10,
        kdj["score"] * 0.15,
        obv["score"] * 0.10,
        vwap["score"] * 0.10,
        ma["score"] * 0.20,
        ichimoku["score"] * 0.15,
    ]
    composite = sum(scores)

    return {
        "macd": macd,
        "atr": atr,
        "kdj": kdj,
        "obv": obv,
        "vwap": vwap,
        "ma_alignment": ma,
        "ichimoku": ichimoku,
        "composite_score": round(composite, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# RSI (Relative Strength Index) — 独立指标
# ═══════════════════════════════════════════════════════════════════════

def calc_rsi(
    close: pd.Series,
    period: int = 14,
) -> dict:
    """计算 RSI 指标.

    Returns:
        dict: {
            "rsi": float,          # 当前 RSI 值
            "zone": str,           # "oversold" | "neutral" | "overbought"
            "divergence": str,     # "bullish" | "bearish" | "none"
            "score": float,        # 0-100 评分
        }
    """
    if len(close) < period + 10:
        return {"rsi": 50, "zone": "neutral", "divergence": "none", "score": 50}

    delta = close.diff()
    gain = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi_val = float(rsi.iloc[-1])

    # 区间
    if rsi_val < 30:
        zone = "oversold"
    elif rsi_val > 70:
        zone = "overbought"
    else:
        zone = "neutral"

    # RSI 背离检测 (简化版)
    divergence = "none"
    lookback = min(20, len(close) - 1)
    if lookback >= 10:
        price_high = float(close.iloc[-lookback:].max())
        rsi_high = float(rsi.iloc[-lookback:].max())
        price_low = float(close.iloc[-lookback:].min())
        rsi_low = float(rsi.iloc[-lookback:].min())
        # 顶背离: 价格新高但 RSI 未新高
        if float(close.iloc[-1]) >= price_high * 0.98 and rsi_val < rsi_high * 0.9:
            divergence = "bearish"
        # 底背离: 价格新低但 RSI 未新低
        elif float(close.iloc[-1]) <= price_low * 1.02 and rsi_val > rsi_low * 1.1:
            divergence = "bullish"

    # 评分
    score = 50.0
    if rsi_val < 30:
        score = 70 + (30 - rsi_val) * 0.5
    elif rsi_val < 40:
        score = 60.0
    elif rsi_val > 70:
        score = 30 - (rsi_val - 70) * 0.5
    elif rsi_val > 60:
        score = 40
    if divergence == "bullish":
        score += 10
    elif divergence == "bearish":
        score -= 10

    return {
        "rsi": round(rsi_val, 1),
        "zone": zone,
        "divergence": divergence,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# Bollinger Bands — 独立指标
# ═══════════════════════════════════════════════════════════════════════

def calc_bollinger(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> dict:
    """计算布林带指标.

    Returns:
        dict: {
            "upper": float,       # 上轨
            "lower": float,       # 下轨
            "middle": float,      # 中轨
            "pct_b": float,       # %B (价格在带内位置)
            "bandwidth": float,   # 带宽
            "squeeze": bool,      # 是否处于挤压状态
            "score": float,       # 0-100 评分
        }
    """
    if len(close) < period + 5:
        return {"upper": 0, "lower": 0, "middle": 0, "pct_b": 0.5,
                "bandwidth": 0, "squeeze": False, "score": 50}

    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std

    price = float(close.iloc[-1])
    upper_val = float(upper.iloc[-1])
    lower_val = float(lower.iloc[-1])
    middle_val = float(sma.iloc[-1])

    # %B: 价格在布林带内的位置 (0=下轨, 1=上轨)
    band_range = upper_val - lower_val
    pct_b = (price - lower_val) / band_range if band_range > 0 else 0.5

    # 带宽
    bandwidth = band_range / middle_val if middle_val > 0 else 0

    # 挤压: 带宽在近 120 日的 20% 分位以下
    bw_series = (upper - lower) / sma
    lookback = min(120, len(bw_series) - 1)
    bw_window = bw_series.iloc[-lookback:].dropna()
    squeeze = bool(bandwidth < float(bw_window.quantile(0.2))) if len(bw_window) >= 20 else False

    # 评分
    score = 50.0
    if pct_b < 0.0:
        score = 70  # 跌破下轨, 超卖
    elif pct_b < 0.2:
        score = 65  # 接近下轨
    elif pct_b > 1.0:
        score = 30  # 突破上轨, 超买
    elif pct_b > 0.8:
        score = 35.0  # 接近上轨
    if squeeze:
        score += 5  # 挤压后可能突破

    return {
        "upper": round(upper_val, 2),
        "lower": round(lower_val, 2),
        "middle": round(middle_val, 2),
        "pct_b": round(pct_b, 3),
        "bandwidth": round(bandwidth, 4),
        "squeeze": squeeze,
        "score": round(max(0, min(100, score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# ADX (Average Directional Index) — 独立指标
# ═══════════════════════════════════════════════════════════════════════

def calc_adx(
    df: pd.DataFrame,
    period: int = 14,
) -> dict:
    """计算 ADX 指标.

    Returns:
        dict: {
            "adx": float,          # ADX 值
            "plus_di": float,      # +DI
            "minus_di": float,     # -DI
            "trend_strength": str, # "strong" | "moderate" | "weak"
            "direction": str,      # "bullish" | "bearish" | "neutral"
            "score": float,        # 0-100 评分
        }
    """
    if len(df) < period * 2 + 5:
        return {"adx": 0, "plus_di": 0, "minus_di": 0,
                "trend_strength": "weak", "direction": "neutral", "score": 50}

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # True Range
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    # Directional Movement
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    # Smoothed
    atr = tr.rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(period).mean() / atr.replace(0, np.nan)

    # DX and ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()

    adx_val = float(adx.iloc[-1]) if len(adx.dropna()) > 0 else 0
    plus_di_val = float(plus_di.iloc[-1]) if len(plus_di.dropna()) > 0 else 0
    minus_di_val = float(minus_di.iloc[-1]) if len(minus_di.dropna()) > 0 else 0

    # 趋势强度
    if adx_val >= 40:
        trend_strength = "strong"
    elif adx_val >= 25:
        trend_strength = "moderate"
    else:
        trend_strength = "weak"

    # 方向
    if plus_di_val > minus_di_val:
        direction = "bullish"
    elif minus_di_val > plus_di_val:
        direction = "bearish"
    else:
        direction = "neutral"

    # 评分
    score = 50.0
    if direction == "bullish" and trend_strength in ("strong", "moderate"):
        score = 65 + min(adx_val / 4, 20)
    elif direction == "bearish" and trend_strength in ("strong", "moderate"):
        score = 35 - min(adx_val / 4, 20)
    elif trend_strength == "weak":
        score = 50  # 无趋势

    return {
        "adx": round(adx_val, 1),
        "plus_di": round(plus_di_val, 1),
        "minus_di": round(minus_di_val, 1),
        "trend_strength": trend_strength,
        "direction": direction,
        "score": round(max(0, min(100, score)), 1),
    }
