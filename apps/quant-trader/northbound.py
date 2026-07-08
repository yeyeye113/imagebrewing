"""北向资金数据模块 — 沪股通/深股通资金流向分析.

提供:
  - 北向资金历史流向
  - 北向资金情绪指标
  - 北向资金与个股关联分析
"""
from __future__ import annotations

import time

import pandas as pd

from .log import get_logger

logger = get_logger("northbound")

# 数据缓存
_NORTHBOUND_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL_S = 3600  # 1 小时缓存


def get_northbound_flow(
    symbol: str = "沪股通",
    days: int = 30,
) -> pd.DataFrame | None:
    """获取北向资金流向数据.

    Args:
        symbol: '沪股通' 或 '深股通'
        days: 获取天数

    Returns:
        pd.DataFrame: 北向资金流向数据
    """
    cache_key = f"{symbol}_{days}"

    # 检查缓存
    if cache_key in _NORTHBOUND_CACHE:
        ts, df = _NORTHBOUND_CACHE[cache_key]
        if time.time() - ts < _CACHE_TTL_S:
            return df

    try:
        import akshare as ak

        df = ak.stock_hsgt_hist_em(symbol=symbol)

        if df is None or df.empty:
            return None

        # 取最近 N 天
        df = df.tail(days).copy()

        # 转换日期
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.set_index('日期').sort_index()

        # 更新缓存
        _NORTHBOUND_CACHE[cache_key] = (time.time(), df)

        return df
    except Exception as e:
        logger.warning("获取北向资金数据失败 %s: %s", symbol, e)
        return None


def get_northbound_sentiment(days: int = 30) -> dict:
    """获取北向资金情绪指标.

    Returns:
        dict: {
            "net_flow_7d": float,      # 7日净流入 (亿元)
            "net_flow_30d": float,     # 30日净流入 (亿元)
            "flow_trend": str,         # "inflow" | "outflow" | "neutral"
            "sentiment": str,          # "bullish" | "bearish" | "neutral"
            "sentiment_score": float,  # 0-100 情绪分
        }
    """
    try:
        # 获取沪股通和深股通数据
        sh_flow = get_northbound_flow("沪股通", days)
        sz_flow = get_northbound_flow("深股通", days)

        if sh_flow is None and sz_flow is None:
            return {
                "net_flow_7d": 0,
                "net_flow_30d": 0,
                "flow_trend": "neutral",
                "sentiment": "neutral",
                "sentiment_score": 50,
            }

        # 合并数据
        total_flow = pd.DataFrame()

        if sh_flow is not None and '当日资金流入' in sh_flow.columns:
            total_flow['sh'] = sh_flow['当日资金流入']
        if sz_flow is not None and '当日资金流入' in sz_flow.columns:
            total_flow['sz'] = sz_flow['当日资金流入']

        if total_flow.empty:
            return {
                "net_flow_7d": 0,
                "net_flow_30d": 0,
                "flow_trend": "neutral",
                "sentiment": "neutral",
                "sentiment_score": 50,
            }

        # 计算总流入
        total_flow['total'] = total_flow.sum(axis=1)
        total_flow = total_flow.dropna(subset=['total'])

        if total_flow.empty:
            return {
                "net_flow_7d": 0,
                "net_flow_30d": 0,
                "flow_trend": "neutral",
                "sentiment": "neutral",
                "sentiment_score": 50,
            }

        # 计算 7 日和 30 日净流入
        net_flow_7d = float(total_flow['total'].iloc[-7:].sum()) if len(total_flow) >= 7 else 0
        net_flow_30d = float(total_flow['total'].iloc[-30:].sum()) if len(total_flow) >= 30 else 0

        # 判断流向趋势
        recent_7d = total_flow['total'].iloc[-7:] if len(total_flow) >= 7 else total_flow['total']
        positive_days = (recent_7d > 0).sum()

        if positive_days >= 5:
            flow_trend = "inflow"
        elif positive_days <= 2:
            flow_trend = "outflow"
        else:
            flow_trend = "neutral"

        # 计算情绪分
        sentiment_score = 50

        # 7 日净流入影响
        if net_flow_7d > 100:
            sentiment_score += 20
        elif net_flow_7d > 50:
            sentiment_score += 10
        elif net_flow_7d < -100:
            sentiment_score -= 20
        elif net_flow_7d < -50:
            sentiment_score -= 10

        # 30 日净流入影响
        if net_flow_30d > 500:
            sentiment_score += 15
        elif net_flow_30d > 200:
            sentiment_score += 8
        elif net_flow_30d < -500:
            sentiment_score -= 15
        elif net_flow_30d < -200:
            sentiment_score -= 8

        # 流向趋势影响
        if flow_trend == "inflow":
            sentiment_score += 10
        elif flow_trend == "outflow":
            sentiment_score -= 10

        sentiment_score = max(0, min(100, sentiment_score))

        # 判断情绪
        if sentiment_score >= 70:
            sentiment = "bullish"
        elif sentiment_score <= 30:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        return {
            "net_flow_7d": round(net_flow_7d, 2),
            "net_flow_30d": round(net_flow_30d, 2),
            "flow_trend": flow_trend,
            "sentiment": sentiment,
            "sentiment_score": round(sentiment_score, 1),
        }
    except Exception as e:
        logger.warning("获取北向资金情绪失败: %s", e)
        return {
            "net_flow_7d": 0,
            "net_flow_30d": 0,
            "flow_trend": "neutral",
            "sentiment": "neutral",
            "sentiment_score": 50,
        }


def get_northbound_stock_signal(symbol: str) -> dict:
    """获取个股北向资金信号.

    Args:
        symbol: 股票代码

    Returns:
        dict: {
            "signal": str,           # "BUY" | "SELL" | "HOLD"
            "confidence": float,     # 0-100 置信度
            "reason": str,           # 信号原因
        }
    """
    try:
        # 获取北向资金整体情绪
        sentiment = get_northbound_sentiment()

        # 根据整体情绪判断
        if sentiment["sentiment"] == "bullish":
            return {
                "signal": "BUY",
                "confidence": sentiment["sentiment_score"],
                "reason": f"北向资金净流入 {sentiment['net_flow_7d']:.0f}亿 (7日)",
            }
        elif sentiment["sentiment"] == "bearish":
            return {
                "signal": "SELL",
                "confidence": 100 - sentiment["sentiment_score"],
                "reason": f"北向资金净流出 {sentiment['net_flow_7d']:.0f}亿 (7日)",
            }
        else:
            return {
                "signal": "HOLD",
                "confidence": 50,
                "reason": f"北向资金中性 {sentiment['net_flow_7d']:.0f}亿 (7日)",
            }
    except Exception as e:
        logger.warning("获取个股北向资金信号失败 %s: %s", symbol, e)
        return {
            "signal": "HOLD",
            "confidence": 50,
            "reason": "数据不可用",
        }


def clear_cache():
    """清除数据缓存."""
    global _NORTHBOUND_CACHE
    _NORTHBOUND_CACHE.clear()
    logger.info("北向资金缓存已清除")
