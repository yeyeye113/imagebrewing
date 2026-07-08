"""Advisor: turns a backtest result into actionable, human-readable guidance.

It combines (1) quantitative checks on the result with (2) a curated set of
principles distilled from top discretionary and systematic traders. The goal is
to flag the mistakes that most often blow up retail accounts: no risk control,
over-trading, curve-fitting, and chasing strategies that merely track the index.

Nothing here is financial advice — it's a disciplined checklist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .engine.metrics import trade_stats


@dataclass
class Tip:
    level: str       # "good" | "info" | "warn" | "risk"
    message: str


# Timeless principles from the trading greats — shown alongside the diagnostics.
PRINCIPLES = [
    "保住本金第一,盈利第二。先想能亏多少,再想能赚多少。(风险管理优先)",
    "截断亏损,让利润奔跑 (Cut losses short, let winners run) —— 海龟法则核心。",
    "单笔风险控制在总资金的 1%–2% 以内,一次亏损绝不能伤筋动骨。",
    "永远带止损进场。没有退出计划的仓位等于裸奔。",
    "不要逆势重仓抄底/摸顶,趋势的力量远超你的判断。",
    "过度交易是账户杀手:手续费和情绪会吃掉你的优势。",
    "回测漂亮 ≠ 实盘能赚。警惕参数过拟合,务必留样本外/前进式检验。",
    "跑不赢买入持有的主动策略,不如直接持有指数。要有正的超额收益。",
    "情绪是敌人:贪婪时减仓,恐惧时别割在地板。机械执行你的系统。",
    "分散与仓位管理比选股更决定长期生死。",
    "永远不要满仓梭哈:保留现金缓冲,单票仓位有上限,才能扛过连续回撤。",
]

TRADER_TACTICS = [
    {"author": "杰西·利弗莫尔", "rule": "只在趋势确认后加仓；第一次试探仓要小，对了再加。", "apply": "short"},
    {"author": "理查德·丹尼斯 (海龟)", "rule": "突破 20 日高点做多，ATR 止损；单笔风险 ≤ 账户 2%。", "apply": "short"},
    {"author": "马克·米勒维尼", "rule": "只买 Stage 2 上升趋势、RS 领先的强势股；弱势市场少动。", "apply": "both"},
    {"author": "尼古拉斯· Darvas", "rule": "股价创新高且成交量配合时买入，跌破箱底严格止损。", "apply": "short"},
    {"author": "威廉·欧奈尔 (CAN SLIM)", "rule": "EPS 加速 + 行业龙头 + 机构增持；7–8% 止损绝不犹豫。", "apply": "long"},
    {"author": "保罗·都铎·琼斯", "rule": "防守赢得冠军：每笔交易先定义最大亏损，再谈盈利目标。", "apply": "both"},
    {"author": "埃德·塞柯塔", "rule": "系统一致执行；Cut losses, ride winners — 盈亏比 > 胜率。", "apply": "both"},
    {"author": "斯坦利·德鲁肯米勒", "rule": "集中火力于高确信度机会；趋势对时敢于重仓，错了快速认错。", "apply": "long"},
    {"author": "彼得·林奇", "rule": "买你看得懂的成长故事；PEG<1.5，业绩加速期介入。", "apply": "long"},
    {"author": "沃伦·巴菲特", "rule": "以合理价格买伟大公司；护城河 + 现金流，少交易多持有。", "apply": "long"},
    {"author": "詹姆斯·西蒙斯", "rule": "统计优势 + 严格风控；小 edge 高频复利，拒绝主观情绪。", "apply": "both"},
    {"author": "乔治·索罗斯", "rule": "反身性：趋势自我强化时顺势，拐点出现果断反手。", "apply": "short"},
    {"author": "雷·达里奥", "rule": "全天候思维：分散 + 风险平价，先问「我错在哪里」。", "apply": "long"},
    {"author": "拉尔夫·文斯", "rule": "最优 f 与仓位管理；Kelly 分数下注，绝不让一次亏损致命。", "apply": "both"},
]

# 高胜率打法 + match 规则（strategy_journal 自动匹配、日志验证、动态优选）
# 值为混合类型 (str/float/dict/list), 显式标注避免推断成 dict[str, object]
HIGH_WIN_RATE_PLAYBOOKS: list[dict[str, Any]] = [
    {"id": "opening_breakout", "name": "开盘突破动量", "trader_id": "turtle", "trader_name": "理查德·丹尼斯 (海龟)", "source": "海龟 + 利弗莫尔", "historical_win_rate": 0.58, "payoff_ratio": 2.1, "horizon": "short", "time_slots": ["09:30-10:00", "13:00-13:30"], "time_allocation": {"active_trading": 0.35, "observation": 0.25, "cash": 0.40}, "match": {"signal": "BUY", "min_tech_score": 72, "min_win_rates": {"win_rate_3d": 0.52}, "min_confidence": 0.55}, "rules": ["开盘 30 分钟内只做高综合分标的", "突破前日高点 + 量能放大才进场", "止损 5%，对了移动止盈"]},
    {"id": "midday_pullback", "name": "午盘回踩低吸", "trader_id": "minervini", "trader_name": "马克·米勒维尼", "source": "米勒维尼 Stage2", "historical_win_rate": 0.54, "payoff_ratio": 1.8, "horizon": "short", "time_slots": ["10:30-11:20", "14:00-14:40"], "time_allocation": {"active_trading": 0.25, "observation": 0.35, "cash": 0.40}, "match": {"signal": "BUY", "min_tech_score": 78, "min_win_rates": {"win_rate_5d": 0.52}}, "rules": ["tech_score≥78 且 5日胜率≥52%", "回踩均线企稳再加仓", "不追涨停"]},
    {"id": "close_momentum", "name": "尾盘趋势延续", "trader_id": "darvas", "trader_name": "尼古拉斯· Darvas", "source": "Darvas + 都铎·琼斯", "historical_win_rate": 0.56, "payoff_ratio": 1.9, "horizon": "short", "time_slots": ["14:30-15:00"], "time_allocation": {"active_trading": 0.30, "observation": 0.20, "cash": 0.50}, "match": {"signal": "BUY", "min_tech_score": 75, "min_win_rates": {"win_rate_7d": 0.52}, "prediction_contains": "prediction_7d", "prediction_text": "涨"}, "rules": ["14:40 后不开新仓", "7日看涨才过夜", "单票 ≤ 15%"]},
    {"id": "weekly_swing", "name": "周线波段持有", "trader_id": "oneil", "trader_name": "威廉·欧奈尔", "source": "CAN SLIM", "historical_win_rate": 0.62, "payoff_ratio": 2.5, "horizon": "long", "time_slots": ["周一 09:45-10:30", "周五 14:00-14:30"], "time_allocation": {"active_trading": 0.20, "hold": 0.55, "cash": 0.25}, "match": {"signal": "BUY", "min_tech_score": 80, "min_win_rates": {"win_rate_30d": 0.52}, "horizon_best": "long"}, "rules": ["30日/1月胜率双确认", "综合分≥85 主力仓", "8% 止损"]},
    {"id": "monthly_core", "name": "月度核心配置", "trader_id": "druckenmiller", "trader_name": "斯坦利·德鲁肯米勒", "source": "德鲁肯米勒 + 塞柯塔", "historical_win_rate": 0.65, "payoff_ratio": 3.0, "horizon": "long", "time_slots": ["每月第一个交易日"], "time_allocation": {"core_hold": 0.60, "tactical": 0.15, "cash": 0.25}, "match": {"signal": "BUY", "min_tech_score": 82, "min_confidence": 0.75, "min_win_rates": {"win_rate_30d": 0.55}}, "rules": ["1月预测 + 技术分双确认", "最多 5 只核心", "每月复盘迭代"]},
    {"id": "livermore_pivot", "name": "利弗莫尔关键点", "trader_id": "livermore", "trader_name": "杰西·利弗莫尔", "source": "利弗莫尔", "historical_win_rate": 0.57, "payoff_ratio": 2.3, "horizon": "short", "time_slots": ["09:35-10:15", "14:00-14:45"], "time_allocation": {"active_trading": 0.40, "observation": 0.20, "cash": 0.40}, "match": {"signal": "BUY", "min_tech_score": 76, "min_win_rates": {"win_rate_3d": 0.54}, "min_confidence": 0.60}, "rules": ["关键点突破才加仓", "试探仓 ≤ 5%", "错了立刻砍"]},
    {"id": "lynch_growth", "name": "林奇成长故事", "trader_id": "lynch", "trader_name": "彼得·林奇", "source": "彼得·林奇", "historical_win_rate": 0.60, "payoff_ratio": 2.2, "horizon": "long", "time_slots": ["财报季", "周中低波动"], "time_allocation": {"research": 0.30, "hold": 0.50, "cash": 0.20}, "match": {"signal": "BUY", "min_tech_score": 74, "min_win_rates": {"win_rate_30d": 0.50}, "horizon_best": "long"}, "rules": ["买看得懂的成长", "业绩加速期介入", "少因波动卖出"]},
    {"id": "buffett_quality", "name": "巴菲特质量价值", "trader_id": "buffett", "trader_name": "沃伦·巴菲特", "source": "巴菲特", "historical_win_rate": 0.63, "payoff_ratio": 2.8, "horizon": "long", "time_slots": ["季度调仓", "大跌后分批"], "time_allocation": {"core_hold": 0.70, "tactical": 0.10, "cash": 0.20}, "match": {"signal": "BUY", "min_tech_score": 78, "min_win_rates": {"win_rate_30d": 0.55}, "min_confidence": 0.65}, "rules": ["高综合分 + 低回撤", "有基本面才越跌越买", "长期持有"]},
    {"id": "simons_quant", "name": "西蒙斯量化共振", "trader_id": "simons", "trader_name": "詹姆斯·西蒙斯", "source": "文艺复兴", "historical_win_rate": 0.59, "payoff_ratio": 1.7, "horizon": "short", "time_slots": ["高流动性时段"], "time_allocation": {"active_trading": 0.45, "observation": 0.15, "cash": 0.40}, "match": {"signal": "BUY", "min_tech_score": 70, "min_win_rates": {"win_rate_3d": 0.50, "win_rate_7d": 0.50}, "min_confidence": 0.50}, "rules": ["多因子共振才出手", "小 edge 高频", "拒绝主观 override"]},
    {"id": "soros_reflexivity", "name": "索罗斯反身性", "trader_id": "soros", "trader_name": "乔治·索罗斯", "source": "索罗斯", "historical_win_rate": 0.55, "payoff_ratio": 2.0, "horizon": "short", "time_slots": ["趋势加速期"], "time_allocation": {"active_trading": 0.35, "observation": 0.35, "cash": 0.30}, "match": {"signal": "BUY", "min_tech_score": 73, "prediction_contains": "prediction_5d", "prediction_text": "涨"}, "rules": ["趋势自我强化时顺势", "拐点快速减仓", "宏观共振"]},
    {"id": "dalio_allweather", "name": "达里奥全天候", "trader_id": "dalio", "trader_name": "雷·达里奥", "source": "桥水", "historical_win_rate": 0.61, "payoff_ratio": 1.6, "horizon": "long", "time_slots": ["月度再平衡"], "time_allocation": {"core_hold": 0.55, "hedge": 0.20, "cash": 0.25}, "match": {"signal": "BUY", "min_tech_score": 72, "min_win_rates": {"win_rate_30d": 0.48}}, "rules": ["分散 + 风险平价", "不因单一预测 all-in", "定期再平衡"]},
    {"id": "seycota_system", "name": "塞柯塔系统执行", "trader_id": "seycota", "trader_name": "埃德·塞柯塔", "source": "塞柯塔", "historical_win_rate": 0.57, "payoff_ratio": 2.4, "horizon": "both", "time_slots": ["信号触发即执行"], "time_allocation": {"active_trading": 0.30, "hold": 0.40, "cash": 0.30}, "match": {"signal": "BUY", "min_confidence": 0.70, "min_tech_score": 74}, "rules": ["机械执行", "盈亏比 > 胜率", "连亏降仓不停系统"]},
    {"id": "jones_defense", "name": "都铎防守反击", "trader_id": "tudor", "trader_name": "保罗·都铎·琼斯", "source": "都铎·琼斯", "historical_win_rate": 0.58, "payoff_ratio": 2.1, "horizon": "short", "time_slots": ["14:00-15:00"], "time_allocation": {"active_trading": 0.25, "observation": 0.35, "cash": 0.40}, "match": {"signal": "BUY", "min_tech_score": 77, "min_confidence": 0.68, "min_win_rates": {"win_rate_7d": 0.51}}, "rules": ["先定义最大亏损", "不对抗宏观逆风", "防守赢得冠军"]},
]


def get_playbook_by_id(playbook_id: str) -> dict | None:
    for p in HIGH_WIN_RATE_PLAYBOOKS:
        if p["id"] == playbook_id:
            return p
    return None


def playbooks_for_horizon(horizon: str) -> list[dict]:
    h = horizon.lower()
    if h in ("blend", "both"):
        return HIGH_WIN_RATE_PLAYBOOKS
    return [p for p in HIGH_WIN_RATE_PLAYBOOKS if p["horizon"] in (h, "both") or h == "blend"]


def time_allocation_summary(horizon: str) -> dict:
    """聚合推荐时间分配比例."""
    books = playbooks_for_horizon(horizon)
    if not books:
        return {"active_trading": 0.25, "observation": 0.25, "hold": 0.30, "cash": 0.20}
    keys: dict[str, list[float]] = {}
    for b in books:
        for k, v in b.get("time_allocation", {}).items():
            keys.setdefault(k, []).append(float(v))
    return {k: round(sum(vs) / len(vs), 2) for k, vs in keys.items()}


def merge_playbook_allocation(
    template: dict[str, float],
    playbook: dict | None,
    *,
    blend: float = 0.55,
) -> dict[str, float]:
    """将策略模板仓位与高手打法 time_allocation 混合."""
    if not playbook:
        return dict(template)
    ta = playbook.get("time_allocation") or {}
    if not ta:
        return dict(template)

    active = float(ta.get("active_trading", 0)) + float(ta.get("tactical", 0))
    hold = float(ta.get("hold", 0)) + float(ta.get("core_hold", 0)) + float(ta.get("research", 0))
    cash = float(ta.get("cash", 0)) + float(ta.get("observation", 0)) * 0.5
    pb_main = active + hold * 0.35
    pb_stable = hold * 0.65
    pb_cash = max(cash, 0.10)
    s = pb_main + pb_stable + pb_cash
    if s <= 0:
        return dict(template)
    pb_main, pb_stable, pb_cash = pb_main / s, pb_stable / s, pb_cash / s

    out = {
        "main": template.get("main", 0.5) * (1 - blend) + pb_main * blend,
        "stable": template.get("stable", 0.3) * (1 - blend) + pb_stable * blend,
        "cash": template.get("cash", 0.2) * (1 - blend) + pb_cash * blend,
    }
    total = sum(out.values()) or 1.0
    return {k: round(v / total, 3) for k, v in out.items()}


def tactics_for_horizon(horizon: str) -> list[dict]:
    h = horizon.lower()
    return [t for t in TRADER_TACTICS if t["apply"] in (h, "both")]


def invest_advice_for_symbol(
    symbol: str,
    name: str,
    horizon: str,
    tech_score: float,
    short_pred: str,
    long_pred: str,
    confidence: float,
) -> list[str]:
    lines: list[str] = []
    if horizon == "short":
        lines.append(f"【短线】{symbol} {name}：技术分 {tech_score:.0f}，3–7日 {short_pred}。")
        lines.append("高置信度 → 小仓试探，严格 5–8% 止损。" if confidence >= 0.85 else "置信度一般 → 减半仓位或观望。")
    else:
        lines.append(f"【长线】{symbol} {name}：技术分 {tech_score:.0f}，30日 {long_pred}。")
        lines.append("技术结构强 → 分批建仓，移动止盈。" if tech_score >= 80 else "等待更深回调或二次确认后再介入。")
    for t in tactics_for_horizon(horizon)[:2]:
        lines.append(f"· {t['author']}：{t['rule']}")
    return lines


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def advise(result, buy_and_hold: float | None = None) -> list[Tip]:
    """Produce a list of Tips from a BacktestResult."""
    tips: list[Tip] = []
    s = result.stats or {}
    ts = trade_stats(result.portfolio.fills)

    sharpe = s.get("sharpe", 0.0)
    max_dd = s.get("max_drawdown", 0.0)
    total_ret = s.get("total_return", 0.0)
    n_rt = ts.get("n_round_trips", 0)

    # --- Risk-adjusted return ------------------------------------------------
    if sharpe >= 1.5:
        tips.append(Tip("good", f"夏普 {sharpe:.2f} 很优秀,风险调整后收益强。"))
    elif sharpe >= 1.0:
        tips.append(Tip("info", f"夏普 {sharpe:.2f} 合格 (>1),但仍有提升空间。"))
    elif sharpe >= 0:
        tips.append(Tip("warn", f"夏普 {sharpe:.2f} 偏低,承担的波动没换来足够回报。"))
    else:
        tips.append(Tip("risk", f"夏普为负 ({sharpe:.2f}),策略在亏损,先别上实盘。"))

    # --- Drawdown / capital preservation ------------------------------------
    if max_dd <= -0.30:
        tips.append(Tip("risk", f"最大回撤 {_pct(max_dd)} 过大,实盘很难扛住。强烈建议加止损/降仓位。"))
    elif max_dd <= -0.20:
        tips.append(Tip("warn", f"最大回撤 {_pct(max_dd)} 偏深,考虑止损或减小单笔仓位。"))
    else:
        tips.append(Tip("good", f"最大回撤 {_pct(max_dd)} 控制得不错。"))

    if not getattr(result, "risk_events", None):
        tips.append(Tip("warn", "本次回测没有任何风控触发——确认你设置了止损 (stop_loss/trailing_stop)。"))
    else:
        n_ev = len(result.risk_events)
        tips.append(Tip("info", f"风控共触发 {n_ev} 次(止损/止盈/熔断),说明纪律在起作用。"))

    # --- Benchmark (alpha) ---------------------------------------------------
    if buy_and_hold is not None:
        if total_ret > buy_and_hold:
            tips.append(Tip("good", f"跑赢买入持有 ({_pct(total_ret)} vs {_pct(buy_and_hold)}),有正超额收益。"))
        else:
            tips.append(Tip("warn", f"没跑赢买入持有 ({_pct(total_ret)} vs {_pct(buy_and_hold)}),主动交易暂无优势。"))

    # --- Trade behaviour -----------------------------------------------------
    n_bars = len(result.equity_curve)
    if n_rt == 0:
        tips.append(Tip("warn", "没有任何完整交易,样本不足,结论不可靠。"))
    else:
        if n_bars and n_rt > n_bars / 5:
            tips.append(Tip("warn", f"交易过于频繁 ({n_rt} 笔),小心手续费和滑点侵蚀收益。"))
        wr = ts.get("win_rate")
        payoff = ts.get("payoff_ratio")
        if wr is not None:
            tips.append(Tip("info", f"胜率 {_pct(wr)},盈亏比 {payoff:.2f}。"
                                    " 低胜率没关系,只要盈亏比够高(让利润奔跑)。"))
        pf = ts.get("profit_factor")
        if pf is not None and pf != float("inf") and pf < 1.2:
            tips.append(Tip("warn", f"盈利因子 {pf:.2f} 偏低 (<1.2),策略边际很薄,实盘易转亏。"))

    if n_rt and n_rt < 20:
        tips.append(Tip("warn", f"完整交易仅 {n_rt} 笔,样本太小,易过拟合;拉长周期或多标的验证。"))

    # --- Position sizing discipline ------------------------------------------
    buys = [f for f in result.portfolio.fills if f.side == "BUY"]
    if buys and result.equity_curve is not None and len(result.equity_curve):
        avg_notional = sum(f.qty * f.price for f in buys) / len(buys)
        avg_eq = float(result.equity_curve.mean())
        if avg_eq > 0:
            avg_pct = avg_notional / avg_eq
            if avg_pct > 0.50:
                tips.append(Tip("risk", f"平均单笔仓位约 {_pct(avg_pct)},接近全仓,建议启用 sizing 限制(单票≤30%,保留现金≥20%)。"))
            elif avg_pct > 0.35:
                tips.append(Tip("warn", f"平均单笔仓位约 {_pct(avg_pct)},偏高;配合止损与 max_position_pct 更稳健。"))
            else:
                tips.append(Tip("good", f"平均单笔仓位约 {_pct(avg_pct)},仓位控制合理。"))

    return tips


def format_tips(tips: list[Tip]) -> str:
    icon = {"good": "[+]", "info": "[i]", "warn": "[!]", "risk": "[X]"}
    lines = [f"  {icon.get(t.level, '[-]')} {t.message}" for t in tips]
    return "\n".join(lines)


def format_principles() -> str:
    return "\n".join(f"  - {p}" for p in PRINCIPLES)
