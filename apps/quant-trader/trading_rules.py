"""交易限制检查模块 — 涨跌停/停牌/交易规则检查.

功能:
  1. 涨跌停检查
  2. 停牌检查
  3. 交易时间检查
  4. 持仓限制检查
  5. 交易频率检查
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from .log import get_logger

logger = get_logger("trading_rules")


@dataclass
class TradingCheckResult:
    """交易检查结果."""
    can_trade: bool          # 是否可以交易
    reason: str              # 原因
    warnings: list[str]      # 警告


def check_price_limit(
    current_price: float,
    prev_close: float,
    limit_pct: float = 0.10,
) -> dict:
    """检查涨跌停.

    Args:
        current_price: 当前价
        prev_close: 昨收价
        limit_pct: 涨跌停幅度 (10%)

    Returns:
        dict: {
            "is_limit_up": bool,
            "is_limit_down": bool,
            "limit_up_price": float,
            "limit_down_price": float,
            "can_buy": bool,
            "can_sell": bool,
        }
    """
    if prev_close <= 0:
        return {
            "is_limit_up": False,
            "is_limit_down": False,
            "limit_up_price": 0,
            "limit_down_price": 0,
            "can_buy": True,
            "can_sell": True,
        }

    # 计算涨跌停价
    limit_up_price = round(prev_close * (1 + limit_pct), 2)
    limit_down_price = round(prev_close * (1 - limit_pct), 2)

    # 判断是否涨跌停
    is_limit_up = current_price >= limit_up_price
    is_limit_down = current_price <= limit_down_price

    # 涨停时不能买入，跌停时不能卖出
    can_buy = not is_limit_up
    can_sell = not is_limit_down

    return {
        "is_limit_up": is_limit_up,
        "is_limit_down": is_limit_down,
        "limit_up_price": limit_up_price,
        "limit_down_price": limit_down_price,
        "can_buy": can_buy,
        "can_sell": can_sell,
    }


def check_trading_time() -> dict:
    """检查交易时间.

    Returns:
        dict: {
            "is_trading_time": bool,
            "current_session": str,  # "morning" | "afternoon" | "closed"
            "next_open": str,
        }
    """
    now = datetime.now()
    current_time = now.time()

    # 交易时间
    morning_start = time(9, 30)
    morning_end = time(11, 30)
    afternoon_start = time(13, 0)
    afternoon_end = time(15, 0)

    # 判断当前时段
    if morning_start <= current_time <= morning_end:
        is_trading_time = True
        current_session = "morning"
        next_open = "13:00"
    elif afternoon_start <= current_time <= afternoon_end:
        is_trading_time = True
        current_session = "afternoon"
        next_open = "09:30 (明天)"
    else:
        is_trading_time = False
        current_session = "closed"
        if current_time < morning_start:
            next_open = "09:30"
        else:
            next_open = "09:30 (明天)"

    return {
        "is_trading_time": is_trading_time,
        "current_session": current_session,
        "next_open": next_open,
    }


def check_position_limit(
    current_position: float,
    new_order_amount: float,
    capital: float,
    max_position_pct: float = 0.25,
    max_total_exposure: float = 0.80,
) -> dict:
    """检查持仓限制.

    Args:
        current_position: 当前持仓金额
        new_order_amount: 新订单金额
        capital: 总资金
        max_position_pct: 单只股票最大持仓比例
        max_total_exposure: 最大总暴露比例

    Returns:
        dict: {
            "can_trade": bool,
            "reason": str,
            "max_allowed": float,
        }
    """
    # 计算单只股票最大持仓
    max_single_position = capital * max_position_pct

    # 计算最大总暴露
    max_total = capital * max_total_exposure

    # 检查单只股票限制
    if current_position + new_order_amount > max_single_position:
        return {
            "can_trade": False,
            "reason": f"超过单只股票持仓限制 ({max_position_pct*100:.0f}%)",
            "max_allowed": max_single_position - current_position,
        }

    # 检查总暴露限制
    if current_position + new_order_amount > max_total:
        return {
            "can_trade": False,
            "reason": f"超过总暴露限制 ({max_total_exposure*100:.0f}%)",
            "max_allowed": max_total - current_position,
        }

    return {
        "can_trade": True,
        "reason": "持仓限制检查通过",
        "max_allowed": max_single_position - current_position,
    }


def check_trading_frequency(
    recent_trades: list[dict],
    max_trades_per_day: int = 5,
    min_interval_seconds: int = 60,
) -> dict:
    """检查交易频率.

    Args:
        recent_trades: 最近交易记录
        max_trades_per_day: 每日最大交易次数
        min_interval_seconds: 最小交易间隔 (秒)

    Returns:
        dict: {
            "can_trade": bool,
            "reason": str,
            "trades_today": int,
            "time_since_last": int,
        }
    """
    now = datetime.now()

    # 统算今日交易次数
    today_trades = [
        t for t in recent_trades
        if t.get("time", datetime.min).date() == now.date()
    ]
    trades_today = len(today_trades)

    # 检查每日限制
    if trades_today >= max_trades_per_day:
        return {
            "can_trade": False,
            "reason": f"超过每日交易次数限制 ({max_trades_per_day})",
            "trades_today": trades_today,
            "time_since_last": 0,
        }

    # 检查交易间隔
    if today_trades:
        last_trade_time = max(t.get("time", datetime.min) for t in today_trades)
        time_since_last = (now - last_trade_time).total_seconds()

        if time_since_last < min_interval_seconds:
            return {
                "can_trade": False,
                "reason": f"交易间隔不足 ({min_interval_seconds}秒)",
                "trades_today": trades_today,
                "time_since_last": int(time_since_last),
            }

    return {
        "can_trade": True,
        "reason": "交易频率检查通过",
        "trades_today": trades_today,
        "time_since_last": 0,
    }


def check_lot_size(
    order_quantity: int,
    lot_size: int = 100,
) -> dict:
    """检查手数限制.

    Args:
        order_quantity: 订单数量
        lot_size: 每手数量 (A股100股)

    Returns:
        dict: {
            "is_valid": bool,
            "reason": str,
            "adjusted_quantity": int,
        }
    """
    if order_quantity <= 0:
        return {
            "is_valid": False,
            "reason": "订单数量必须大于0",
            "adjusted_quantity": 0,
        }

    # 检查是否为整手
    if order_quantity % lot_size != 0:
        # 调整为整手
        adjusted_quantity = (order_quantity // lot_size) * lot_size
        return {
            "is_valid": False,
            "reason": f"订单数量必须为{lot_size}的整倍数",
            "adjusted_quantity": adjusted_quantity,
        }

    return {
        "is_valid": True,
        "reason": "手数检查通过",
        "adjusted_quantity": order_quantity,
    }


def comprehensive_trading_check(
    symbol: str,
    current_price: float,
    prev_close: float,
    order_direction: int,  # 1=买入, -1=卖出
    order_quantity: int,
    current_position: float,
    capital: float,
    recent_trades: list[dict] | None = None,
) -> TradingCheckResult:
    """综合交易检查.

    Args:
        symbol: 股票代码
        current_price: 当前价
        prev_close: 昨收价
        order_direction: 订单方向
        order_quantity: 订单数量
        current_position: 当前持仓
        capital: 总资金
        recent_trades: 最近交易记录

    Returns:
        TradingCheckResult: 检查结果
    """
    warnings = []
    can_trade = True
    reasons = []

    # 1. 涨跌停检查
    limit_check = check_price_limit(current_price, prev_close)
    if order_direction == 1 and not limit_check["can_buy"]:
        can_trade = False
        reasons.append("涨停无法买入")
    elif order_direction == -1 and not limit_check["can_sell"]:
        can_trade = False
        reasons.append("跌停无法卖出")

    # 2. 交易时间检查
    time_check = check_trading_time()
    if not time_check["is_trading_time"]:
        warnings.append(f"非交易时间，下次开盘: {time_check['next_open']}")

    # 3. 持仓限制检查
    order_amount = current_price * order_quantity
    position_check = check_position_limit(
        current_position, order_amount, capital
    )
    if not position_check["can_trade"]:
        can_trade = False
        reasons.append(position_check["reason"])

    # 4. 交易频率检查
    if recent_trades is None:
        recent_trades = []
    freq_check = check_trading_frequency(recent_trades)
    if not freq_check["can_trade"]:
        warnings.append(freq_check["reason"])

    # 5. 手数检查
    lot_check = check_lot_size(order_quantity)
    if not lot_check["is_valid"]:
        warnings.append(lot_check["reason"])

    # 汇总原因
    if not can_trade:
        reason = "; ".join(reasons)
    elif warnings:
        reason = "; ".join(warnings)
    else:
        reason = "交易检查通过"

    return TradingCheckResult(
        can_trade=can_trade,
        reason=reason,
        warnings=warnings,
    )


def get_trading_check_signal(
    symbol: str,
    current_price: float,
    prev_close: float,
) -> dict:
    """获取交易检查信号.

    Returns:
        dict: {
            "can_trade": bool,
            "reason": str,
            "warnings": list[str],
        }
    """
    result = comprehensive_trading_check(
        symbol=symbol,
        current_price=current_price,
        prev_close=prev_close,
        order_direction=1,
        order_quantity=100,
        current_position=0,
        capital=100000,
    )

    return {
        "can_trade": result.can_trade,
        "reason": result.reason,
        "warnings": result.warnings,
    }
