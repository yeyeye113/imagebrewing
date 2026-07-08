"""期货风控模块 — 杠杆/爆仓/逐日盯市/保证金追缴预警。

与股票的 RiskConfig 不同，期货的核心风险是：
- 杠杆放大：保证金制度下实际杠杆可达 5-20 倍
- 逐日盯市：每日结算，亏损当天就要补钱
- 强平风险：保证金不足时被交易所强制平仓
- 夜盘波动：夜间流动性低，滑点大
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import ContractSpec, contract_info


@dataclass
class FuturesPosition:
    """一个期货持仓的实时状态。"""

    code: str  # 品种代码 (RB, SC, IF...)
    direction: str  # "long" | "short"
    lots: int  # 手数
    entry_price: float  # 开仓均价
    current_price: float  # 最新价
    leverage: float = 1.0  # 实际杠杆倍数 (用户设置)
    stop_loss_price: float = 0.0  # 止损价位 (0=未设)
    take_profit_price: float = 0.0  # 止盈价位
    opened_at: str = ""  # 开仓时间 ISO

    @property
    def spec(self) -> ContractSpec | None:
        return contract_info(self.code)

    @property
    def contract_value(self) -> float:
        """合约面值（元）。"""
        s = self.spec
        if not s:
            return self.current_price * self.lots
        if s.multiplier != 1:
            return self.current_price * s.multiplier * self.lots
        return self.current_price * s.contract_size * self.lots

    @property
    def used_margin(self) -> float:
        """占用保证金。"""
        s = self.spec
        if not s:
            return self.contract_value * 0.10
        return s.calc_margin(self.current_price, self.lots)

    @property
    def unrealized_pnl(self) -> float:
        """浮动盈亏。"""
        s = self.spec
        multiplier = 1.0
        if s:
            multiplier = s.multiplier if s.multiplier != 1 else s.contract_size

        if self.direction == "long":
            return (self.current_price - self.entry_price) * multiplier * self.lots
        return (self.entry_price - self.current_price) * multiplier * self.lots

    @property
    def pnl_pct(self) -> float:
        """盈亏百分比（相对保证金）。"""
        margin = self.used_margin
        if margin <= 0:
            return 0.0
        return self.unrealized_pnl / margin

    @property
    def distance_to_stop(self) -> float:
        """距止损的价差百分比。"""
        if self.stop_loss_price <= 0 or self.entry_price <= 0:
            return 1.0
        if self.direction == "long":
            return (self.current_price - self.stop_loss_price) / self.entry_price
        return (self.stop_loss_price - self.current_price) / self.entry_price

    @property
    def distance_to_liquidation(self) -> float:
        """估算距强平的距离百分比。

        强平线 ≈ 保证金维持率降至 0% (实际交易所设 100%-120% 维持保证金)。
        简化: (equity - used_margin * leverage) / contract_value。
        """
        margin = self.used_margin
        if self.contract_value <= 0:
            return 1.0
        loss_capacity = margin * (1 - 0.3)  # 假设 30% 保证金后强平
        return loss_capacity / self.contract_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.spec.name if self.spec else "",
            "direction": self.direction,
            "lots": self.lots,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "pnl_pct": round(self.pnl_pct * 100, 2),
            "used_margin": round(self.used_margin, 2),
            "leverage": self.leverage,
            "dist_to_stop_pct": round(self.distance_to_stop * 100, 2),
            "dist_to_liq_pct": round(self.distance_to_liquidation * 100, 2),
        }


@dataclass
class FuturesRiskReport:
    """综合风险评估报告。"""

    positions: list[FuturesPosition]
    total_equity: float
    total_margin: float
    available_cash: float
    warnings: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    risk_level: str = "normal"  # normal / warning / danger / critical

    @property
    def margin_ratio(self) -> float:
        """保证金占用率。"""
        return self.total_margin / self.total_equity if self.total_equity > 0 else 1.0

    @property
    def total_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions)

    def to_text(self) -> str:
        """格式化风险报告。"""
        lines = [
            "╔══════════════════════════════════════════════╗",
            "║  🛡️ 期货风控报告                              ║",
            "╠══════════════════════════════════════════════╣",
        ]
        level_icon = {"normal": "🟢", "warning": "🟡", "danger": "🟠", "critical": "🔴"}
        lines.append(f"║  风险等级: {level_icon.get(self.risk_level, '⚪')} {self.risk_level:<32s} ║")
        lines.append(f"║  总权益: ¥{self.total_equity:>12,.0f}                       ║")
        lines.append(f"║  保证金: ¥{self.total_margin:>12,.0f} ({self.margin_ratio * 100:.0f}%)               ║")
        lines.append(f"║  可用金: ¥{self.available_cash:>12,.0f}                       ║")
        lines.append(f"║  浮动盈亏: ¥{self.total_pnl:>10,.0f}                         ║")
        lines.append("╠══════════════════════════════════════════════╣")

        for p in self.positions:
            dir_icon = "📈" if p.direction == "long" else "📉"
            pnl_sign = "+" if p.unrealized_pnl >= 0 else ""
            lines.append(
                f"║  {dir_icon} {p.spec.name if p.spec else p.code:<8s} "
                f"{p.direction.upper():4s} "
                f"{p.lots}手 "
                f"盈亏 {pnl_sign}{p.unrealized_pnl:,.0f} ({p.pnl_pct:+.1f}%)"
            )
            dist = f"距止损 {p.distance_to_stop * 100:+.1f}%" if p.stop_loss_price > 0 else "未设止损 ⚠️"
            lines.append(f"║    入场 ¥{p.entry_price:,.0f} → ¥{p.current_price:,.0f} | {dist} | 杠杆 {p.leverage:.0f}x")

        if self.warnings:
            lines.append("╠══════════════════════════════════════════════╣")
            for w in self.warnings[:4]:
                lines.append(f"║  ⚠️ {w[:40]:<40s} ║")
        if self.alerts:
            for a in self.alerts[:3]:
                lines.append(f"║  🚨 {a[:40]:<40s} ║")

        lines.append("╚══════════════════════════════════════════════╝")
        return "\n".join(lines)


def assess_futures_risk(
    positions: list[FuturesPosition],
    equity: float,
    cash: float,
) -> FuturesRiskReport:
    """评估期货组合的整体风险。"""

    warnings: list[str] = []
    alerts: list[str] = []
    total_margin = sum(p.used_margin for p in positions)

    # 保证金率检查
    margin_pct = total_margin / equity if equity > 0 else 0
    if margin_pct > 0.80:
        alerts.append(f"保证金率 {margin_pct * 100:.0f}% — 接近满仓，追加保证金风险极高")
    elif margin_pct > 0.60:
        warnings.append(f"保证金率 {margin_pct * 100:.0f}% — 仓位偏重")
    elif margin_pct > 0.40:
        warnings.append(f"保证金率 {margin_pct * 100:.0f}% — 建议控制在 30% 以内")

    # 逐仓检查
    for p in positions:
        if not p.stop_loss_price:
            warnings.append(f"{p.code} 未设止损 — 期货杠杆下裸仓极度危险")
        if p.pnl_pct < -0.20:
            alerts.append(f"{p.code} 浮亏 {p.pnl_pct * 100:.0f}% — 距强平 {p.distance_to_liquidation * 100:.0f}%")
        if p.distance_to_stop < -0.05:
            alerts.append(f"{p.code} 已跌破止损位 {p.stop_loss_price}")
        if p.leverage > 10:
            warnings.append(f"{p.code} 杠杆 {p.leverage:.0f}x 过高")

    # 集中度检查
    if len(positions) > 1:
        max_pos = max(positions, key=lambda p: p.used_margin)
        conc = max_pos.used_margin / total_margin if total_margin > 0 else 0
        if conc > 0.50:
            warnings.append(f"单一品种 {max_pos.code} 占比 {conc * 100:.0f}% — 过度集中")

    # 风险等级
    if alerts:
        risk_level = "critical" if len(alerts) >= 2 or margin_pct > 0.85 else "danger"
    elif len(warnings) >= 3:
        risk_level = "warning"
    else:
        risk_level = "normal"

    return FuturesRiskReport(
        positions=positions,
        total_equity=equity,
        total_margin=total_margin,
        available_cash=cash,
        warnings=warnings,
        alerts=alerts,
        risk_level=risk_level,
    )
