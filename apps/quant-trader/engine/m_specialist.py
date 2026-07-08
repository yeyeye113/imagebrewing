"""M豆粕专属交易模块 — 针对M0+SELL(1089条,66.3%)优化。

核心发现:
  - M0+SELL: 66.3%准确率, 1089条样本, 100%置信度>0.7
  - M0+BUY: 59.0%准确率 (不在白名单)
  - M豆粕是系统中样本量最大的品种

专属规则:
  1. M豆粕只做空(SSELL), 不做多
  2. 专属止损: ATR×1.0 (更紧, 因为空头趋势明确)
  3. 专属止盈: ATR×2.5 (保守止盈)
  4. 持有期: 7天 (短于默认10天)
  5. 仓位: 标准仓位×1.2 (Tier1放大)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MSpecialistConfig:
    """M豆粕专属配置。"""
    symbol: str = "M"
    only_short: bool = True          # 只做空
    stop_loss_atr_mult: float = 1.0  # 止损ATR倍数 (默认1.5)
    take_profit_atr_mult: float = 2.5  # 止盈ATR倍数 (默认3.0)
    hold_days: int = 7               # 持有天数
    position_mult: float = 1.2       # 仓位倍数 (Tier1放大)
    min_confidence: float = 0.50     # 最低置信度
    require_trend: bool = True       # 要求空头趋势确认


class MSpecialist:
    """M豆粕专属交易专家。"""

    def __init__(self, config: MSpecialistConfig | None = None):
        self.config = config or MSpecialistConfig()

    def should_trade(self, symbol: str, direction: str, confidence: float,
                     trend_aligned: bool = False) -> tuple[bool, str]:
        """判断M豆粕是否应该交易。

        Args:
            symbol: 品种代码
            direction: BUY/SELL
            confidence: 置信度
            trend_aligned: 是否与空头趋势对齐

        Returns:
            (should_trade, reason)
        """
        if symbol.upper().rstrip("0") != self.config.symbol:
            return (True, "")  # 非M品种，不干预

        # 规则1: M豆粕只做空
        if self.config.only_short and direction.upper() == "BUY":
            return (False, "M豆粕专属: 只做空, 拦截BUY")

        # 规则2: 置信度门槛
        if confidence < self.config.min_confidence:
            return (False, f"M豆粕专属: 置信度{confidence:.0%} < {self.config.min_confidence:.0%}")

        # 规则3: 趋势确认
        if self.config.require_trend and not trend_aligned:
            return (False, "M豆粕专属: 未确认空头趋势")

        return (True, "")

    def get_stop_loss(self, atr: float, price: float) -> float:
        """计算M豆粕专属止损百分比。"""
        if atr <= 0 or price <= 0:
            return 0.05  # 默认5%
        stop = self.config.stop_loss_atr_mult * atr / price
        return max(0.02, min(0.10, stop))  # 限幅2%-10%

    def get_take_profit(self, atr: float, price: float) -> float:
        """计算M豆粕专属止盈百分比。"""
        if atr <= 0 or price <= 0:
            return 0.08  # 默认8%
        tp = self.config.take_profit_atr_mult * atr / price
        return max(0.04, min(0.15, tp))  # 限幅4%-15%

    def get_hold_days(self) -> int:
        return self.config.hold_days

    def get_position_mult(self) -> float:
        return self.config.position_mult
