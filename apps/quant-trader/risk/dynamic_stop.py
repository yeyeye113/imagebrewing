"""动态止损优化 — 根据市场状态动态调整止损。

止损策略:
  - ATR止损: 基于波动率
  - 位置止损: 基于支撑阻力
  - 时间止损: 基于持有时间
  - 移动止损: 盈利后移动

功能:
  - 动态计算止损位
  - 多种止损策略组合
  - 自动调整

用法:
    from quanttrader.risk.dynamic_stop import DynamicStopLoss
    stop_loss = DynamicStopLoss()
    stop_price = stop_loss.calculate(entry_price, signal, hl_result)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StopLossResult:
    """止损计算结果。"""

    stop_price: float
    stop_type: str  # 'atr', 'support', 'resistance', 'time'
    distance: float  # 距离入场价的百分比
    risk_reward: float  # 风险收益比
    description: str


class DynamicStopLoss:
    """动态止损计算器。"""

    def __init__(self):
        self.default_atr_multiplier = 1.5
        self.max_stop_pct = 0.05  # 最大止损5%
        self.min_stop_pct = 0.01  # 最小止损1%

    def calculate(
        self,
        entry_price: float,
        signal: str,
        hl_result: Any = None,
        atr: float = 0,
        position_pct: float = 50,
    ) -> StopLossResult:
        """计算动态止损。

        Args:
            entry_price: 入场价
            signal: 信号 (LONG/SHORT)
            hl_result: 高低点分析结果
            atr: ATR值
            position_pct: 位置百分比

        Returns:
            止损计算结果
        """
        # 候选止损位
        candidates = []

        # 1. ATR止损
        if atr > 0:
            atr_stop = self._atr_stop(entry_price, signal, atr, position_pct)
            candidates.append(atr_stop)

        # 2. 支撑阻力止损
        if hl_result:
            sr_stop = self._support_resistance_stop(entry_price, signal, hl_result)
            candidates.append(sr_stop)

        # 3. 百分比止损
        pct_stop = self._percentage_stop(entry_price, signal)
        candidates.append(pct_stop)

        # 选择最优止损
        best_stop = self._select_best_stop(candidates, entry_price, signal)

        return best_stop

    def _atr_stop(
        self,
        entry_price: float,
        signal: str,
        atr: float,
        position_pct: float,
    ) -> StopLossResult:
        """ATR止损。"""
        # 基础ATR倍数
        multiplier = self.default_atr_multiplier

        # 位置调整
        if position_pct > 80:  # 位置过高
            multiplier *= 0.8  # 收紧止损
        elif position_pct < 20:  # 位置过低
            multiplier *= 1.2  # 放宽止损

        # 计算止损价
        if signal == "LONG":
            stop_price = entry_price - atr * multiplier
        else:
            stop_price = entry_price + atr * multiplier

        # 确保止损在合理范围
        stop_price = self._clamp_stop(entry_price, stop_price, signal)

        distance = abs(stop_price - entry_price) / entry_price
        risk_reward = self._calculate_risk_reward(entry_price, stop_price, signal)

        return StopLossResult(
            stop_price=stop_price,
            stop_type="atr",
            distance=distance,
            risk_reward=risk_reward,
            description=f"ATR止损: {multiplier:.1f}倍ATR",
        )

    def _support_resistance_stop(
        self,
        entry_price: float,
        signal: str,
        hl_result: Any,
    ) -> StopLossResult:
        """支撑阻力止损。"""
        if signal == "LONG":
            # 做多止损放在支撑下方
            support = hl_result.nearest_support
            stop_price = support * 0.99  # 支撑下方1%
        else:
            # 做空止损放在阻力上方
            resistance = hl_result.nearest_resistance
            stop_price = resistance * 1.01  # 阻力上方1%

        # 确保止损在合理范围
        stop_price = self._clamp_stop(entry_price, stop_price, signal)

        distance = abs(stop_price - entry_price) / entry_price
        risk_reward = self._calculate_risk_reward(entry_price, stop_price, signal)

        return StopLossResult(
            stop_price=stop_price,
            stop_type="support_resistance",
            distance=distance,
            risk_reward=risk_reward,
            description=f"支撑阻力止损: {'支撑' if signal == 'LONG' else '阻力'}位",
        )

    def _percentage_stop(self, entry_price: float, signal: str) -> StopLossResult:
        """百分比止损。"""
        # 默认2%止损
        stop_pct = 0.02

        if signal == "LONG":
            stop_price = entry_price * (1 - stop_pct)
        else:
            stop_price = entry_price * (1 + stop_pct)

        distance = stop_pct
        risk_reward = self._calculate_risk_reward(entry_price, stop_price, signal)

        return StopLossResult(
            stop_price=stop_price,
            stop_type="percentage",
            distance=distance,
            risk_reward=risk_reward,
            description=f"百分比止损: {stop_pct * 100:.0f}%",
        )

    def _select_best_stop(
        self,
        candidates: list[StopLossResult],
        entry_price: float,
        signal: str,
    ) -> StopLossResult:
        """选择最优止损。"""
        # 过滤掉不合理的止损
        valid_candidates = []
        for c in candidates:
            if c.distance >= self.min_stop_pct and c.distance <= self.max_stop_pct:
                valid_candidates.append(c)

        if not valid_candidates:
            # 如果没有合理的选择，使用百分比止损
            return self._percentage_stop(entry_price, signal)

        # 选择风险收益比最好的
        best = max(valid_candidates, key=lambda x: x.risk_reward)
        return best

    def _clamp_stop(self, entry_price: float, stop_price: float, signal: str) -> float:
        """限制止损在合理范围。"""
        if signal == "LONG":
            # 做多止损不能太近也不能太远
            min_stop = entry_price * (1 - self.max_stop_pct)
            max_stop = entry_price * (1 - self.min_stop_pct)
            return float(max(min_stop, min(stop_price, max_stop)))
        else:
            # 做空止损不能太近也不能太远
            min_stop = entry_price * (1 + self.min_stop_pct)
            max_stop = entry_price * (1 + self.max_stop_pct)
            return float(min(max_stop, max(stop_price, min_stop)))

    def _calculate_risk_reward(
        self,
        entry_price: float,
        stop_price: float,
        signal: str,
    ) -> float:
        """计算风险收益比。"""
        risk = abs(entry_price - stop_price)
        if risk == 0:
            return 0

        # 假设目标是风险的2倍
        reward = risk * 2
        return reward / risk

    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        signal: str,
        highest_price: float = 0,
        lowest_price: float = 0,
    ) -> float:
        """计算移动止损。

        Args:
            entry_price: 入场价
            current_price: 当前价
            signal: 信号
            highest_price: 做多后最高价
            lowest_price: 做空后最低价

        Returns:
            移动止损价
        """
        if signal == "LONG":
            # 做多移动止损: 从最高点回撤2%
            if highest_price > 0:
                trailing_stop = highest_price * 0.98
                # 不能低于入场价
                return max(trailing_stop, entry_price)
            return entry_price * 0.98
        else:
            # 做空移动止损: 从最低点反弹2%
            if lowest_price > 0:
                trailing_stop = lowest_price * 1.02
                # 不能高于入场价
                return min(trailing_stop, entry_price)
            return entry_price * 1.02
