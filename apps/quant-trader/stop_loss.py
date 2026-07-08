"""止损止盈优化模块 — 动态止损止盈策略.

核心原理:
  1. ATR 动态止损: 根据波动率调整止损距离
  2. 移动止损: 保护利润
  3. 分批止盈: 逐步锁定利润
  4. 时间止损: 持仓时间过长自动平仓
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .analysis.indicators import calc_atr
from .log import get_logger

logger = get_logger("stop_loss")


@dataclass
class StopLossConfig:
    """止损止盈配置."""
    # 基础止损
    base_stop_loss: float = 0.05      # 基础止损 5%
    atr_multiplier: float = 2.0       # ATR 倍数

    # 移动止损
    trailing_stop: bool = True        # 启用移动止损
    trailing_activation: float = 0.03 # 盈利 3% 后激活
    trailing_distance: float = 0.02   # 移动止损距离 2%

    # 分批止盈
    partial_take_profit: bool = True  # 启用分批止盈
    tp_level_1: float = 0.05          # 第一目标 5%
    tp_level_2: float = 0.10          # 第二目标 10%
    tp_level_3: float = 0.20          # 第三目标 20%
    tp_ratio_1: float = 0.3           # 第一目标平仓 30%
    tp_ratio_2: float = 0.3           # 第二目标平仓 30%
    tp_ratio_3: float = 0.4           # 第三目标平仓 40%

    # 时间止损
    time_stop: bool = True            # 启用时间止损
    max_holding_days: int = 30        # 最大持仓天数


@dataclass
class StopLossResult:
    """止损止盈计算结果."""
    stop_loss_price: float      # 止损价
    take_profit_price_1: float  # 第一止盈价
    take_profit_price_2: float  # 第二止盈价
    take_profit_price_3: float  # 第三止盈价
    trailing_stop_price: float  # 移动止损价
    stop_loss_pct: float        # 止损百分比
    take_profit_pct: float      # 止盈百分比
    risk_reward_ratio: float    # 风险回报比


def calculate_atr_stop_loss(
    prices: pd.DataFrame,
    entry_price: float,
    direction: int,
    config: StopLossConfig | None = None,
) -> float:
    """计算 ATR 止损价.

    Args:
        prices: OHLCV 数据
        entry_price: 入场价
        direction: 方向 (+1 看多, -1 看空)
        config: 止损配置

    Returns:
        float: 止损价
    """
    if config is None:
        config = StopLossConfig()

    # 计算 ATR
    atr = calc_atr(prices)
    atr_val = atr['atr']

    # ATR 止损距离
    atr_stop_distance = atr_val * config.atr_multiplier

    # 基础止损距离
    base_stop_distance = entry_price * config.base_stop_loss

    # 取较大值
    stop_distance = max(atr_stop_distance, base_stop_distance)

    # 计算止损价
    if direction == 1:  # 看多
        stop_loss_price = entry_price - stop_distance
    else:  # 看空
        stop_loss_price = entry_price + stop_distance

    return float(stop_loss_price)


def calculate_trailing_stop(
    entry_price: float,
    current_price: float,
    highest_price: float,
    lowest_price: float,
    direction: int,
    config: StopLossConfig | None = None,
) -> float:
    """计算移动止损价.

    Args:
        entry_price: 入场价
        current_price: 当前价
        highest_price: 持仓期间最高价
        lowest_price: 持仓期间最低价
        direction: 方向 (+1 看多, -1 看空)
        config: 止损配置

    Returns:
        float: 移动止损价
    """
    if config is None:
        config = StopLossConfig()

    if not config.trailing_stop:
        return 0.0

    if direction == 1:  # 看多
        # 计算盈利
        profit_pct = (highest_price - entry_price) / entry_price

        # 激活移动止损
        if profit_pct >= config.trailing_activation:
            # 移动止损价 = 最高价 - 移动距离
            trailing_stop = highest_price * (1 - config.trailing_distance)
            return trailing_stop
        else:
            return 0.0
    else:  # 看空
        # 计算盈利
        profit_pct = (entry_price - lowest_price) / entry_price

        # 激活移动止损
        if profit_pct >= config.trailing_activation:
            # 移动止损价 = 最低价 + 移动距离
            trailing_stop = lowest_price * (1 + config.trailing_distance)
            return trailing_stop
        else:
            return 0.0


def calculate_take_profit(
    entry_price: float,
    direction: int,
    config: StopLossConfig | None = None,
) -> tuple[float, float, float]:
    """计算分批止盈价.

    Args:
        entry_price: 入场价
        direction: 方向 (+1 看多, -1 看空)
        config: 止损配置

    Returns:
        (tp1, tp2, tp3): 三个止盈价
    """
    if config is None:
        config = StopLossConfig()

    if not config.partial_take_profit:
        return 0.0, 0.0, 0.0

    if direction == 1:  # 看多
        tp1 = entry_price * (1 + config.tp_level_1)
        tp2 = entry_price * (1 + config.tp_level_2)
        tp3 = entry_price * (1 + config.tp_level_3)
    else:  # 看空
        tp1 = entry_price * (1 - config.tp_level_1)
        tp2 = entry_price * (1 - config.tp_level_2)
        tp3 = entry_price * (1 - config.tp_level_3)

    return tp1, tp2, tp3


def calculate_stop_loss_result(
    prices: pd.DataFrame,
    entry_price: float,
    direction: int,
    config: StopLossConfig | None = None,
) -> StopLossResult:
    """计算完整的止损止盈结果.

    Args:
        prices: OHLCV 数据
        entry_price: 入场价
        direction: 方向 (+1 看多, -1 看空)
        config: 止损配置

    Returns:
        StopLossResult: 止损止盈结果
    """
    if config is None:
        config = StopLossConfig()

    # 计算 ATR 止损
    stop_loss_price = calculate_atr_stop_loss(prices, entry_price, direction, config)

    # 计算分批止盈
    tp1, tp2, tp3 = calculate_take_profit(entry_price, direction, config)

    # 计算移动止损 (初始值)
    trailing_stop_price = 0.0

    # 计算止损百分比
    stop_loss_pct = abs(entry_price - stop_loss_price) / entry_price

    # 计算止盈百分比 (取第一目标)
    take_profit_pct = abs(tp1 - entry_price) / entry_price if tp1 > 0 else 0.0

    # 计算风险回报比
    risk_reward_ratio = take_profit_pct / stop_loss_pct if stop_loss_pct > 0 else 0.0

    return StopLossResult(
        stop_loss_price=round(stop_loss_price, 2),
        take_profit_price_1=round(tp1, 2),
        take_profit_price_2=round(tp2, 2),
        take_profit_price_3=round(tp3, 2),
        trailing_stop_price=round(trailing_stop_price, 2),
        stop_loss_pct=round(stop_loss_pct, 4),
        take_profit_pct=round(take_profit_pct, 4),
        risk_reward_ratio=round(risk_reward_ratio, 2),
    )


def check_stop_loss_triggered(
    current_price: float,
    stop_loss_price: float,
    direction: int,
) -> bool:
    """检查是否触发止损.

    Args:
        current_price: 当前价
        stop_loss_price: 止损价
        direction: 方向 (+1 看多, -1 看空)

    Returns:
        bool: 是否触发止损
    """
    if direction == 1:  # 看多
        return current_price <= stop_loss_price
    else:  # 看空
        return current_price >= stop_loss_price


def check_take_profit_triggered(
    current_price: float,
    take_profit_price: float,
    direction: int,
) -> bool:
    """检查是否触发止盈.

    Args:
        current_price: 当前价
        take_profit_price: 止盈价
        direction: 方向 (+1 看多, -1 看空)

    Returns:
        bool: 是否触发止盈
    """
    if direction == 1:  # 看多
        return current_price >= take_profit_price
    else:  # 看空
        return current_price <= take_profit_price


def get_optimal_stop_loss(
    prices: pd.DataFrame,
    direction: int,
    confidence: float,
) -> dict:
    """获取最优止损止盈配置.

    Args:
        prices: OHLCV 数据
        direction: 方向
        confidence: 置信度

    Returns:
        dict: {
            "stop_loss_pct": float,
            "take_profit_pct": float,
            "risk_reward_ratio": float,
            "config": StopLossConfig,
        }
    """
    # 根据置信度调整配置
    if confidence >= 90:
        # 高置信度: 更宽松的止损，更高的止盈
        config = StopLossConfig(
            base_stop_loss=0.03,
            atr_multiplier=1.5,
            trailing_activation=0.02,
            trailing_distance=0.015,
            tp_level_1=0.05,
            tp_level_2=0.10,
            tp_level_3=0.20,
        )
    elif confidence >= 80:
        # 中等置信度: 标准配置
        config = StopLossConfig(
            base_stop_loss=0.05,
            atr_multiplier=2.0,
            trailing_activation=0.03,
            trailing_distance=0.02,
            tp_level_1=0.05,
            tp_level_2=0.10,
            tp_level_3=0.15,
        )
    else:
        # 低置信度: 更严格的止损，更低的止盈
        config = StopLossConfig(
            base_stop_loss=0.04,
            atr_multiplier=2.5,
            trailing_activation=0.04,
            trailing_distance=0.025,
            tp_level_1=0.04,
            tp_level_2=0.08,
            tp_level_3=0.12,
        )

    # 计算入场价
    entry_price = float(prices['close'].iloc[-1])

    # 计算止损止盈
    result = calculate_stop_loss_result(prices, entry_price, direction, config)

    return {
        "stop_loss_pct": result.stop_loss_pct,
        "take_profit_pct": result.take_profit_pct,
        "risk_reward_ratio": result.risk_reward_ratio,
        "stop_loss_price": result.stop_loss_price,
        "take_profit_price_1": result.take_profit_price_1,
        "take_profit_price_2": result.take_profit_price_2,
        "take_profit_price_3": result.take_profit_price_3,
        "config": config,
    }
