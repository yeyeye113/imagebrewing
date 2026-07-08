"""多因子评分引擎 — 动量/波动率/成交量/趋势/均值回归.

五因子模型, 每个因子独立评分 0-100, 加权合成综合分.
可扩展: 新增因子只需实现同签名函数.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import calc_atr, calc_kdj, calc_ma_alignment, calc_macd
from .volume import calc_obv_slope, calc_volume_price_divergence, calc_volume_ratio

# ═══════════════════════════════════════════════════════════════════════
# 因子数据结构
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class FactorScore:
    """单因子评分结果."""
    name: str
    score: float          # 0-100
    weight: float         # 权重
    weighted: float       # score * weight
    signals: dict = field(default_factory=dict)   # 细分信号
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "weight": round(self.weight, 3),
            "weighted": round(self.weighted, 1),
            "signals": self.signals,
            "description": self.description,
        }


# ═══════════════════════════════════════════════════════════════════════
# 因子 1: 动量因子 (Momentum)
# ═══════════════════════════════════════════════════════════════════════

def momentum_factor(
    df: pd.DataFrame,
    periods: list[int] | None = None,
) -> FactorScore:
    """动量因子: 多周期收益率 + 加速度.

    评分逻辑:
      - 正收益加分, 负收益减分
      - 短期动量 > 长期动量 (加速) 加分
      - 连续上涨天数加分
    """
    if periods is None:
        periods = [5, 10, 20, 60]

    if df is None or len(df) < max(periods) + 1:
        return FactorScore("动量", 50, 0, 0, description="数据不足")

    close = df["close"]
    returns = {}
    for p in periods:
        if len(close) > p:
            returns[f"ret_{p}d"] = float(close.iloc[-1] / close.iloc[-p] - 1)

    # 多周期动量合成
    scores = []
    weights_list = [0.15, 0.20, 0.35, 0.30]  # 短→长权重
    for (k, ret), w in zip(returns.items(), weights_list):
        if ret > 0.1:
            s = 75 + min(ret * 100, 20)
        elif ret > 0.03:
            s = 60 + ret * 200
        elif ret > 0:
            s = 55 + ret * 100
        elif ret > -0.03:
            s = 45 + ret * 100
        else:
            s = max(25, 45 + ret * 100)
        scores.append(s * w)

    base_score = sum(scores) / sum(weights_list[:len(scores)])

    # 加速度: 短期 > 中期 → 加速 (年化比较)
    if "ret_5d" in returns and "ret_20d" in returns:
        accel = returns["ret_5d"] * 4 - returns["ret_20d"]
        if accel > 0.02:
            base_score += 5
        elif accel < -0.02:
            base_score -= 5

    # 动量衰减检测: 5d 正但小于 10d/2 → 衰减
    if "ret_5d" in returns and "ret_10d" in returns:
        if returns["ret_5d"] > 0 and returns["ret_5d"] < returns["ret_10d"] / 2:
            base_score -= 8  # 动量衰减惩罚

    # 连续上涨天数
    streak = 0
    for i in range(-1, -min(10, len(close)), -1):
        if float(close.iloc[i]) > float(close.iloc[i-1]):
            streak += 1
        else:
            break
    if streak >= 5:
        base_score += 5
    elif streak >= 3:
        base_score += 3

    return FactorScore(
        name="动量",
        score=max(0, min(100, base_score)),
        weight=0,
        weighted=0,
        signals=returns,
        description=f"{len([r for r in returns.values() if r > 0])}/{len(returns)} 周期正收益, 连涨{streak}天",
    )


# ═══════════════════════════════════════════════════════════════════════
# 因子 2: 波动率因子 (Volatility)
# ═══════════════════════════════════════════════════════════════════════

def volatility_factor(df: pd.DataFrame) -> FactorScore:
    """波动率因子: ATR分位 + 波动率趋势.

    评分逻辑:
      - 低波动环境得分高 (适合入场)
      - 波动率下降趋势加分
    """
    if df is None or len(df) < 30:
        return FactorScore("波动率", 50, 0, 0, description="数据不足")

    atr = calc_atr(df)
    close = df["close"]

    # 波动率趋势: 近5日 vs 近20日
    rets = close.pct_change().dropna()
    vol_5 = float(rets.iloc[-5:].std()) if len(rets) >= 5 else 0
    vol_20 = float(rets.iloc[-20:].std()) if len(rets) >= 20 else 0
    vol_trend = vol_5 / vol_20 if vol_20 > 0 else 1

    base_score = atr["score"]

    # 波动率收敛加分
    if vol_trend < 0.8:
        base_score += 8  # 波动率显著下降
    elif vol_trend < 0.95:
        base_score += 4
    elif vol_trend > 1.3:
        base_score -= 8  # 波动率飙升

    return FactorScore(
        name="波动率",
        score=max(0, min(100, base_score)),
        weight=0,
        weighted=0,
        signals={
            "atr_pct": atr["atr_pct"],
            "atr_percentile": atr["atr_percentile"],
            "vol_trend": round(vol_trend, 2),
            "regime": atr["volatility_regime"],
        },
        description=f"ATR分位{atr['atr_percentile']:.0f}% · {atr['volatility_regime']}波动 · 趋势{vol_trend:.2f}",
    )


# ═══════════════════════════════════════════════════════════════════════
# 因子 3: 成交量因子 (Volume)
# ═══════════════════════════════════════════════════════════════════════

def volume_factor(df: pd.DataFrame) -> FactorScore:
    """成交量因子: 量比 + OBV斜率 + 量价背离.

    评分逻辑:
      - 温和放量 + OBV流入 → 高分
      - 量价背离扣分
    """
    if df is None or len(df) < 20 or "volume" not in df.columns:
        return FactorScore("成交量", 50, 0, 0, description="数据不足")

    close = df["close"]
    volume = df["volume"]

    vr = calc_volume_ratio(volume)
    obv = calc_obv_slope(close, volume)
    vp = calc_volume_price_divergence(close, volume)

    base_score = vr["score"] * 0.35 + obv["score"] * 0.40 + vp["score"] * 0.25

    # 量价方向一致性: 放量下跌降分, 放量上涨加分
    ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0
    if vr["ratio"] > 1.3 and ret_5d < -0.02:
        base_score *= 0.7   # 放量下跌 → 降分
    elif vr["ratio"] > 1.3 and ret_5d > 0.02:
        base_score *= 1.1   # 放量上涨 → 加分

    return FactorScore(
        name="成交量",
        score=max(0, min(100, base_score)),
        weight=0,
        weighted=0,
        signals={
            "volume_ratio": vr["ratio"],
            "volume_level": vr["level"],
            "obv_direction": obv["direction"],
            "obv_strength": obv["strength"],
            "divergence": vp["divergence"],
        },
        description=f"量比{vr['ratio']:.1f}({vr['level']}) · 资金{obv['direction']}({obv['strength']}) · {vp['detail']}",
    )


# ═══════════════════════════════════════════════════════════════════════
# 因子 4: 趋势因子 (Trend)
# ═══════════════════════════════════════════════════════════════════════

def trend_factor(df: pd.DataFrame) -> FactorScore:
    """趋势因子: MACD + 均线排列 + 价格位置.

    评分逻辑:
      - 多头排列 + MACD 金叉 → 高分
      - 空头排列 + MACD 死叉 → 低分
    """
    if df is None or len(df) < 60:
        return FactorScore("趋势", 50, 0, 0, description="数据不足")

    close = df["close"]
    macd = calc_macd(close)
    ma = calc_ma_alignment(close)

    base_score = macd["score"] * 0.50 + ma["score"] * 0.50

    # MACD + 均线共振加分
    if macd["cross"] == "golden" and ma["alignment"] == "bullish":
        base_score += 10
    elif macd["cross"] == "death" and ma["alignment"] == "bearish":
        base_score -= 10

    return FactorScore(
        name="趋势",
        score=max(0, min(100, base_score)),
        weight=0,
        weighted=0,
        signals={
            "macd_cross": macd["cross"],
            "macd_divergence": macd["divergence"],
            "ma_alignment": ma["alignment"],
            "ma_above_count": f"{ma['above_count']}/{ma['total']}",
        },
        description=f"均线{ma['alignment']}({ma['above_count']}/{ma['total']}) · MACD{macd['cross']}",
    )


# ═══════════════════════════════════════════════════════════════════════
# 因子 5: 均值回归因子 (Mean Reversion)
# ═══════════════════════════════════════════════════════════════════════

def mean_reversion_factor(df: pd.DataFrame) -> FactorScore:
    """均值回归因子: RSI + KDJ + 偏离度.

    评分逻辑:
      - 超卖区间回升 → 高分 (抄底机会)
      - 超买区间 → 低分 (追高风险)
    """
    if df is None or len(df) < 30:
        return FactorScore("均值回归", 50, 0, 0, description="数据不足")

    close = df["close"]
    kdj = calc_kdj(df)

    # RSI 计算
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = float((100 - 100 / (1 + rs)).iloc[-1]) if len(rs) > 14 else 50

    # 偏离度: 价格 vs 20日均线
    ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else float(close.iloc[-1])
    price = float(close.iloc[-1])
    deviation = (price - ma20) / ma20 if ma20 > 0 else 0

    # 评分
    score = 50

    # RSI 评分
    if rsi < 30:
        score += 20  # 超卖
    elif rsi < 40:
        score += 10
    elif rsi > 70:
        score -= 20  # 超买
    elif rsi > 60:
        score -= 10

    # KDJ 评分
    score += (kdj["score"] - 50) * 0.3

    # 偏离度评分
    if deviation < -0.05:
        score += 10  # 低于均线, 有回归空间
    elif deviation > 0.05:
        score -= 5  # 高于均线, 回归风险

    return FactorScore(
        name="均值回归",
        score=max(0, min(100, score)),
        weight=0,
        weighted=0,
        signals={
            "rsi": round(rsi, 1),
            "kdj_k": kdj["k"],
            "kdj_zone": kdj["zone"],
            "ma20_deviation": round(deviation, 4),
        },
        description=f"RSI={rsi:.0f} · KDJ({kdj['zone']}) · 偏离MA20={deviation*100:+.1f}%",
    )


# ═══════════════════════════════════════════════════════════════════════
# 多因子综合评分
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_FACTOR_WEIGHTS = {
    "动量": 0.25,
    "波动率": 0.15,
    "成交量": 0.15,
    "趋势": 0.25,
    "均值回归": 0.20,
}


def multi_factor_score(
    df: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> dict:
    """多因子综合评分.

    Args:
        df: 行情数据 (需含 open/high/low/close/volume)
        weights: 因子权重, 默认等权

    Returns:
        dict: {
            "composite": float,      # 综合分 0-100
            "grade": str,            # A/B/C/D
            "signal": str,           # "强烈看多" | "偏多" | "中性" | "偏空" | "强烈看空"
            "factors": list[dict],   # 各因子详情
            "top_signals": list[str], # 关键信号
        }
    """
    w = weights or DEFAULT_FACTOR_WEIGHTS

    factors = [
        momentum_factor(df),
        volatility_factor(df),
        volume_factor(df),
        trend_factor(df),
        mean_reversion_factor(df),
    ]

    # 设置权重
    for f in factors:
        f.weight = w.get(f.name, 0.20)
        f.weighted = f.score * f.weight

    composite = sum(f.weighted for f in factors)
    composite = max(0, min(100, composite))

    # 评级
    if composite >= 75:
        grade = "A"
        signal = "强烈看多"
    elif composite >= 62:
        grade = "B"
        signal = "偏多"
    elif composite >= 45:
        grade = "C"
        signal = "中性"
    elif composite >= 30:
        grade = "D"
        signal = "偏空"
    else:
        grade = "E"
        signal = "强烈看空"

    # 关键信号提取
    top_signals = []
    for f in factors:
        if f.score >= 70:
            top_signals.append(f"✅ {f.name}: {f.description}")
        elif f.score <= 35:
            top_signals.append(f"⚠️ {f.name}: {f.description}")

    return {
        "composite": round(composite, 1),
        "grade": grade,
        "signal": signal,
        "factors": [f.to_dict() for f in factors],
        "top_signals": top_signals,
    }
