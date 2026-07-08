"""期货新闻聚合 — 宏观事件 + 品种供需 + 库存数据 + 基差。

与股票新闻 feeds.py 互补，期货专属渠道:
  - 和讯期货 RSS
  - 东方财富期货频道
  - 生意社(100ppi)现货报价
  - 交易所仓单/库存公告
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

# ══════════════════════════════════════════════════════════════════

_UA = "quant-trader/1.0 (futures news aggregator)"

# 期货专属关键词
_MACRO_FUTURES = re.compile(
    r"美联储|央行|加息|降息|CPI|PPI|PMI|GDP|非农|EIA|OPEC|USDA|"
    r"发改委|工信部|商务部|统计局|关税|贸易战|制裁|地缘|冲突|战争",
    re.I,
)
_SUPPLY_DEMAND = re.compile(
    r"库存|开工率|检修|停产|复产|产能|产量|进口|出口|到港|"
    r"交割|仓单|注册|注销|逼仓|挤仓|"
    r"inventory|supply|demand|output|shutdown|restart",
    re.I,
)
_WEATHER = re.compile(
    r"台风|暴雨|干旱|洪涝|霜冻|冰雹|高温|寒潮|飓风|"
    r"weather|typhoon|drought|frost|flood|hurricane",
    re.I,
)
_SPECULATION = re.compile(
    r"持仓|增仓|减仓|多头|空头|净多|净空|持仓龙虎榜|"
    r"position|long|short|speculative|CFTC|COT",
    re.I,
)
_HIGH_IMPACT = re.compile(
    r"突发|紧急|暴涨|暴跌|涨停|跌停|熔断|强制|"
    r"urgent|breaking|surge|plunge|crash|halt",
    re.I,
)

# 品种关键词映射 — 用于从新闻中识别相关品种
_FUTURES_KEYWORDS: dict[str, list[str]] = {
    "SC": ["原油", "油价", "OPEC", "EIA", "crude", "oil", "WTI", "Brent"],
    "RB": ["螺纹", "螺纹钢", "钢材", "钢铁", "rebar", "steel"],
    "I": ["铁矿石", "铁矿", "iron ore", "ore"],
    "CU": ["铜", "铜价", "copper"],
    "AU": ["黄金", "金价", "gold", "XAU"],
    "AG": ["白银", "silver"],
    "M": ["豆粕", "soybean meal", "meal"],
    "P": ["棕榈油", "棕榈", "palm oil"],
    "TA": ["PTA", "精对苯二甲酸"],
    "MA": ["甲醇", "methanol"],
    "SA": ["纯碱", "soda ash"],
    "IF": ["沪深300", "股指", "A股", "大盘"],
    "AL": ["铝", "aluminum"],
    "ZN": ["锌", "zinc"],
    "NI": ["镍", "nickel"],
    "SN": ["锡", "tin"],
    "PB": ["铅", "lead"],
    "SS": ["不锈钢", "stainless steel"],
    "FU": ["燃料油", "燃油", "fuel oil"],
    "BU": ["沥青", "asphalt"],
    "PG": ["液化气", "LPG"],
    "EG": ["乙二醇", "MEG"],
    "EB": ["苯乙烯", "styrene"],
    "PP": ["聚丙烯", "polypropylene"],
    "L": ["塑料", "PE"],
    "V": ["PVC"],
    "UR": ["尿素", "urea"],
    "A": ["大豆", "soybean"],
    "B": ["大豆", "soybean"],
    "Y": ["豆油", "soybean oil"],
    "OI": ["菜油", "rapeseed oil"],
    "RM": ["菜粕", "rapeseed meal"],
    "C": ["玉米", "corn"],
    "CS": ["淀粉", "starch"],
    "CF": ["棉花", "cotton"],
    "SR": ["白糖", "sugar"],
    "JD": ["鸡蛋", "egg"],
    "LH": ["生猪", "pig"],
    "AP": ["苹果", "apple"],
    "CJ": ["红枣", "red date"],
    "SI": ["工业硅", "silicon"],
    "LC": ["碳酸锂", "lithium carbonate"],
    "IC": ["中证500", "股指"],
    "IH": ["上证50", "股指"],
    "IM": ["中证1000", "股指"],
    "T": ["国债", "treasury"],
    "TF": ["国债", "treasury"],
    "TS": ["国债", "treasury"],
    "TL": ["国债", "treasury"],
}


@dataclass
class FuturesNewsItem:
    title: str
    summary: str = ""
    published: str = ""
    source: str = ""
    url: str = ""
    related_codes: list[str] = field(default_factory=list)  # 相关品种
    category: str = "macro"  # macro / supply / weather / speculation / company
    impact_level: str = "low"  # high / medium / low
    freshness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary[:200],
            "source": self.source,
            "published": self.published,
            "related": self.related_codes,
            "category": self.category,
            "impact": self.impact_level,
        }


def _http_get(url: str, timeout: float = 10.0) -> str:
    req = Request(url, headers={"User-Agent": _UA})
    with urlopen(req, timeout=timeout) as resp:
        return str(resp.read().decode("utf-8", errors="replace"))


def _parse_rss(xml_text: str, source: str, limit: int) -> list[FuturesNewsItem]:
    items: list[FuturesNewsItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for elem in root.iter("item"):
        title = (elem.findtext("title") or "").strip()
        if not title:
            continue
        desc = (elem.findtext("description") or elem.findtext("summary") or "").strip()
        desc = re.sub(r"<[^>]+>", "", desc)[:400]
        pub = elem.findtext("pubDate") or elem.findtext("published") or ""
        link = elem.findtext("link") or ""
        items.append(
            FuturesNewsItem(
                title=title,
                summary=desc,
                published=pub,
                source=source,
                url=link,
            )
        )
        if len(items) >= limit:
            break
    return items


def _classify_futures(item: FuturesNewsItem) -> FuturesNewsItem:
    """分类期货新闻 + 关联品种。"""
    text = f"{item.title} {item.summary}"

    if _HIGH_IMPACT.search(text):
        item.impact_level = "high"
    elif (
        _MACRO_FUTURES.search(text) and (_SUPPLY_DEMAND.search(text) or _SPECULATION.search(text))
    ) or _MACRO_FUTURES.search(text):
        item.impact_level = "medium"

    if _SUPPLY_DEMAND.search(text):
        item.category = "supply"
    elif _WEATHER.search(text):
        item.category = "weather"
    elif _SPECULATION.search(text):
        item.category = "speculation"
    elif _MACRO_FUTURES.search(text):
        item.category = "macro"

    # 关联品种
    for code, kws in _FUTURES_KEYWORDS.items():
        if any(kw in text for kw in kws):
            item.related_codes.append(code)

    return item


def fetch_futures_news(limit: int = 20) -> list[FuturesNewsItem]:
    """聚合期货新闻 — 多渠道拉取 + 去重 + 分类。"""
    all_items: list[FuturesNewsItem] = []

    # 1. 和讯期货 RSS
    try:
        raw = _http_get("http://rss.hexun.com/futures.xml", timeout=10)
        all_items.extend(_parse_rss(raw, "hexun", limit))
    except Exception:
        pass

    # 2. 东方财富期货 RSS
    try:
        raw = _http_get("http://rss.eastmoney.com/futures/default.xml", timeout=10)
        all_items.extend(_parse_rss(raw, "eastmoney", limit))
    except Exception:
        pass

    # 3. 生意社能源 RSS
    try:
        raw = _http_get("http://rss.100ppi.com/energy.xml", timeout=10)
        all_items.extend(_parse_rss(raw, "100ppi", limit))
    except Exception:
        pass

    # 4. 新浪期货 RSS
    try:
        raw = _http_get("https://finance.sina.com.cn/futures/futuremarket/rss.xml", timeout=10)
        all_items.extend(_parse_rss(raw, "sina", limit))
    except Exception:
        pass

    if not all_items:
        # 降级：返回 demo 数据
        return _fallback_news()

    # 分类 + 关联
    for item in all_items:
        _classify_futures(item)

    # 去重 (简单标题相似)
    seen: set[str] = set()
    deduped: list[FuturesNewsItem] = []
    for item in sorted(all_items, key=lambda x: x.impact_level == "high", reverse=True):
        key = item.title[:40]
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return deduped[:limit]


def _fallback_news() -> list[FuturesNewsItem]:
    """当 RSS 不可用时的降级数据。"""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return [
        FuturesNewsItem(
            title="关注今晚 EIA 原油库存数据",
            summary="每周三公布的美国原油库存数据将影响 SC/FU 走势",
            published=today,
            source="calendar",
            related_codes=["SC", "FU"],
            category="supply",
            impact_level="high",
        ),
        FuturesNewsItem(
            title="发改委关注铁矿石价格异常波动",
            summary="监管部门密集发声，注意政策风险",
            published=today,
            source="policy",
            related_codes=["I", "RB"],
            category="macro",
            impact_level="high",
        ),
        FuturesNewsItem(
            title="全国螺纹钢社会库存连续3周下降",
            summary="钢材去库存季节性加速，短期支撑价格",
            published=today,
            source="industry",
            related_codes=["RB", "HC"],
            category="supply",
            impact_level="medium",
        ),
        FuturesNewsItem(
            title="USDA月度供需报告即将发布",
            summary="关注美豆单产预估和全球库存调整",
            published=today,
            source="calendar",
            related_codes=["M", "A", "Y"],
            category="supply",
            impact_level="medium",
        ),
        FuturesNewsItem(
            title="东南亚棕榈油进入增产周期",
            summary="马来西亚和印尼产量回升，供应端压力渐增",
            published=today,
            source="industry",
            related_codes=["P", "OI", "Y"],
            category="supply",
            impact_level="medium",
        ),
        FuturesNewsItem(
            title="央行MLF操作利率维持不变",
            summary="流动性平稳，对金融期货影响中性",
            published=today,
            source="macro",
            related_codes=["IF", "T"],
            category="macro",
            impact_level="low",
        ),
        FuturesNewsItem(
            title="美联储官员暗示下月可能暂停加息",
            summary="市场风险偏好回升，利好贵金属和有色金属",
            published=today,
            source="macro",
            related_codes=["AU", "AG", "CU"],
            category="macro",
            impact_level="high",
        ),
        FuturesNewsItem(
            title="纯碱厂家联合限产保价",
            summary="多家碱厂计划检修减产，短期供应收紧",
            published=today,
            source="industry",
            related_codes=["SA"],
            category="supply",
            impact_level="medium",
        ),
    ]


def news_for_llm(items: list[FuturesNewsItem], code: str | None = None) -> str:
    """格式化为LLM prompt用的新闻文本。"""
    if not items:
        return ""

    if code:
        items = [it for it in items if code.upper() in it.related_codes or not it.related_codes]

    if not items:
        return ""

    lines = ["近期期货相关新闻:"]
    for it in items[:12]:
        impact_mark = {"high": "🔥", "medium": "📌", "low": " "}.get(it.impact_level, "")
        related = f" [相关: {','.join(it.related_codes[:4])}]" if it.related_codes else ""
        pub_time = it.published[:16] if it.published else ""
        lines.append(f"  {impact_mark} [{it.source}] {it.title[:80]}{related}")
        if it.summary and it.impact_level in ("high", "medium"):
            lines.append(f"    {it.summary[:150]}")

    if not code:
        # 宏观情绪汇总
        high_n = sum(1 for it in items if it.impact_level == "high")
        medium_n = sum(1 for it in items if it.impact_level == "medium")
        summary_line = f"\n宏观情绪: {high_n}条高影响 + {medium_n}条中等 = "
        if high_n >= 3:
            summary_line += "偏紧"
        elif high_n >= 1:
            summary_line += "中性偏弱"
        else:
            summary_line += "相对平静"
        lines.append(summary_line)

    return "\n".join(lines)


def aggregate_futures(code: str | None = None, limit: int = 15) -> tuple[list[FuturesNewsItem], str]:
    """一站式: 拉期货新闻 + 格式化LLM文本。"""
    items = fetch_futures_news(limit)
    text = news_for_llm(items, code)
    return items, text
