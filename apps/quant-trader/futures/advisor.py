"""期货操盘顾问 — 扫描结果 + 风控 → 可执行建议。

提供：
  - 多空信号评估（趋势+量仓+期限结构三要素）
  - 开仓建议（仓位/止损/止盈）
  - 风控清单（保证金率/杠杆/夜盘风险）
  - 合约临近到期提醒
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .contracts import (
    MARKET_HOURS,
    contract_info,
    next_expiry,
)
from .risk import FuturesPosition, FuturesRiskReport, assess_futures_risk
from .scanner import FuturesSignal

# ── 期货交易原则 ──

FUTURES_PRINCIPLES = [
    "期货带杠杆，单笔风险不得超过总资金的 2%。",
    "永不裸仓：每笔开仓必带止损。夜盘流动性差，止损可以放宽但不可省略。",
    "多空皆可为，但同一品种不同时持有多空双开。",
    "增仓方向是主力方向 — 增仓上涨做多、增仓下跌做空。",
    "交割月前 10 天平仓换月，不进交割月。",
    "趋势是你的朋友：期货趋势一旦形成，惯性远超股票。",
    "顺势加仓、逆势止损，亏损不加仓摊平。",
    "夜盘波动通常是日盘的 0.6-0.8 倍，别在 23:00 后追单。",
    "成交量萎缩 + 持仓下降 = 资金离场，跟主力走。",
    "基差是市场的真正预期：现货升水=供应紧，现货贴水=需求弱。",
]


@dataclass
class TradeAdvice:
    """一条可执行的交易建议。"""

    code: str
    name: str
    direction: str  # long / short / neutral
    entry_zone: str  # "现价入场" / "逢回调入场" / "等突破入场"
    stop_loss_price: float
    take_profit_price: float
    suggested_lots: int
    margin_required: float
    risk_amount: float  # 如果止损触发，亏多少钱
    confidence: str  # 高/中/低
    reasoning: str
    expiry_warning: str = ""
    night_risk: str = ""

    def to_text(self) -> str:
        lines = [
            f"  {'📈做多' if self.direction == 'long' else '📉做空' if self.direction == 'short' else '⚖️观望'} "
            f"{self.code} {self.name}",
            f"    入场: {self.entry_zone} | 止损 ¥{self.stop_loss_price:,.0f} | 止盈 ¥{self.take_profit_price:,.0f}",
            f"    仓位: {self.suggested_lots}手 | 保证金 ¥{self.margin_required:,.0f} | 风险 ¥{self.risk_amount:,.0f}",
            f"    置信度: {self.confidence} | {self.reasoning}",
        ]
        if self.expiry_warning:
            lines.append(f"    ⚠️ {self.expiry_warning}")
        if self.night_risk:
            lines.append(f"    🌙 {self.night_risk}")
        return "\n".join(lines)


@dataclass
class FuturesAdvisor:
    """期货综合顾问。"""

    equity: float = 100_000.0
    cash: float = 100_000.0
    max_leverage: float = 3.0  # 最大杠杆
    max_margin_pct: float = 0.30  # 最大保证金占比
    risk_per_trade: float = 0.02  # 单笔风险 ≤ 总资金 2%

    def analyze_signal(self, sig: FuturesSignal) -> TradeAdvice:
        """分析单个扫描信号 → 生成交易建议。"""
        spec = contract_info(sig.code)
        price = sig.price

        if not spec or price <= 0:
            return TradeAdvice(
                code=sig.code,
                name=sig.name,
                direction="neutral",
                entry_zone="N/A",
                stop_loss_price=0,
                take_profit_price=0,
                suggested_lots=0,
                margin_required=0,
                risk_amount=0,
                confidence="低",
                reasoning="数据不足",
            )

        direction = sig.signal
        if direction == "neutral" or sig.signal_strength == "weak":
            return TradeAdvice(
                code=sig.code,
                name=spec.name,
                direction="neutral",
                entry_zone="观望",
                stop_loss_price=0,
                take_profit_price=0,
                suggested_lots=0,
                margin_required=0,
                risk_amount=0,
                confidence="低",
                reasoning=f"信号偏弱({sig.signal_strength}) | {sig.reason}",
            )

        # 止损: ATR 的 1.5-2x
        atr = sig.atr if sig.atr > 0 else price * 0.01
        if direction == "long":
            stop_loss = price - atr * 1.5
            take_profit = price + atr * 3.0
        else:
            stop_loss = price + atr * 1.5
            take_profit = price - atr * 3.0

        # 仓位计算: 风险预算 / 止损距离
        risk_budget = self.equity * self.risk_per_trade
        contract_value = spec.contract_size * price if spec.contract_size > 0 else price
        stop_distance_pct = atr * 1.5 / price
        if stop_distance_pct > 0:
            lots_by_risk = int(risk_budget / (contract_value * stop_distance_pct))
        else:
            lots_by_risk = 0

        # 保证金约束
        margin_per_lot = spec.calc_margin(price, 1)
        max_margin = self.equity * self.max_margin_pct
        lots_by_margin = int(max_margin / margin_per_lot) if margin_per_lot > 0 else 0

        lots = min(lots_by_risk, lots_by_margin, 10)
        lots = max(1, lots) if direction != "neutral" and confidence_map[sig.signal_strength] != "低" else 0

        # 到期提醒
        expiry_warning = ""
        exp = next_expiry(sig.code)
        days_to_exp = (exp - dt.date.today()).days
        if days_to_exp < 10:
            expiry_warning = f"🟠 距到期仅 {days_to_exp} 天！不建议开新仓"
        elif days_to_exp < 20:
            expiry_warning = f"🟡 距到期 {days_to_exp} 天，注意换月"

        # 夜盘风险
        night_risk = ""
        hours = MARKET_HOURS.get(sig.code)
        if hours and hours.night_open:
            night_risk = "有夜盘，注意夜间波动可能导致跳空"

        # 入场策略
        if direction == "long":
            entry_zone = "逢回调到均线附近入场" if sig.change_pct > 2 else "现价或略低入场"
        else:
            entry_zone = "逢反弹到压力位入场" if sig.change_pct < -2 else "现价或略高入场"

        risk_amount = lots * contract_value * stop_distance_pct
        confidence = confidence_map.get(sig.signal_strength, "中")

        return TradeAdvice(
            code=sig.code,
            name=spec.name,
            direction=direction,
            entry_zone=entry_zone,
            stop_loss_price=round(stop_loss, 2),
            take_profit_price=round(take_profit, 2),
            suggested_lots=lots,
            margin_required=round(margin_per_lot * lots, 2),
            risk_amount=round(risk_amount, 2),
            confidence=confidence,
            reasoning=sig.reason,
            expiry_warning=expiry_warning,
            night_risk=night_risk,
        )

    def review_positions(self, positions: list[FuturesPosition]) -> FuturesRiskReport:
        """审查现有持仓。"""
        report = assess_futures_risk(positions, self.equity, self.cash)
        return report

    def scan_and_advise(self) -> tuple[list, list[TradeAdvice]]:
        from .scanner_v2 import scan_futures as sf_v2

        scan = sf_v2()
        advices = [self.analyze_signal(s) for s in scan.signals]
        return scan.signals, advices


confidence_map = {"strong": "高", "moderate": "中", "weak": "低"}


def advise_futures(
    equity: float = 100_000,
    cash: float = 100_000,
    positions: list[FuturesPosition] | None = None,
) -> tuple[list, list[TradeAdvice], FuturesRiskReport | None]:
    """快捷顾问函数。"""
    advisor = FuturesAdvisor(equity=equity, cash=cash)
    scan, advices = advisor.scan_and_advise()
    risk = advisor.review_positions(positions or []) if positions else None
    return scan, advices, risk


def format_advices(advices: list[TradeAdvice], max_show: int = 8) -> str:
    """格式化建议输出。"""
    lines = [
        "╔══════════════════════════════════════════════╗",
        "║  🎯 期货辅助交易建议                          ║",
        "╠══════════════════════════════════════════════╣",
    ]

    active = [a for a in advices if a.direction != "neutral"]
    neutral = [a for a in advices if a.direction == "neutral"]

    for a in active[:max_show]:
        lines.append(a.to_text())

    if neutral and len(active) < 5:
        lines.append("╠══════════════════════════════════════════════╣")
        lines.append("║  ⏸️ 观望品种:                                  ║")
        for a in neutral[:3]:
            lines.append(f"║  {a.code} {a.name:<8s} — {a.reasoning[:28]:<28s} ║")

    lines.append("╠══════════════════════════════════════════════╣")
    long_n = sum(1 for a in active if a.direction == "long")
    short_n = sum(1 for a in active if a.direction == "short")
    lines.append(f"║  多 {long_n} · 空 {short_n} · 观望 {len(neutral)}                             ║")
    lines.append("╚══════════════════════════════════════════════╝")

    return "\n".join(lines)


def format_principles() -> str:
    return "\n".join(f"  - {p}" for p in FUTURES_PRINCIPLES)
