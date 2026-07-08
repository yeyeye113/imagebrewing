"""模块6: CostModel — 成本模型 + 期望值适配器。

只读展示: 手续费、滑点、冲击成本估计；毛期望、成本、净期望。
净期望为负时必须提示风险。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def analyze(
    prices: pd.DataFrame,
    symbol: str = "",
    commission_rate: float = 0.00005,  # 万0.5（期货默认）
    slippage_bps: float = 2.0,         # 2个基点
    impact_model: str = "sqrt",        # sqrt | linear
    **kwargs,
) -> dict:
    """计算交易成本和净期望值。

    Args:
        prices: OHLCV DataFrame
        symbol: 品种代码
        commission_rate: 手续费率（单边）
        slippage_bps: 滑点基点数
        impact_model: 冲击成本模型 (sqrt=平方根, linear=线性)

    Returns:
        dict: 成本和期望值展示数据
    """
    if prices is None or len(prices) < 20:
        return _empty(symbol, "数据不足")

    closes = prices["close"].astype(float)
    highs = prices["high"].astype(float) if "high" in prices.columns else closes
    lows = prices["low"].astype(float) if "low" in prices.columns else closes
    volumes = prices["volume"].astype(float) if "volume" in prices.columns else pd.Series(0, index=prices.index)

    last_price = float(closes.iloc[-1])
    if last_price <= 0:
        return _empty(symbol, "价格异常")

    # ── 成本计算 ──

    # 1. 手续费（双边: 开仓 + 平仓）
    commission = last_price * commission_rate * 2

    # 2. 滑点（基于ATR估算）
    atr = _compute_atr(highs, lows, closes, period=14)
    slippage = last_price * slippage_bps / 10000

    # 3. 冲击成本（基于成交量估算）
    avg_volume = float(volumes.tail(20).mean()) if len(volumes) >= 20 else 0
    if avg_volume > 0 and impact_model == "sqrt":
        # 平方根模型: impact = spread * sqrt(order_size / ADV)
        # 假设单笔下单量为 ADV 的 1%
        participation = 0.01
        impact = last_price * 0.001 * np.sqrt(participation)  # 简化
    elif avg_volume > 0:
        impact = last_price * 0.001 * 0.01  # 线性模型
    else:
        impact = last_price * 0.0005  # 默认 0.05%

    total_cost = commission + slippage + impact

    # ── 期望值计算 ──

    # 毛期望: 基于近期平均波动率估算潜在收益
    recent_returns = closes.pct_change().dropna().tail(20)
    avg_daily_move = float(recent_returns.abs().mean()) if len(recent_returns) > 0 else 0.01
    # 假设持仓 3 天，方向正确时的平均收益
    gross_expectation = avg_daily_move * 3 * last_price * 0.55  # 55% 胜率假设

    # 净期望
    net_expectation = gross_expectation - total_cost
    is_negative = net_expectation < 0

    # 盈亏比
    risk_reward = gross_expectation / total_cost if total_cost > 0 else 0

    # 风险提示
    risk_warning = None
    if is_negative:
        risk_warning = f"净期望为负 ({net_expectation:.2f})，即使胜率较高也可能亏损"
    elif risk_reward < 2:
        risk_warning = f"盈亏比偏低 ({risk_reward:.1f}:1)，建议 >2:1"

    return {
        "symbol": symbol,
        "costs": {
            "commission": round(commission, 4),
            "slippage": round(slippage, 4),
            "impact": round(impact, 4),
            "total": round(total_cost, 4),
            "total_pct": round(total_cost / last_price * 100, 4),  # 占价格百分比
        },
        "expectation": {
            "gross": round(gross_expectation, 4),
            "cost": round(total_cost, 4),
            "net": round(net_expectation, 4),
            "is_negative": is_negative,
        },
        "risk_reward_ratio": round(risk_reward, 2),
        "risk_warning": risk_warning,
        "params": {
            "commission_rate": commission_rate,
            "slippage_bps": slippage_bps,
            "impact_model": impact_model,
            "last_price": round(last_price, 2),
            "atr_14": round(atr, 2),
        },
        "strategy_impact": "none",
    }


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "costs": {"commission": 0, "slippage": 0, "impact": 0, "total": 0, "total_pct": 0},
        "expectation": {"gross": 0, "cost": 0, "net": 0, "is_negative": True},
        "risk_reward_ratio": 0,
        "risk_warning": reason,
        "params": {},
        "strategy_impact": "none",
    }


def _compute_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    tr1 = highs - lows
    tr2 = (highs - closes.shift(1)).abs()
    tr3 = (lows - closes.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else 0.0
