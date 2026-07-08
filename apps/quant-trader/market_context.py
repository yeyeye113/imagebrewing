"""市场嗅觉模块 — 感知市场环境, 动态调整策略权重.

核心能力:
  - 市场状态判断 (牛市/熊市/震荡)
  - 板块轮动检测
  - 市场情绪分析
  - 季节性/日历效应
  - 宏观环境因子
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

import numpy as np
import pandas as pd


class MarketRegime(str, Enum):
    BULL = "牛市"
    BEAR = "熊市"
    SIDEWAYS = "震荡"
    VOLATILE = "高波动"


class SentimentLevel(str, Enum):
    EXTREME_FEAR = "极度恐慌"
    FEAR = "恐慌"
    NEUTRAL = "中性"
    GREED = "贪婪"
    EXTREME_GREED = "极度贪婪"


@dataclass
class MarketContext:
    """市场环境上下文."""
    regime: MarketRegime
    regime_confidence: float      # 0-1
    sentiment: SentimentLevel
    sentiment_score: float        # 0-100 (0=极度恐慌, 100=极度贪婪)
    sector_rotation: str          # 当前领涨板块
    seasonal_bias: str            # 季节性倾向
    macro_factors: dict           # 宏观因子
    recommended_weights: dict     # 推荐因子权重
    warnings: list[str]
    opportunities: list[str]


# ═══════════════════════════════════════════════════════════════════════
# 市场状态判断
# ═══════════════════════════════════════════════════════════════════════

def detect_market_regime(
    index_prices: pd.DataFrame,
    lookback: int = 60,
) -> tuple[MarketRegime, float, dict]:
    """判断市场状态 (牛/熊/震荡/高波动).

    使用多个指标综合判断:
      - 趋势: MA20/MA60/MA120 排列
      - 动量: 近20/60日收益
      - 波动率: ATR分位
      - 宽度: 涨跌比 (如果有数据)
    """
    if index_prices is None or len(index_prices) < lookback:
        return MarketRegime.SIDEWAYS, 0.5, {}

    close = index_prices["close"]
    price = float(close.iloc[-1])

    # 趋势指标
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else ma20
    ma120 = float(close.rolling(120).mean().iloc[-1]) if len(close) >= 120 else ma60

    trend_bull = price > ma20 > ma60 > ma120
    trend_bear = price < ma20 < ma60 < ma120

    # 动量指标
    ret_20 = float(close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0
    ret_60 = float(close.iloc[-1] / close.iloc[-60] - 1) if len(close) >= 60 else 0

    # 波动率
    returns = close.pct_change().dropna()
    vol_20 = float(returns.iloc[-20:].std()) if len(returns) >= 20 else 0.02
    vol_60 = float(returns.iloc[-60:].std()) if len(returns) >= 60 else 0.02
    vol_ratio = vol_20 / vol_60 if vol_60 > 0 else 1

    # 判断
    signals = {
        "trend": 1 if trend_bull else (-1 if trend_bear else 0),
        "momentum_20": 1 if ret_20 > 0.03 else (-1 if ret_20 < -0.03 else 0),
        "momentum_60": 1 if ret_60 > 0.08 else (-1 if ret_60 < -0.08 else 0),
        "volatility": -1 if vol_ratio > 1.5 else (1 if vol_ratio < 0.7 else 0),
    }

    score = sum(signals.values())

    if score >= 2:
        regime = MarketRegime.BULL
        confidence = min(0.5 + score * 0.15, 0.95)
    elif score <= -2:
        regime = MarketRegime.BEAR
        confidence = min(0.5 + abs(score) * 0.15, 0.95)
    elif vol_ratio > 1.5:
        regime = MarketRegime.VOLATILE
        confidence = 0.6
    else:
        regime = MarketRegime.SIDEWAYS
        confidence = 0.5

    details = {
        "price": price,
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "ma120": round(ma120, 2),
        "ret_20d": round(ret_20 * 100, 2),
        "ret_60d": round(ret_60 * 100, 2),
        "vol_20d": round(vol_20 * 100, 2),
        "vol_ratio": round(vol_ratio, 2),
        "signals": signals,
        "score": score,
    }

    return regime, confidence, details


# ═══════════════════════════════════════════════════════════════════════
# 市场情绪分析
# ═══════════════════════════════════════════════════════════════════════

def analyze_sentiment(
    index_prices: pd.DataFrame,
    volume_data: pd.Series | None = None,
    advance_decline: float | None = None,
) -> tuple[SentimentLevel, float]:
    """分析市场情绪.

    使用指标:
      - RSI (超买超卖)
      - 涨跌幅分布
      - 成交量变化
      - 涨跌比 (如果有)
    """
    if index_prices is None or len(index_prices) < 20:
        return SentimentLevel.NEUTRAL, 50

    close = index_prices["close"]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = float((100 - 100 / (1 + rs)).iloc[-1]) if len(rs) > 14 else 50

    # 涨跌幅分布 (近20日)
    returns = close.pct_change().iloc[-20:]
    up_days = (returns > 0).sum()
    down_days = (returns < 0).sum()

    # 成交量情绪
    vol_score = 50
    if volume_data is not None and len(volume_data) >= 20:
        vol_recent = float(volume_data.iloc[-5:].mean())
        vol_avg = float(volume_data.iloc[-20:].mean())
        if vol_avg > 0:
            vol_ratio = vol_recent / vol_avg
            if vol_ratio > 1.5:
                vol_score = 70  # 放量
            elif vol_ratio < 0.7:
                vol_score = 30  # 缩量

    # 综合情绪分数
    sentiment_score = (
        rsi * 0.4 +
        (up_days / 20 * 100) * 0.3 +
        vol_score * 0.2 +
        (50 + (advance_decline or 0) * 25) * 0.1
    )

    # 情绪等级
    if sentiment_score >= 80:
        level = SentimentLevel.EXTREME_GREED
    elif sentiment_score >= 65:
        level = SentimentLevel.GREED
    elif sentiment_score >= 45:
        level = SentimentLevel.NEUTRAL
    elif sentiment_score >= 30:
        level = SentimentLevel.FEAR
    else:
        level = SentimentLevel.EXTREME_FEAR

    return level, round(sentiment_score, 1)


# ═══════════════════════════════════════════════════════════════════════
# 板块轮动检测
# ═══════════════════════════════════════════════════════════════════════

def detect_sector_rotation(
    sector_performance: dict[str, float],
) -> tuple[str, list[str], list[str]]:
    """检测板块轮动.

    Args:
        sector_performance: {板块名: 近期收益率}

    Returns:
        (领涨板块, 强势板块列表, 弱势板块列表)
    """
    if not sector_performance:
        return "未知", [], []

    # 按收益排序
    sorted_sectors = sorted(sector_performance.items(), key=lambda x: x[1], reverse=True)

    # 领涨
    leader = sorted_sectors[0][0]

    # 强势 (前30%)
    n_strong = max(1, len(sorted_sectors) // 3)
    strong = [s[0] for s in sorted_sectors[:n_strong]]

    # 弱势 (后30%)
    weak = [s[0] for s in sorted_sectors[-n_strong:]]

    return leader, strong, weak


# ═══════════════════════════════════════════════════════════════════════
# 季节性分析
# ═══════════════════════════════════════════════════════════════════════

def seasonal_analysis(current_date: date | None = None) -> dict:
    """分析季节性效应.

    基于历史统计的A股季节性规律:
      - 1月: 春季躁动
      - 3-4月: 年报行情
      - 5月: Sell in May
      - 9-10月: 秋季行情
      - 12月: 年末资金紧张
    """
    d = current_date or date.today()
    month = d.month

    patterns = {
        1: {"bias": "偏多", "desc": "春季躁动, 资金回流", "strength": 0.6},
        2: {"bias": "偏多", "desc": "春节后资金宽松", "strength": 0.5},
        3: {"bias": "偏多", "desc": "年报预期, 政策窗口", "strength": 0.7},
        4: {"bias": "偏多", "desc": "年报兑现, 一季报", "strength": 0.6},
        5: {"bias": "偏空", "desc": "Sell in May, 资金收紧", "strength": -0.4},
        6: {"bias": "中性", "desc": "半年末资金紧张", "strength": -0.2},
        7: {"bias": "偏多", "desc": "三季度行情启动", "strength": 0.4},
        8: {"bias": "中性", "desc": "中报期, 分化", "strength": 0.1},
        9: {"bias": "偏空", "desc": "秋季调整, 资金回笼", "strength": -0.3},
        10: {"bias": "偏多", "desc": "四季度行情, 政策预期", "strength": 0.5},
        11: {"bias": "偏多", "desc": "年末布局", "strength": 0.3},
        12: {"bias": "偏空", "desc": "年末资金紧张, 调仓", "strength": -0.3},
    }

    return patterns.get(month, {"bias": "中性", "desc": "无明显规律", "strength": 0})


# ═══════════════════════════════════════════════════════════════════════
# 动态因子权重调整
# ═══════════════════════════════════════════════════════════════════════

def adjust_factor_weights(
    regime: MarketRegime,
    sentiment: SentimentLevel,
    seasonal_bias: str,
) -> dict[str, float]:
    """根据市场环境动态调整因子权重.

    牛市: 动量权重提高
    熊市: 均值回归权重提高, 波动率权重提高
    震荡: 趋势权重降低, 均值回归权重提高
    """
    # 基础权重
    weights = {
        "动量": 0.25,
        "波动率": 0.15,
        "成交量": 0.15,
        "趋势": 0.25,
        "均值回归": 0.20,
    }

    # 市场状态调整
    if regime == MarketRegime.BULL:
        weights["动量"] += 0.10
        weights["趋势"] += 0.05
        weights["均值回归"] -= 0.10
        weights["波动率"] -= 0.05
    elif regime == MarketRegime.BEAR:
        weights["均值回归"] += 0.10
        weights["波动率"] += 0.10
        weights["动量"] -= 0.10
        weights["趋势"] -= 0.10
    elif regime == MarketRegime.VOLATILE:
        weights["波动率"] += 0.15
        weights["均值回归"] += 0.05
        weights["动量"] -= 0.10
        weights["趋势"] -= 0.10

    # 情绪调整
    if sentiment in (SentimentLevel.EXTREME_GREED, SentimentLevel.GREED):
        weights["均值回归"] += 0.05
        weights["动量"] -= 0.05
    elif sentiment in (SentimentLevel.EXTREME_FEAR, SentimentLevel.FEAR):
        weights["动量"] += 0.05
        weights["均值回归"] -= 0.05

    # 季节性调整
    if seasonal_bias == "偏多":
        weights["动量"] += 0.03
        weights["趋势"] += 0.02
    elif seasonal_bias == "偏空":
        weights["波动率"] += 0.03
        weights["均值回归"] += 0.02

    # 归一化
    total = sum(weights.values())
    weights = {k: round(v / total, 3) for k, v in weights.items()}

    return weights


# ═══════════════════════════════════════════════════════════════════════
# 宏观因子
# ═══════════════════════════════════════════════════════════════════════

def estimate_macro_factors() -> dict:
    """估算当前宏观因子 (简化版).

    实际应用中应接入:
      - 央行利率决议
      - CPI/PPI 数据
      - PMI 指数
      - 社融数据
      - 北向资金
    """
    # 这里用简化逻辑
    return {
        "rate_env": "宽松",      # 宽松/中性/紧缩
        "inflation": "温和",     # 通缩/温和/高通胀
        "growth": "复苏",       # 衰退/筑底/复苏/过热
        "liquidity": "充裕",    # 紧张/中性/充裕
        "policy": "支持",       # 收紧/中性/支持
    }


# ═══════════════════════════════════════════════════════════════════════
# 综合市场上下文
# ═══════════════════════════════════════════════════════════════════════

def build_market_context(
    index_prices: pd.DataFrame | None = None,
    sector_performance: dict[str, float] | None = None,
    volume_data: pd.Series | None = None,
) -> MarketContext:
    """构建完整的市场环境上下文."""
    warnings = []
    opportunities = []

    # 市场状态
    if index_prices is not None and len(index_prices) >= 60:
        regime, confidence, regime_details = detect_market_regime(index_prices)
    else:
        regime, confidence = MarketRegime.SIDEWAYS, 0.5
        regime_details = {}

    # 市场情绪
    sentiment, sentiment_score = analyze_sentiment(index_prices, volume_data)

    # 板块轮动
    if sector_performance:
        leader, strong, weak = detect_sector_rotation(sector_performance)
    else:
        leader, strong, weak = "未知", [], []

    # 季节性
    seasonal = seasonal_analysis()

    # 宏观因子
    macro = estimate_macro_factors()

    # 动态权重
    weights = adjust_factor_weights(regime, sentiment, seasonal["bias"])

    # 生成警告和机会
    if regime == MarketRegime.BEAR:
        warnings.append("市场处于熊市, 控制仓位, 优先防守")
    if regime == MarketRegime.VOLATILE:
        warnings.append("市场波动加剧, 降低仓位, 收紧止损")
    if sentiment in (SentimentLevel.EXTREME_GREED,):
        warnings.append("市场极度贪婪, 注意回调风险")
    if sentiment in (SentimentLevel.EXTREME_FEAR,):
        opportunities.append("市场极度恐慌, 可能是抄底机会")
    if seasonal["bias"] == "偏空":
        warnings.append(f"季节性偏空: {seasonal['desc']}")
    if seasonal["bias"] == "偏多":
        opportunities.append(f"季节性偏多: {seasonal['desc']}")
    if strong:
        opportunities.append(f"强势板块: {', '.join(strong[:3])}")

    return MarketContext(
        regime=regime,
        regime_confidence=confidence,
        sentiment=sentiment,
        sentiment_score=sentiment_score,
        sector_rotation=leader,
        seasonal_bias=seasonal["bias"],
        macro_factors=macro,
        recommended_weights=weights,
        warnings=warnings,
        opportunities=opportunities,
    )


def format_market_context(ctx: MarketContext) -> str:
    """格式化市场上下文."""
    lines = [
        "=== 市场环境分析 ===",
        f"市场状态: {ctx.regime.value} (置信度 {ctx.regime_confidence:.0%})",
        f"市场情绪: {ctx.sentiment.value} ({ctx.sentiment_score:.0f}/100)",
        f"季节性: {ctx.seasonal_bias}",
        f"领涨板块: {ctx.sector_rotation}",
        "",
        "推荐因子权重:",
    ]
    for k, v in ctx.recommended_weights.items():
        lines.append(f"  {k}: {v:.1%}")

    if ctx.warnings:
        lines.append("")
        lines.append("风险提示:")
        for w in ctx.warnings:
            lines.append(f"  {w}")

    if ctx.opportunities:
        lines.append("")
        lines.append("机会提示:")
        for o in ctx.opportunities:
            lines.append(f"  {o}")

    return "\n".join(lines)
