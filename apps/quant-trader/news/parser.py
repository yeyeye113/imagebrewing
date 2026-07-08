"""Rule-based financial news sentiment parser (CN + EN keywords).

Lightweight — no NLP model required. External AI can replace/augment via the
`/news/analyze` endpoint by posting custom text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BULLISH = [
    "上涨",
    "利好",
    "突破",
    "增长",
    "盈利",
    "超预期",
    "回购",
    "增持",
    "创新高",
    "反弹",
    "景气",
    "扩产",
    "签约",
    "中标",
    "分红",
    "复苏",
    "强劲",
    "surge",
    "rally",
    "beat",
    "upgrade",
    "bullish",
    "growth",
    "profit",
    "record high",
    "outperform",
    "buy",
    "strong",
]
BEARISH = [
    "下跌",
    "利空",
    "下滑",
    "亏损",
    "暴雷",
    "减持",
    "调查",
    "处罚",
    "退市",
    "违约",
    "裁员",
    "下调",
    "警示",
    "质押",
    "爆仓",
    "诉讼",
    "风险",
    "crash",
    "plunge",
    "miss",
    "downgrade",
    "bearish",
    "loss",
    "warning",
    "fraud",
    "investigation",
    "sell",
    "weak",
]
SHORT_TERM = ["今日", "盘中", "短线", "涨停", "跌停", "开盘", "收盘", "intraday", "today"]
LONG_TERM = ["战略", "五年", "长期", "产业", "规划", "并购", "重组", "annual", "long-term"]


@dataclass
class SentimentResult:
    score: float  # -1 .. +1
    label: str  # bullish | bearish | neutral
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    keywords: list[str] = field(default_factory=list)
    summary: str = ""


def _tokenize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def analyze_text(text: str) -> SentimentResult:
    t = _tokenize(text)
    if not t:
        return SentimentResult(0.0, "neutral", summary="无文本")

    bull = [k for k in BULLISH if k.lower() in t]
    bear = [k for k in BEARISH if k.lower() in t]
    nb, ns = len(bull), len(bear)

    if nb == 0 and ns == 0:
        score, label = 0.0, "neutral"
    else:
        score = max(-1.0, min(1.0, (nb - ns) / max(nb + ns, 1)))
        if score > 0.15:
            label = "bullish"
        elif score < -0.15:
            label = "bearish"
        else:
            label = "neutral"

    kw = list(dict.fromkeys(bull + bear))[:12]
    summary = f"偏多({nb})" if label == "bullish" else f"偏空({ns})" if label == "bearish" else "中性"
    return SentimentResult(score, label, nb, ns, 0, kw, summary)


def analyze_items(items: list) -> SentimentResult:
    """Aggregate sentiment across news headlines/summaries."""
    if not items:
        return SentimentResult(0.0, "neutral", summary="无新闻")

    scores = []
    total_bull = total_bear = neutral = 0
    all_kw: list[str] = []
    for it in items:
        text = f"{getattr(it, 'title', '')} {getattr(it, 'summary', '')}"
        r = analyze_text(text)
        scores.append(r.score)
        total_bull += r.bullish_count
        total_bear += r.bearish_count
        if r.label == "neutral":
            neutral += 1
        all_kw.extend(r.keywords)

    avg = sum(scores) / len(scores)
    if avg > 0.12:
        label = "bullish"
    elif avg < -0.12:
        label = "bearish"
    else:
        label = "neutral"

    return SentimentResult(
        round(avg, 4),
        label,
        total_bull,
        total_bear,
        neutral,
        list(dict.fromkeys(all_kw))[:15],
        f"共{len(items)}条 · 均分{avg:+.2f} · {label}",
    )


def horizon_fit_from_news(items: list) -> dict[str, float]:
    """Suggest which investment horizon fits recent news tone."""
    if not items:
        return {"short": 0.33, "medium": 0.34, "long": 0.33}

    text = " ".join(f"{getattr(i, 'title', '')} {getattr(i, 'summary', '')}" for i in items).lower()
    short_hits = sum(1 for k in SHORT_TERM if k.lower() in text)
    long_hits = sum(1 for k in LONG_TERM if k.lower() in text)
    sent = analyze_items(items)

    short = 0.35 + short_hits * 0.08 + (0.1 if abs(sent.score) > 0.3 else 0)
    long = 0.30 + long_hits * 0.10 + (0.15 if sent.label == "neutral" else 0)
    medium = 0.40 + (0.1 if 0.1 <= abs(sent.score) <= 0.3 else 0)

    total = short + medium + long
    return {
        "short": round(short / total, 3),
        "medium": round(medium / total, 3),
        "long": round(long / total, 3),
    }


def recommend_action(sentiment: SentimentResult, horizon: str = "medium") -> str:
    h = (horizon or "medium").lower()
    if sentiment.label == "bullish":
        if h == "short":
            return "新闻偏多 → 短线可顺势试多,严止损。"
        if h == "long":
            return "新闻偏多 → 长线可分批布局,忌追高。"
        return "新闻偏多 → 中线可持有/逢回调加仓。"
    if sentiment.label == "bearish":
        return "新闻偏空 → 建议减仓观望,勿逆势重仓。"
    return "新闻中性 → 以技术面为主,控制仓位。"


# ══════════════════════════════════════════════════════════════════
# 新闻风险等级评估 — 替代旧的信号叠加模式
# ══════════════════════════════════════════════════════════════════

# 高风险关键词: 突发事件/政策/交易所公告
_HIGH_RISK_KEYWORDS = [
    "黑天鹅", "暴跌", "暴涨", "熔断", "停牌", "退市", "违约",
    "爆仓", "调查", "处罚", "制裁", "战争", "冲突", "封锁",
    "加息", "降息", "紧急", "突发", "公告", "暂停交易",
    "black swan", "crash", "circuit breaker", "halt", "delist",
    "default", "investigation", "sanction", "war", "emergency",
    "urgent", "breaking", "suspend",
]

# 政策风险关键词
_POLICY_RISK_KEYWORDS = [
    "政策", "监管", "限制", "禁令", "关税", "配额",
    "policy", "regulation", "restriction", "ban", "tariff", "quota",
]

# 宏观风险关键词
_MACRO_RISK_KEYWORDS = [
    "衰退", "通胀", "萧条", "危机", "恐慌",
    "recession", "inflation", "depression", "crisis", "panic",
]


def assess_news_risk(
    items: list,
    sentiment: SentimentResult | None = None,
) -> dict:
    """评估新闻风险等级 — 仅作为风险否决，不参与正向加分。

    返回:
        {
            "risk_level": "low" | "medium" | "high",
            "risk_score": 0.0-1.0,
            "has突发事件": bool,
            "has政策风险": bool,
            "has宏观风险": bool,
            "should_block": bool,       # 是否应阻断交易
            "should_reduce": bool,      # 是否应降低仓位
            "reason": str,
        }

    规则:
        - neutral 新闻不加分
        - positive 新闻最多加 1-3 分 (不在此函数处理，在 gate 中处理)
        - negative 新闻扣 5-15 分 (不在此函数处理，在 gate 中处理)
        - high_risk 新闻直接阻断交易
    """
    risk = {
        "risk_level": "low",
        "risk_score": 0.0,
        "has突发事件": False,
        "has政策风险": False,
        "has宏观风险": False,
        "should_block": False,
        "should_reduce": False,
        "reason": "",
    }

    if not items:
        return risk

    # 合并所有文本
    all_text = " ".join(
        f"{getattr(i, 'title', '')} {getattr(i, 'summary', '')}"
        for i in items
    ).lower()

    # 检测高风险
    high_risk_hits = [k for k in _HIGH_RISK_KEYWORDS if k.lower() in all_text]
    policy_risk_hits = [k for k in _POLICY_RISK_KEYWORDS if k.lower() in all_text]
    macro_risk_hits = [k for k in _MACRO_RISK_KEYWORDS if k.lower() in all_text]

    risk["has突发事件"] = len(high_risk_hits) > 0
    risk["has政策风险"] = len(policy_risk_hits) > 0
    risk["has宏观风险"] = len(macro_risk_hits) > 0

    # 计算风险分数
    risk_score = 0.0
    if high_risk_hits:
        risk_score += min(1.0, len(high_risk_hits) * 0.4)
    if policy_risk_hits:
        risk_score += min(0.5, len(policy_risk_hits) * 0.2)
    if macro_risk_hits:
        risk_score += min(0.3, len(macro_risk_hits) * 0.15)

    # 如果 sentiment 是 bearish 且 score < -0.3，增加风险
    if sentiment and sentiment.label == "bearish" and sentiment.score < -0.3:
        risk_score += 0.2

    risk["risk_score"] = min(1.0, risk_score)

    # 判定风险等级
    if risk_score >= 0.6:
        risk["risk_level"] = "high"
        risk["should_block"] = True
        risk["should_reduce"] = True
        risk["reason"] = f"高风险新闻: {', '.join(high_risk_hits[:3])}"
    elif risk_score >= 0.3:
        risk["risk_level"] = "medium"
        risk["should_reduce"] = True
        risk["reason"] = f"中等风险: 突发={'是' if high_risk_hits else '否'} 政策={'是' if policy_risk_hits else '否'}"
    else:
        risk["risk_level"] = "low"
        risk["reason"] = "新闻风险低"

    return risk
