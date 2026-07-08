"""新闻二次确认 + 期货黑天鹅冲击预设。

股票: 新闻情绪 vs LLM信号 交叉验证
期货: 预设8类大新闻冲击场景 → 波动率/方向/影响品种

作为 forecast 流程的补充步骤，在 LLM 决策后执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ══════════════════════════════════════════════════════════════════
# 新闻二次确认
# ══════════════════════════════════════════════════════════════════


@dataclass
class NewsConfirm:
    """新闻 vs LLM 信号 交叉验证结果。"""

    symbol: str
    news_sentiment: str  # bullish / bearish / neutral
    news_score: float  # -1.0 to +1.0
    llm_signal: str  # BUY / SELL / HOLD
    llm_confidence: float
    aligned: bool  # 新闻和LLM方向一致?
    conflict_level: str  # "none" | "mild" | "severe"
    advice: str  # 建议调整


def cross_validate(
    symbol: str,
    news_sentiment: str,
    news_score: float,
    llm_signal: str,
    llm_confidence: float,
) -> NewsConfirm:
    """新闻情绪 vs LLM 信号 交叉验证。

    一致 → 通过
    新闻空但LLM多 → 警��（可能被新闻情绪带动）
    新闻多但LLM空 → 警告（可能错过反转）
    """
    # 新闻方向
    news_dir = 1 if news_sentiment in ("bullish", "吉") else (-1 if news_sentiment in ("bearish", "凶") else 0)
    # LLM方向
    llm_dir = 1 if llm_signal in ("BUY", "LONG") else (-1 if llm_signal in ("SELL", "SHORT") else 0)

    conflict = "none"
    advice = ""

    if llm_dir == 0:
        # LLM说观望 → 新闻方向不重要
        conflict = "none"
        advice = "信号观望，新闻仅供参考"
    elif news_dir == llm_dir and news_dir != 0:
        # 同向 → 最佳
        conflict = "none"
        advice = "✅ 新闻与LLM同向确认，可适度提高置信度"
    elif news_dir == -llm_dir and llm_dir != 0 and abs(news_score) > 0.3:
        # 反向且新闻情绪强 → 严重冲突
        conflict = "severe"
        if llm_dir == 1:
            advice = f"⚠️ LLM看多但新闻偏空({news_score:+.2f})，建议减仓或设更紧止损"
        else:
            advice = f"⚠️ LLM看空但新闻偏多({news_score:+.2f})，可能是反弹陷阱，建议观望"
    elif news_dir == -llm_dir:
        conflict = "mild"
        advice = "📌 新闻与LLM方向相反但信号不强，按LLM为准但注意反转"
    elif news_dir == 0:
        conflict = "none"
        advice = "新闻中性，LLM信号独立判断"
    else:
        conflict = "none"
        advice = ""

    return NewsConfirm(
        symbol=symbol,
        news_sentiment=news_sentiment,
        news_score=news_score,
        llm_signal=llm_signal,
        llm_confidence=llm_confidence,
        aligned=(conflict == "none" and llm_dir != 0),
        conflict_level=conflict,
        advice=advice,
    )


# ══════════════════════════════════════════════════════════════════
# 期货黑天鹅冲击预设
# ══════════════════════════════════════════════════════════════════


@dataclass
class ShockScenario:
    """一个预设的黑天鹅/大新闻冲击场景。"""

    id: str
    category: str  # geo / macro / supply / weather / policy
    title: str  # 场景名称
    probability: str  # "low" / "medium" / "high" (主观概率)
    volatility_multiplier: float  # 波动率放大倍数
    direction: str  # "bullish" / "bearish" / "both"
    affected_codes: list[str]  # 受影响的期货品种
    duration_days: int  # 预计影响天数
    description: str  # 场景描述 + 应对建议

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "probability": self.probability,
            "volatility_multiplier": self.volatility_multiplier,
            "direction": self.direction,
            "affected_codes": self.affected_codes,
            "duration_days": self.duration_days,
            "description": self.description,
        }


# 预设冲击场景库
_SHOCK_SCENARIOS: list[ShockScenario] = [
    ShockScenario(
        id="fed_hike",
        category="macro",
        title="美联储超预期加息/降息",
        probability="medium",
        volatility_multiplier=3.0,
        direction="both",
        affected_codes=["AU", "AG", "CU", "SC", "IF", "T"],
        duration_days=3,
        description="利率变动引发全球资产重定价。贵金属(金银)首当其冲，有色金属(铜)受需求预期影响，原油跟跌。建议: 降息→做多贵金属; 加息→做空有色。波动率3倍，仓位减半。",
    ),
    ShockScenario(
        id="opec_cut",
        category="supply",
        title="OPEC+ 意外减产/增产",
        probability="medium",
        volatility_multiplier=4.0,
        direction="bullish",
        affected_codes=["SC", "FU", "BU", "PG", "TA", "MA"],
        duration_days=5,
        description="原油供给端突发变化。SC为首，能源化工链(燃料油/沥青/LPG/PTA/甲醇)全线跟动。减产→做多SC+化工链; 增产→做空。波动率4倍，注意夜盘跳空。",
    ),
    ShockScenario(
        id="usda_surprise",
        category="supply",
        title="USDA 报告大幅调整库存/单产",
        probability="medium",
        volatility_multiplier=2.5,
        direction="both",
        affected_codes=["M", "A", "B", "Y", "P", "OI", "RM", "C"],
        duration_days=3,
        description="USDA月度供需报告(每月10日左右)意外调整美国/全球大豆玉米库存或单产数据。豆粕/豆油/棕榈油/菜粕全线波动。降库存→做多; 增库存→做空。波动率2.5倍。",
    ),
    ShockScenario(
        id="china_policy",
        category="policy",
        title="中国发改委/工信部突发调控",
        probability="high",
        volatility_multiplier=2.0,
        direction="bearish",
        affected_codes=["I", "RB", "HC", "SA", "TA", "MA", "C"],
        duration_days=5,
        description="监管部门对铁矿石/螺纹钢/纯碱等品种价格异常波动发声或出台措施。通常利空，短期打压多头情绪。建议: 减仓规避，政策明确后再入场。波动率2倍。",
    ),
    ShockScenario(
        id="typhoon_port",
        category="weather",
        title="强台风/洪水冲击港口和产区",
        probability="low",
        volatility_multiplier=2.0,
        direction="both",
        affected_codes=["RU", "P", "OI", "CF", "SR", "AP", "CJ"],
        duration_days=3,
        description="台风登陆影响海南/广东/广西橡胶产区或棕榈油进口港。短期供应受阻→利多。但影响通常3-5天消退。建议: 短线跟进，不追高。波动率2倍。",
    ),
    ShockScenario(
        id="war_geo",
        category="geo",
        title="地缘冲突升级 (中东/台海/俄乌)",
        probability="low",
        volatility_multiplier=5.0,
        direction="both",
        affected_codes=["SC", "AU", "AG", "CU", "FU", "IF"],
        duration_days=7,
        description="地缘冲突→避险情绪飙升。原油(中东)暴涨，黄金(避险)暴涨，股指(风险资产)暴跌。波动率5倍，极度危险。建议: 轻仓或空仓，等局势明朗。做多贵金属+原油，做空股指。",
    ),
    ShockScenario(
        id="covid_lockdown",
        category="macro",
        title="大规模疫情/封锁",
        probability="low",
        volatility_multiplier=3.0,
        direction="bearish",
        affected_codes=["SC", "CU", "IF", "RU", "P", "M"],
        duration_days=10,
        description="疫情封锁→需求崩塌。原油/铜/橡胶等工业品首当其冲，股指跟跌。农产品相对抗跌(刚需)。建议: 做空工业品+股指，农产品观望。波动率3倍。",
    ),
    ShockScenario(
        id="mine_accident",
        category="supply",
        title="大型矿山事故/停产",
        probability="low",
        volatility_multiplier=3.0,
        direction="bullish",
        affected_codes=["I", "CU", "NI", "SN", "SI", "LC"],
        duration_days=5,
        description="主要矿山(铁矿石/铜/镍/锡/锂)发生事故或被迫停产。短期供给紧张→价格跳涨。建议: 追多但设紧止损，供给恢复后可能快速回落。波动率3倍。",
    ),
]


def get_shocks(active_only: bool = True) -> list[ShockScenario]:
    """获取冲击场景列表。"""
    if active_only:
        # 返回概率为medium/high的
        return [s for s in _SHOCK_SCENARIOS if s.probability in ("high", "medium")]
    return list(_SHOCK_SCENARIOS)


def get_shocks_for_code(code: str) -> list[ShockScenario]:
    """获取影响指定品种的冲击场景。"""
    code_upper = code.upper()
    return [s for s in _SHOCK_SCENARIOS if code_upper in s.affected_codes]


def format_shock_alert(shocks: list[ShockScenario], code: str) -> str:
    """格式化冲击预警文本。"""
    if not shocks:
        return ""

    lines = [f"⚡ 预设冲击预警 ({code}):"]
    for s in shocks[:3]:
        prob_icon = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(s.probability, "⚪")
        dir_icon = {"bullish": "📈", "bearish": "📉", "both": "↕️"}.get(s.direction, "❓")
        lines.append(f"  {prob_icon} {s.title} [{s.category}] {dir_icon}")
        lines.append(f"     波动率×{s.volatility_multiplier:.0f} | 影响{s.duration_days}天 | {s.description[:80]}...")

    return "\n".join(lines)


def all_shocks_summary() -> str:
    """所有冲击场景摘要。"""
    lines = ["⚡ 期货黑天鹅冲击预设 (8类场景):", ""]
    for s in _SHOCK_SCENARIOS:
        prob = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(s.probability, "⚪")
        lines.append(f"  {prob} [{s.category:7s}] {s.title}")
        lines.append(
            f"     波动率×{s.volatility_multiplier:.0f} | {s.direction:8s} | "
            f"影响{s.duration_days}天 | {','.join(s.affected_codes[:5])}"
        )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# API 接口用
# ══════════════════════════════════════════════════════════════════


def news_cross_check(
    symbol: str, news_sentiment: str, news_score: float, llm_signal: str, llm_confidence: float
) -> dict[str, Any]:
    """股票+期货通用的新闻交叉验证接口。"""
    nc = cross_validate(symbol, news_sentiment, news_score, llm_signal, llm_confidence)
    return {
        "symbol": nc.symbol,
        "news_sentiment": nc.news_sentiment,
        "news_score": nc.news_score,
        "llm_signal": nc.llm_signal,
        "llm_confidence": nc.llm_confidence,
        "aligned": nc.aligned,
        "conflict_level": nc.conflict_level,
        "advice": nc.advice,
    }


def shock_check(code: str) -> dict[str, Any]:
    """检查某个期货品种是否在冲击预设中。"""
    shocks = get_shocks_for_code(code)
    return {
        "code": code,
        "shock_count": len(shocks),
        "max_volatility": max((s.volatility_multiplier for s in shocks), default=1.0),
        "active_shocks": [s.to_dict() for s in shocks],
        "alert_text": format_shock_alert(shocks, code),
    }
