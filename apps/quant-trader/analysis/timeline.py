"""交易计划时间轴 — 从高低点到可执行计划。

输入: HighLowResult + 用户目标/约束
输出: 时间轴计划 (入场区间/目标位/止损/里程碑/关键日期)

用法:
    from quanttrader.analysis import build_timeline, TimelinePlan
    plan = build_timeline(highlow_result, direction="long", capital=10000)
    print(plan.to_text())
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from .highlow import HighLowResult


@dataclass
class Milestone:
    """时间轴上的一个里程碑。"""

    date: str  # YYYY-MM-DD
    label: str  # "入场观察" / "第一目标" / "止损警戒"
    price: float
    action: str  # "观察" / "建仓" / "加仓" / "减仓" / "止损" / "止盈"
    note: str = ""

    def to_text(self) -> str:
        icon = {"观察": "👀", "建仓": "🟢", "加仓": "⬆️", "减仓": "⬇️", "止损": "🛑", "止盈": "💰"}.get(self.action, "📍")
        return f"  {icon} {self.date} | {self.label:<12s} | ¥{self.price:,.2f} | {self.action} | {self.note}"


@dataclass
class TimelinePlan:
    """交易计划时间轴。"""

    symbol: str
    direction: str  # "long" | "short" | "neutral"
    current_price: float
    entry_zone: tuple[float, float] = (0, 0)  # 入场区间
    target_1: float = 0.0  # 第一目标
    target_2: float = 0.0  # 第二目标
    stop_loss: float = 0.0  # 止损
    risk_reward: float = 0.0  # 风险收益比
    hold_days: int = 0  # 建议持有天数
    milestones: list[Milestone] = field(default_factory=list)
    reasoning: str = ""
    # 高低点预测 (新增)
    predicted_high: float = 0.0  # 预测高点
    predicted_low: float = 0.0  # 预测低点

    def to_text(self) -> str:
        dir_icon = {"long": "📈做多", "short": "📉做空", "neutral": "⚖️观望"}.get(self.direction, "❓")
        lines = [
            "╔══════════════════════════════════════════════════════╗",
            f"║  📋 {self.symbol} 交易计划 — {dir_icon:<20s}    ║",
            "╠══════════════════════════════════════════════════════╣",
            f"║  当前价: ¥{self.current_price:,.2f}                              ║",
            f"║  预测高点: ¥{self.predicted_high:,.2f}                            ║",
            f"║  预测低点: ¥{self.predicted_low:,.2f}                            ║",
            f"║  入场区间: ¥{self.entry_zone[0]:,.2f} ~ ¥{self.entry_zone[1]:,.2f}                    ║",
            f"║  第一目标: ¥{self.target_1:,.2f}                              ║",
            f"║  第二目标: ¥{self.target_2:,.2f}                              ║",
            f"║  止损位: ¥{self.stop_loss:,.2f}                               ║",
            f"║  风险收益比: 1:{self.risk_reward:.1f}                              ║",
            f"║  建议持有: {self.hold_days} 个交易日                             ║",
            "╠══════════════════════════════════════════════════════╣",
            "║  时间轴:                                             ║",
        ]
        for m in self.milestones:
            lines.append(f"║{m.to_text():<54s}║")
        lines.append("╠══════════════════════════════════════════════════════╣")
        # 推理过程 (截断)
        for line in self.reasoning[:200].split("\n"):
            lines.append(f"║  {line:<52s}║")
        lines.append("╚══════════════════════════════════════════════════════╝")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "current_price": self.current_price,
            "entry_zone": list(self.entry_zone),
            "target_1": self.target_1,
            "target_2": self.target_2,
            "stop_loss": self.stop_loss,
            "risk_reward": round(self.risk_reward, 2),
            "hold_days": self.hold_days,
            "reasoning": self.reasoning,
            "milestones": [
                {"date": m.date, "label": m.label, "price": m.price, "action": m.action, "note": m.note}
                for m in self.milestones
            ],
        }


# ══════════════════════════════════════════════════════════════════
# 计划生成
# ══════════════════════════════════════════════════════════════════


def _calc_risk_reward(entry: float, target: float, stop: float, direction: str) -> float:
    """计算风险收益比。"""
    if direction == "long":
        reward = target - entry
        risk = entry - stop
    else:
        reward = entry - target
        risk = stop - entry
    if risk <= 0:
        return 0
    return reward / risk


def build_timeline(
    hl: HighLowResult,
    direction: str = "long",
    capital: float = 10000,
    max_hold_days: int = 10,
    risk_pct: float = 0.02,
) -> TimelinePlan:
    """从高低点分析生成交易计划时间轴。

    Args:
        hl: 高低点分析结果
        direction: "long" | "short" | "neutral"
        capital: 可用资金
        max_hold_days: 最大持有天数
        risk_pct: 单笔风险比例
    """
    price = hl.current_price
    atr = hl.atr if hl.atr > 0 else price * 0.02
    today = dt.date.today()

    supports = hl.supports()
    resistances = hl.resistances()

    if direction == "neutral" or not supports or not resistances:
        return TimelinePlan(
            symbol=hl.symbol,
            direction="neutral",
            current_price=price,
            reasoning="信号不明确，建议观望等待更清晰的方向。",
            milestones=[Milestone(today.isoformat(), "观望", price, "观察", "等待信号确认")],
        )

    # 入场区间
    if direction == "long":
        # 做多: 回调到支撑附近入场
        entry_low = supports[0].price if supports else price * 0.98
        entry_high = price * 0.995  # 现价附近
        entry_zone = (entry_low, entry_high)
        # 目标
        target_1 = resistances[0].price if resistances else price * 1.03
        target_2 = resistances[1].price if len(resistances) > 1 else target_1 * 1.03
        # 止损: 支撑下方一个ATR
        stop_loss = entry_low - atr
        # 预测高点: 阻力位上方
        predicted_high = resistances[0].price * 1.02 if resistances else price * 1.05
        # 预测低点: 支撑位下方
        predicted_low = supports[0].price * 0.98 if supports else price * 0.95
    else:
        # 做空: 反弹到阻力附近入场
        entry_low = price * 0.995
        entry_high = resistances[0].price if resistances else price * 1.02
        entry_zone = (entry_low, entry_high)
        # 目标
        target_1 = supports[0].price if supports else price * 0.97
        target_2 = supports[1].price if len(supports) > 1 else target_1 * 0.97
        # 止损: 阻力上方一个ATR
        stop_loss = entry_high + atr
        # 预测高点: 阻力位上方
        predicted_high = resistances[0].price * 1.02 if resistances else price * 1.05
        # 预测低点: 支撑位下方
        predicted_low = supports[0].price * 0.98 if supports else price * 0.95

    # 风险收益比
    entry_mid = (entry_zone[0] + entry_zone[1]) / 2
    rr = _calc_risk_reward(entry_mid, target_1, stop_loss, direction)

    # 持有天数: 根据目标距离和ATR估算
    target_dist = abs(target_1 - entry_mid)
    daily_move = atr * 0.7  # 日均真实波幅约0.7*ATR
    est_days = int(target_dist / daily_move) if daily_move > 0 else max_hold_days
    hold_days = min(max(est_days, 2), max_hold_days)

    # 时间轴里程碑
    milestones: list[Milestone] = []

    # 高低点预测里程碑
    milestones.append(
        Milestone(today.isoformat(), "预测高点", predicted_high, "观察", f"阻力位附近 ¥{predicted_high:,.0f}")
    )
    milestones.append(
        Milestone(today.isoformat(), "预测低点", predicted_low, "观察", f"支撑位附近 ¥{predicted_low:,.0f}")
    )

    if direction == "long":
        milestones.append(
            Milestone(
                today.isoformat(),
                "观察入场",
                entry_mid,
                "观察",
                f"等待回调至¥{entry_zone[0]:,.0f}~¥{entry_zone[1]:,.0f}区间",
            )
        )
        entry_date = today + dt.timedelta(days=1)
        milestones.append(
            Milestone(entry_date.isoformat(), "建仓", entry_mid, "建仓", f"1手 风险¥{abs(entry_mid - stop_loss):,.0f}")
        )
        t1_date = today + dt.timedelta(days=hold_days // 2)
        milestones.append(Milestone(t1_date.isoformat(), "第一目标", target_1, "减仓", "减半仓，移动止损至成本"))
        t2_date = today + dt.timedelta(days=hold_days)
        milestones.append(Milestone(t2_date.isoformat(), "第二目标", target_2, "止盈", "全部平仓"))
        milestones.append(
            Milestone(
                (today + dt.timedelta(days=max_hold_days)).isoformat(),
                "时间止损",
                price,
                "止损",
                f"超过{max_hold_days}天未达目标则平仓",
            )
        )
    else:
        milestones.append(
            Milestone(
                today.isoformat(),
                "观察入场",
                entry_mid,
                "观察",
                f"等待反弹至¥{entry_zone[0]:,.0f}~¥{entry_zone[1]:,.0f}区间",
            )
        )
        entry_date = today + dt.timedelta(days=1)
        milestones.append(
            Milestone(entry_date.isoformat(), "建仓", entry_mid, "建仓", f"1手 风险¥{abs(stop_loss - entry_mid):,.0f}")
        )
        t1_date = today + dt.timedelta(days=hold_days // 2)
        milestones.append(Milestone(t1_date.isoformat(), "第一目标", target_1, "减仓", "减半仓，移动止损至成本"))
        t2_date = today + dt.timedelta(days=hold_days)
        milestones.append(Milestone(t2_date.isoformat(), "第二目标", target_2, "止盈", "全部平仓"))

    # 止损里程碑
    milestones.append(Milestone(today.isoformat(), "止损警戒", stop_loss, "止损", f"价格触及¥{stop_loss:,.0f}立即止损"))

    # 推理
    reasoning_lines = [
        f"趋势: {hl.trend}",
        f"ATR(14): ¥{atr:,.2f} (日均波动)",
        f"当前位置: 支撑¥{hl.nearest_support:,.0f} ~ 阻力¥{hl.nearest_resistance:,.0f}，位于{hl.position_pct:.0f}%处",
        f"预测高点: ¥{predicted_high:,.0f} | 预测低点: ¥{predicted_low:,.0f}",
        f"风险收益比 1:{rr:.1f} {'✅ 可行' if rr >= 1.5 else '⚠️ 偏低，谨慎'}",
        f"建议持有 {hold_days} 天，最大 {max_hold_days} 天",
    ]
    reasoning = "\n".join(reasoning_lines)

    return TimelinePlan(
        symbol=hl.symbol,
        direction=direction,
        current_price=price,
        entry_zone=entry_zone,
        target_1=target_1,
        target_2=target_2,
        stop_loss=stop_loss,
        risk_reward=rr,
        hold_days=hold_days,
        milestones=sorted(milestones, key=lambda m: m.date),
        reasoning=reasoning,
        predicted_high=predicted_high,
        predicted_low=predicted_low,
    )
