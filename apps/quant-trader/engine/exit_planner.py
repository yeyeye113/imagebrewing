"""高低点预测驱动的出场规划器 — 止盈止损计算。

使用高低点预测来计算合理的入场区间、止损位、止盈位和风险收益比。
不单独决定方向，只负责出场参数。

Usage:
    planner = ExitPlanner()
    exit_info = planner.plan_exit(
        symbol="M0", direction="BUY",
        current_price=3200, predicted_high_pct=0.03,
        predicted_low_pct=-0.02, atr=50, volatility=0.15, cost_pct=0.003
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExitPlan:
    """出场规划结果。"""
    symbol: str = ""
    direction: str = "HOLD"
    entry_zone: list[float] = field(default_factory=list)
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    risk_reward_ratio: float = 0.0
    invalid_reason: str = ""
    approved: bool = True

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_zone": [round(x, 4) for x in self.entry_zone],
            "stop_loss_pct": round(self.stop_loss_pct, 4),
            "take_profit_pct": round(self.take_profit_pct, 4),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "invalid_reason": self.invalid_reason,
            "approved": self.approved,
        }


class ExitPlanner:
    """基于高低点预测的出场规划器。"""

    def __init__(
        self,
        max_stop_loss: float = 0.05,
        min_risk_reward: float = 1.8,
        cost_buffer: float = 0.005,
    ):
        """
        Args:
            max_stop_loss: 最大允许止损比例
            min_risk_reward: 最低风险收益比
            cost_buffer: 成本缓冲 (commission + slippage)
        """
        self.max_stop_loss = max_stop_loss
        self.min_risk_reward = min_risk_reward
        self.cost_buffer = cost_buffer

    def plan_exit(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        predicted_high_pct: float,
        predicted_low_pct: float,
        atr: float = 0.0,
        volatility: float = 0.0,
        cost_pct: float = 0.003,
    ) -> dict:
        """计算出场参数。

        Args:
            symbol: 品种代码
            direction: "BUY" 或 "SELL"
            current_price: 当前价格
            predicted_high_pct: 预测最高价偏离当前价的百分比 (正数, 如 0.03 = +3%)
            predicted_low_pct: 预测最低价偏离当前价的百分比 (负数, 如 -0.02 = -2%)
            atr: 平均真实波幅 (绝对值)
            volatility: 当前波动率
            cost_pct: 交易成本百分比 (commission + slippage)

        Returns:
            ExitPlan.to_dict()
        """
        plan = ExitPlan(symbol=symbol, direction=direction)

        # ── 输入验证 ──
        if direction not in ("BUY", "SELL"):
            plan.invalid_reason = f"无效方向: {direction}"
            plan.approved = False
            return plan.to_dict()

        if current_price <= 0:
            plan.invalid_reason = "当前价格无效"
            plan.approved = False
            return plan.to_dict()

        total_cost = cost_pct + self.cost_buffer

        # ── 根据方向计算 ──
        if direction == "BUY":
            upside = predicted_high_pct  # 正数
            downside = abs(predicted_low_pct)  # 转正数

            # 入场区间: 当前价 ± ATR 的一部分
            if atr > 0:
                entry_low = current_price - atr * 0.3
                entry_high = current_price + atr * 0.3
            else:
                entry_low = current_price * 0.995
                entry_high = current_price * 1.005
            plan.entry_zone = [entry_low, entry_high]

            # 风险收益比
            net_upside = upside - total_cost
            net_downside = downside + total_cost

            if net_downside <= 0:
                plan.risk_reward_ratio = 0.0
            else:
                plan.risk_reward_ratio = net_upside / net_downside if net_upside > 0 else 0.0

            # 止损: 取预测低点和最大止损中较小的
            predicted_stop = downside + total_cost
            plan.stop_loss_pct = min(predicted_stop, self.max_stop_loss)
            plan.stop_loss_pct = max(plan.stop_loss_pct, 0.02)  # 最低 2%

            # 止盈: 取预测高点空间的 80% (不追顶)
            plan.take_profit_pct = upside * 0.8 if upside > 0 else 0.08
            plan.take_profit_pct = min(plan.take_profit_pct, 0.15)  # 最高 15%

        elif direction == "SELL":
            upside = abs(predicted_low_pct)  # 下跌空间
            downside = predicted_high_pct  # 上涨风险

            if atr > 0:
                entry_low = current_price - atr * 0.3
                entry_high = current_price + atr * 0.3
            else:
                entry_low = current_price * 0.995
                entry_high = current_price * 1.005
            plan.entry_zone = [entry_low, entry_high]

            net_upside = upside - total_cost
            net_downside = downside + total_cost

            if net_downside <= 0:
                plan.risk_reward_ratio = 0.0
            else:
                plan.risk_reward_ratio = net_upside / net_downside if net_upside > 0 else 0.0

            predicted_stop = downside + total_cost
            plan.stop_loss_pct = min(predicted_stop, self.max_stop_loss)
            plan.stop_loss_pct = max(plan.stop_loss_pct, 0.02)

            plan.take_profit_pct = upside * 0.8 if upside > 0 else 0.08
            plan.take_profit_pct = min(plan.take_profit_pct, 0.15)

        # ── 合理性检查 ──

        # 预测空间不足以覆盖成本
        if upside <= total_cost:
            plan.invalid_reason = (
                f"预测空间 {upside:.2%} 不足以覆盖成本 {total_cost:.2%}"
            )
            plan.approved = False
            return plan.to_dict()

        # 风险收益比不足
        if plan.risk_reward_ratio < self.min_risk_reward:
            plan.invalid_reason = (
                f"风险收益比 {plan.risk_reward_ratio:.2f} 低于阈值 {self.min_risk_reward}"
            )
            plan.approved = False
            return plan.to_dict()

        # 价格已接近预测目标 (不追单)
        if direction == "BUY" and current_price > 0:
            distance_to_high = predicted_high_pct
            if 0 < distance_to_high < total_cost * 2:
                plan.invalid_reason = (
                    f"当前价已接近预测高点 (距离 {distance_to_high:.2%})，不追单"
                )
                plan.approved = False
                return plan.to_dict()

        if direction == "SELL" and current_price > 0:
            distance_to_low = abs(predicted_low_pct)
            if 0 < distance_to_low < total_cost * 2:
                plan.invalid_reason = (
                    f"当前价已接近预测低点 (距离 {distance_to_low:.2%})，不追单"
                )
                plan.approved = False
                return plan.to_dict()

        plan.approved = True
        return plan.to_dict()
