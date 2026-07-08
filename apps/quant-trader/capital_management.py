"""资金管理优化模块 — 凯利公式等仓位管理.

核心原理:
  1. 凯利公式: f = (bp - q) / b
  2. 固定比例法: 每次交易固定比例
  3. 动态仓位: 根据信号强度调整
  4. 风险预算: 控制总风险暴露
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .log import get_logger

logger = get_logger("capital_management")


@dataclass
class PositionSize:
    """仓位大小计算结果."""
    method: str              # 计算方法
    position_pct: float      # 仓位百分比 (0-1)
    position_amount: float   # 仓位金额
    risk_per_trade: float    # 每笔交易风险
    max_loss: float          # 最大亏损
    reason: str              # 计算原因


def kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.5,
) -> float:
    """凯利公式计算最优仓位.

    Args:
        win_rate: 胜率 (0-1)
        avg_win: 平均盈利 (正数)
        avg_loss: 平均亏损 (正数)
        fraction: 凯利分数 (0.5 = 半凯利)

    Returns:
        float: 最优仓位比例 (0-1)
    """
    if avg_loss == 0 or win_rate == 0:
        return 0.0

    # 计算赔率
    odds = avg_win / avg_loss

    # 凯利公式: f = (bp - q) / b
    # b = 赔率, p = 胜率, q = 败率
    q = 1 - win_rate
    kelly = (odds * win_rate - q) / odds

    # 使用半凯利降低风险
    kelly = kelly * fraction

    # 限制范围
    kelly = max(0.0, min(0.25, kelly))

    return kelly


def fixed_ratio_position(
    capital: float,
    risk_per_trade: float = 0.02,
    stop_loss_pct: float = 0.05,
) -> float:
    """固定比例法计算仓位.

    Args:
        capital: 总资金
        risk_per_trade: 每笔交易风险 (占总资金比例)
        stop_loss_pct: 止损百分比

    Returns:
        float: 仓位金额
    """
    # 每笔交易最大亏损
    max_loss = capital * risk_per_trade

    # 仓位金额 = 最大亏损 / 止损百分比
    position_amount = max_loss / stop_loss_pct if stop_loss_pct > 0 else 0

    # 仓位比例
    position_pct = position_amount / capital if capital > 0 else 0

    # 限制范围
    position_pct = max(0.0, min(0.25, position_pct))

    return position_pct


def dynamic_position_size(
    confidence: float,
    volatility: float,
    base_position: float = 0.10,
) -> float:
    """动态仓位大小.

    Args:
        confidence: 置信度 (0-100)
        volatility: 波动率
        base_position: 基础仓位

    Returns:
        float: 仓位比例
    """
    # 置信度调整
    if confidence >= 90:
        conf_multiplier = 1.5
    elif confidence >= 80:
        conf_multiplier = 1.2
    elif confidence >= 70:
        conf_multiplier = 1.0
    elif confidence >= 60:
        conf_multiplier = 0.8
    else:
        conf_multiplier = 0.5

    # 波动率调整
    if volatility > 0.03:
        vol_multiplier = 0.5  # 高波动减仓
    elif volatility > 0.02:
        vol_multiplier = 0.8
    elif volatility < 0.01:
        vol_multiplier = 1.3  # 低波动加仓
    else:
        vol_multiplier = 1.0

    # 计算仓位
    position = base_position * conf_multiplier * vol_multiplier

    # 限制范围
    position = max(0.05, min(0.25, position))

    return position


def calculate_position_size(
    capital: float,
    entry_price: float,
    stop_loss_price: float,
    confidence: float,
    win_rate: float = 0.5,
    avg_win: float = 0.05,
    avg_loss: float = 0.03,
    method: str = "kelly",
) -> PositionSize:
    """计算仓位大小.

    Args:
        capital: 总资金
        entry_price: 入场价
        stop_loss_price: 止损价
        confidence: 置信度
        win_rate: 胜率
        avg_win: 平均盈利
        avg_loss: 平均亏损
        method: 计算方法 ("kelly" | "fixed" | "dynamic")

    Returns:
        PositionSize: 仓位计算结果
    """
    # 计算止损百分比
    stop_loss_pct = abs(entry_price - stop_loss_price) / entry_price if entry_price > 0 else 0.05

    # 根据方法计算仓位
    if method == "kelly":
        position_pct = kelly_criterion(win_rate, avg_win, avg_loss)
        reason = f"凯利公式: 胜率={win_rate:.0%} 赔率={avg_win/avg_loss:.1f}"
    elif method == "fixed":
        position_pct = fixed_ratio_position(capital, risk_per_trade=0.02, stop_loss_pct=stop_loss_pct)
        reason = f"固定比例: 风险=2% 止损={stop_loss_pct:.1%}"
    elif method == "dynamic":
        volatility = stop_loss_pct  # 用止损百分比近似波动率
        position_pct = dynamic_position_size(confidence, volatility)
        reason = f"动态仓位: 置信度={confidence:.0f}% 波动率={volatility:.1%}"
    else:
        position_pct = 0.10
        reason = "默认仓位 10%"

    # 计算仓位金额
    position_amount = capital * position_pct

    # 计算每笔交易风险
    risk_per_trade = position_amount * stop_loss_pct

    # 计算最大亏损
    max_loss = risk_per_trade

    return PositionSize(
        method=method,
        position_pct=round(position_pct, 4),
        position_amount=round(position_amount, 2),
        risk_per_trade=round(risk_per_trade, 2),
        max_loss=round(max_loss, 2),
        reason=reason,
    )


def calculate_portfolio_risk(
    positions: list[dict],
    capital: float,
) -> dict:
    """计算组合风险.

    Args:
        positions: 持仓列表 [{"symbol": str, "position_pct": float, "stop_loss_pct": float}]
        capital: 总资金

    Returns:
        dict: {
            "total_exposure": float,
            "total_risk": float,
            "max_loss": float,
            "risk_per_trade": float,
            "diversification_score": float,
        }
    """
    if not positions:
        return {
            "total_exposure": 0,
            "total_risk": 0,
            "max_loss": 0,
            "risk_per_trade": 0,
            "diversification_score": 100,
        }

    # 计算总暴露
    total_exposure = sum(p.get("position_pct", 0) for p in positions)

    # 计算总风险
    total_risk = sum(
        p.get("position_pct", 0) * p.get("stop_loss_pct", 0.05)
        for p in positions
    )

    # 计算最大亏损
    max_loss = total_risk * capital

    # 计算每笔交易风险
    risk_per_trade = total_risk / len(positions) if positions else 0

    # 计算分散化分数
    # 理想情况: 每个持仓占比相近
    if len(positions) > 1:
        avg_position = total_exposure / len(positions)
        position_std = np.std([p.get("position_pct", 0) for p in positions])
        diversification_score = max(0, 100 - position_std * 1000)
    else:
        diversification_score = 50

    return {
        "total_exposure": round(total_exposure, 4),
        "total_risk": round(total_risk, 4),
        "max_loss": round(max_loss, 2),
        "risk_per_trade": round(risk_per_trade, 4),
        "diversification_score": round(diversification_score, 1),
    }


def get_optimal_position(
    capital: float,
    entry_price: float,
    stop_loss_price: float,
    confidence: float,
    method: str = "kelly",
) -> dict:
    """获取最优仓位.

    Args:
        capital: 总资金
        entry_price: 入场价
        stop_loss_price: 止损价
        confidence: 置信度
        method: 计算方法

    Returns:
        dict: {
            "position_pct": float,
            "position_amount": float,
            "risk_per_trade": float,
            "max_loss": float,
            "reason": str,
        }
    """
    # 计算仓位
    position = calculate_position_size(
        capital=capital,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        confidence=confidence,
        method=method,
    )

    return {
        "position_pct": position.position_pct,
        "position_amount": position.position_amount,
        "risk_per_trade": position.risk_per_trade,
        "max_loss": position.max_loss,
        "reason": position.reason,
    }
