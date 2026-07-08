"""Pre-trade and post-backtest risk assessment with loss / VaR estimates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .metrics import TRADING_DAYS
from .position_sizing import SizingConfig, compute_entry_notional, compute_portfolio_weights
from .risk import RiskConfig

VAR_Z_95 = 1.645


@dataclass
class TradeRiskAssessment:
    symbol: str
    price: float
    equity: float
    cash: float
    position_value: float
    exposure_pct: float
    cash_pct: float
    daily_vol: float
    annual_vol: float
    proposed_notional: float
    proposed_position_pct: float
    exposure_pct_after: float
    cash_pct_after: float
    max_loss_at_stop: float
    max_loss_pct: float
    max_loss_at_trailing: float
    var_95_1d: float
    var_95_1d_pct: float
    cap_breakdown: dict
    binding_cap: str
    risk_score: int
    risk_grade: str
    warnings: list[str] = field(default_factory=list)
    scenarios: list[dict] = field(default_factory=list)


@dataclass
class PortfolioRiskAssessment:
    symbols: list[str]
    allocation: str
    total_cash: float
    allocated_pct: float
    idle_cash_pct: float
    weights: dict
    per_symbol: dict
    portfolio_daily_vol: float
    portfolio_var_95_1d: float
    portfolio_var_95_1d_pct: float
    concentration_hhi: float
    risk_score: int
    risk_grade: str
    warnings: list[str] = field(default_factory=list)


def _vol_from_prices(prices: pd.DataFrame) -> tuple[float, float]:
    ret = prices["close"].pct_change().dropna()
    if len(ret) < 2:
        return 0.0, 0.0
    daily = float(ret.std())
    return daily, daily * np.sqrt(TRADING_DAYS)


def _entry_cap_breakdown(
    equity: float,
    cash: float,
    position_value: float,
    order_size: float,
    sizing: SizingConfig,
    risk: RiskConfig,
    total_invested: float | None = None,
) -> tuple[dict, str]:
    min_cash = equity * sizing.cash_reserve_pct
    usable_cash = max(0.0, cash - min_cash)
    if total_invested is None:
        total_invested = position_value
    caps = {
        "order_size": usable_cash * order_size,
        "cash_available": cash,
        "max_position_pct": max(0.0, equity * sizing.max_position_pct - position_value),
        "max_total_exposure": max(0.0, equity * sizing.max_total_exposure - total_invested),
    }
    if risk.stop_loss and risk.risk_per_trade:
        caps["risk_based"] = equity * risk.risk_per_trade / risk.stop_loss

    positive = {k: v for k, v in caps.items() if v > 0}
    proposed = min(positive.values()) if positive else 0.0
    binding = min(positive, key=lambda k: positive[k]) if positive else "none"
    return caps, binding


def _risk_grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def _score_trade(
    equity: float,
    pos_pct_after: float,
    exp_after: float,
    cash_after: float,
    max_loss_pct: float,
    risk: RiskConfig,
    sizing: SizingConfig,
    has_stop: bool,
) -> tuple[int, list[str]]:
    score = 100
    warnings: list[str] = []

    if pos_pct_after > sizing.max_position_pct + 0.01:
        score -= 25
        warnings.append(f"预估仓位 {pos_pct_after:.0%} 超过单票上限 {sizing.max_position_pct:.0%}。")
    elif pos_pct_after > sizing.max_position_pct * 0.9:
        score -= 10
        warnings.append(f"预估仓位 {pos_pct_after:.0%} 接近单票上限。")

    if exp_after > sizing.max_total_exposure + 0.01:
        score -= 20
        warnings.append(f"预估总敞口 {exp_after:.0%} 超过上限 {sizing.max_total_exposure:.0%}。")

    if cash_after < sizing.cash_reserve_pct - 0.01:
        score -= 15
        warnings.append(f"预估现金比例 {cash_after:.0%} 低于保留要求 {sizing.cash_reserve_pct:.0%}。")

    if not has_stop:
        score -= 20
        warnings.append("未设置止损 — 无法量化最大亏损,不建议实盘。")
    elif risk.risk_per_trade and max_loss_pct > risk.risk_per_trade * 1.5:
        score -= 15
        warnings.append(f"预估最大亏损 {max_loss_pct:.1%} 超过单笔风险预算 {risk.risk_per_trade:.1%}。")

    if pos_pct_after > 0.5:
        score -= 15
        warnings.append("仓位超过净值 50%,接近全仓,抗风险能力弱。")

    return max(0, min(100, score)), warnings


def _loss_scenarios(
    equity: float,
    notional: float,
    price: float,
    risk: RiskConfig,
) -> list[dict]:
    scenarios = []
    if risk.stop_loss and price > 0:
        loss = notional * risk.stop_loss
        scenarios.append(
            {
                "name": "止损触发",
                "trigger": f"-{risk.stop_loss:.0%}",
                "loss": round(loss, 2),
                "loss_pct_equity": round(loss / equity, 4) if equity else 0,
            }
        )
    if risk.trailing_stop and price > 0:
        loss = notional * risk.trailing_stop
        scenarios.append(
            {
                "name": "移动止损(从峰值)",
                "trigger": f"-{risk.trailing_stop:.0%}",
                "loss": round(loss, 2),
                "loss_pct_equity": round(loss / equity, 4) if equity else 0,
            }
        )
    if risk.max_drawdown:
        loss = equity * risk.max_drawdown
        scenarios.append(
            {
                "name": "组合熔断",
                "trigger": f"回撤 {risk.max_drawdown:.0%}",
                "loss": round(loss, 2),
                "loss_pct_equity": round(risk.max_drawdown, 4),
            }
        )
    if risk.take_profit and price > 0:
        gain = notional * risk.take_profit
        scenarios.append(
            {
                "name": "止盈触发",
                "trigger": f"+{risk.take_profit:.0%}",
                "loss": round(-gain, 2),
                "loss_pct_equity": round(-gain / equity, 4) if equity else 0,
            }
        )
    return scenarios


def assess_trade(
    symbol: str,
    price: float,
    prices: pd.DataFrame,
    equity: float,
    cash: float,
    position_value: float = 0.0,
    order_size: float = 0.25,
    sizing: SizingConfig | None = None,
    risk: RiskConfig | None = None,
    commission: float = 0.0005,
    slippage: float = 0.0005,
    total_invested: float | None = None,
) -> TradeRiskAssessment:
    """Estimate risk for a hypothetical new long at `price`."""
    sizing = sizing or SizingConfig()
    risk = risk or RiskConfig()
    daily_vol, annual_vol = _vol_from_prices(prices)

    caps, binding = _entry_cap_breakdown(
        equity,
        cash,
        position_value,
        order_size,
        sizing,
        risk,
        total_invested,
    )
    notional = compute_entry_notional(
        equity,
        cash,
        position_value,
        order_size,
        sizing,
        risk,
    )
    exec_price = price * (1 + slippage)
    est_commission = notional * commission
    position_after = position_value + notional
    pos_pct_after = position_after / equity if equity else 0
    exp_after = position_after / equity if equity else 0
    cash_after = (cash - notional - est_commission) / equity if equity else 0

    max_loss = notional * risk.stop_loss if risk.stop_loss else 0.0
    max_loss_pct = max_loss / equity if equity else 0.0
    max_loss_trail = notional * risk.trailing_stop if risk.trailing_stop else 0.0
    var_1d = position_after * daily_vol * VAR_Z_95
    var_pct = var_1d / equity if equity else 0.0

    score, warnings = _score_trade(
        equity,
        pos_pct_after,
        exp_after,
        cash_after,
        max_loss_pct,
        risk,
        sizing,
        bool(risk.stop_loss),
    )
    if binding == "risk_based":
        warnings.append("风险定仓生效 — 按 stop_loss × risk_per_trade 限制仓位。")
    elif binding in ("max_position_pct", "max_total_exposure"):
        warnings.append(f"仓位受 {binding} 限制,未用满 order_size。")

    return TradeRiskAssessment(
        symbol=symbol,
        price=price,
        equity=equity,
        cash=cash,
        position_value=position_value,
        exposure_pct=position_value / equity if equity else 0,
        cash_pct=cash / equity if equity else 0,
        daily_vol=daily_vol,
        annual_vol=annual_vol,
        proposed_notional=round(notional, 2),
        proposed_position_pct=round(pos_pct_after, 4),
        exposure_pct_after=round(exp_after, 4),
        cash_pct_after=round(cash_after, 4),
        max_loss_at_stop=round(max_loss, 2),
        max_loss_pct=round(max_loss_pct, 4),
        max_loss_at_trailing=round(max_loss_trail, 2),
        var_95_1d=round(var_1d, 2),
        var_95_1d_pct=round(var_pct, 4),
        cap_breakdown={k: round(v, 2) for k, v in caps.items()},
        binding_cap=binding,
        risk_score=score,
        risk_grade=_risk_grade(score),
        warnings=warnings,
        scenarios=_loss_scenarios(equity, notional, price, risk),
    )


def assess_portfolio(
    prices_by_symbol: dict[str, pd.DataFrame],
    allocation: str = "equal",
    total_cash: float = 100_000.0,
    order_size: float = 0.25,
    sizing: SizingConfig | None = None,
    risk: RiskConfig | None = None,
) -> PortfolioRiskAssessment:
    """Estimate portfolio-level risk for planned multi-asset allocation."""
    sizing = sizing or SizingConfig()
    risk = risk or RiskConfig()
    weights = compute_portfolio_weights(prices_by_symbol, allocation, sizing)
    allocated_frac = sum(weights.values())
    idle_frac = 1.0 - allocated_frac

    per_symbol: dict = {}
    weighted_vol_sq = 0.0

    for sym, df in prices_by_symbol.items():
        w = weights.get(sym, 0)
        slice_cash = total_cash * w
        price = float(df["close"].iloc[-1])
        daily_vol, annual_vol = _vol_from_prices(df)
        trade = assess_trade(
            sym,
            price,
            df,
            total_cash,
            total_cash * idle_frac + slice_cash,
            position_value=0,
            order_size=order_size,
            sizing=sizing,
            risk=risk,
        )
        sym_var = slice_cash * daily_vol * VAR_Z_95
        weighted_vol_sq += (w * daily_vol) ** 2
        per_symbol[sym] = {
            "weight": round(w, 4),
            "allocated_cash": round(slice_cash, 2),
            "price": price,
            "daily_vol": round(daily_vol, 4),
            "annual_vol": round(annual_vol, 4),
            "proposed_notional": trade.proposed_notional,
            "max_loss_at_stop": trade.max_loss_at_stop,
            "var_95_1d": round(sym_var, 2),
            "risk_grade": trade.risk_grade,
            "risk_score": trade.risk_score,
        }

    port_daily_vol = float(np.sqrt(weighted_vol_sq))
    port_var = total_cash * port_daily_vol * VAR_Z_95
    hhi = sum(w**2 for w in weights.values())

    score = 100
    warnings: list[str] = []
    if idle_frac < sizing.cash_reserve_pct - 0.01:
        score -= 10
        warnings.append(f"组合分配后闲置现金 {idle_frac:.0%} 低于保留线。")
    if hhi > 0.35:
        score -= 15
        warnings.append(f"集中度偏高 (HHI={hhi:.2f}),分散不足。")
    if max(weights.values(), default=0) > sizing.max_weight_per_symbol + 0.01:
        score -= 15
        warnings.append("存在单票权重超限。")
    grade_rank = {"A": 4, "B": 3, "C": 2, "D": 1}
    worst = min((p["risk_grade"] for p in per_symbol.values()), key=lambda g: grade_rank.get(g, 0), default="A")
    if worst in ("C", "D"):
        score -= 10
        warnings.append("部分标的风险评级偏低,建议复核参数。")

    score = max(0, min(100, score))
    return PortfolioRiskAssessment(
        symbols=list(prices_by_symbol),
        allocation=allocation,
        total_cash=total_cash,
        allocated_pct=round(allocated_frac, 4),
        idle_cash_pct=round(idle_frac, 4),
        weights={k: round(v, 4) for k, v in weights.items()},
        per_symbol=per_symbol,
        portfolio_daily_vol=round(float(port_daily_vol), 4),
        portfolio_var_95_1d=round(float(port_var), 2),
        portfolio_var_95_1d_pct=round(float(port_var / total_cash), 4) if total_cash else 0,
        concentration_hhi=round(hhi, 4),
        risk_score=score,
        risk_grade=_risk_grade(score),
        warnings=warnings,
    )


def assess_backtest_result(result, equity_start: float, risk: RiskConfig | None = None) -> dict:
    """Post-backtest risk summary from fills and equity curve."""
    risk = risk or RiskConfig()
    fills = result.portfolio.fills
    buys = [f for f in fills if f.side == "BUY"]
    curve = result.equity_curve

    avg_notional = sum(f.qty * f.price for f in buys) / len(buys) if buys else 0.0
    avg_eq = float(curve.mean()) if len(curve) else equity_start
    max_dd = result.stats.get("max_drawdown", 0.0)
    ann_vol = result.stats.get("annual_vol", 0.0)
    max_pos_pct = avg_notional / avg_eq if avg_eq else 0
    daily_vol = ann_vol / np.sqrt(TRADING_DAYS) if ann_vol else 0
    var_est = avg_eq * daily_vol * VAR_Z_95

    warnings = []
    if max_pos_pct > 0.35:
        warnings.append(f"回测平均仓位 {max_pos_pct:.0%} 偏高。")
    if max_dd < -0.25:
        warnings.append(f"历史最大回撤 {max_dd:.0%} 较深。")
    if not result.risk_events:
        warnings.append("回测期间无风控触发,实盘需确认止损已启用。")
    if risk.stop_loss and max_pos_pct > 0:
        est_loss = avg_notional * risk.stop_loss
        if risk.risk_per_trade and avg_eq and est_loss / avg_eq > risk.risk_per_trade * 1.2:
            warnings.append(
                f"平均仓位止损亏损约 ${est_loss:,.0f} ({est_loss / avg_eq:.1%}),"
                f" 超过风险预算 {risk.risk_per_trade:.1%}。"
            )

    return {
        "avg_position_pct": round(max_pos_pct, 4),
        "avg_notional": round(avg_notional, 2),
        "max_drawdown": round(max_dd, 4),
        "estimated_var_95_1d": round(var_est, 2),
        "estimated_var_95_1d_pct": round(var_est / avg_eq, 4) if avg_eq else 0,
        "n_trades": len(buys),
        "risk_events": len(result.risk_events or []),
        "warnings": warnings,
    }


def assessment_to_dict(obj) -> dict:
    return asdict(obj)
