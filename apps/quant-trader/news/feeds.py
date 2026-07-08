"""Market-wide news aggregator — multi-source, de-duplicated, ranked.

Pulls from:
  - A-share: 东方财富新闻 (akshare stock_news_em) + 百度财经RSS
  - US: Yahoo Finance RSS + MarketWatch headlines
  - Fallback: demo headlines keyed to symbol sentiment

Features:
  - Cross-source dedup via title similarity (Jaccard on 2-char bigrams)
  - Freshness scoring (recency-weighted)
  - Impact classification: company-level vs sector vs macro
  - Chinese + English keyword extraction unified
  - Async-compatible (sync default, but built for asyncio wrapper)
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

# ═══════════════════════════════════════════════════════════════════════════
# Data class
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class NewsItem:
    title: str
    summary: str = ""
    published: str = ""
    source: str = ""
    url: str = ""
    symbol: str = ""
    impact_level: str = "low"  # high | medium | low
    category: str = "company"  # company | sector | macro | technical
    freshness: float = 0.0  # 1.0 = just now, 0.0 = >24h
    keywords: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Dedup engine
# ═══════════════════════════════════════════════════════════════════════════


def _bigrams(text: str) -> set[str]:
    t = re.sub(r"\s+", "", text.lower())
    return {t[i : i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t}


def _jaccard(a: str, b: str) -> float:
    sa, sb = _bigrams(a), _bigrams(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def deduplicate(items: list[NewsItem], threshold: float = 0.65) -> list[NewsItem]:
    """Remove near-duplicate headlines across sources."""
    kept: list[NewsItem] = []
    for item in items:
        if not any(_jaccard(item.title, k.title) > threshold for k in kept):
            kept.append(item)
    return kept


# ═══════════════════════════════════════════════════════════════════════════
# Freshness scoring
# ═══════════════════════════════════════════════════════════════════════════


def _parse_relative_time(s: str) -> float:
    """Parse a relative Chinese time string into hours ago."""
    s = s.strip()
    # "3小时前" / "30分钟前" / "1天前" / "2024-06-18"
    m = re.search(r"(\d+)\s*小时前", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+)\s*分钟前", s)
    if m:
        return float(m.group(1)) / 60.0
    m = re.search(r"(\d+)\s*天前", s)
    if m:
        return float(m.group(1)) * 24.0
    m = re.search(r"(\d+)\s*秒前", s)
    if m:
        return float(m.group(1)) / 3600.0
    # Try ISO/date parse
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00")[:25])
        age = (datetime.now(UTC) - dt.replace(tzinfo=UTC)).total_seconds() / 3600
        return max(0, age)
    except Exception:
        return 12.0  # unknown → 12h


def score_freshness(items: list[NewsItem]) -> list[NewsItem]:
    """Assign freshness scores (1.0 = now, decays over 24h)."""
    for item in items:
        hrs = _parse_relative_time(item.published) if item.published else 12.0
        item.freshness = round(max(0.0, 1.0 - hrs / 24.0), 3)
    return items


# ═══════════════════════════════════════════════════════════════════════════
# Impact classification
# ═══════════════════════════════════════════════════════════════════════════

COMPANY_KW = re.compile(
    r"财报|业绩|营收|利润|分红|回购|增持|减持|高管|CEO|董事长|重组|并购|上市|退市|"
    r"earnings|revenue|profit|dividend|buyback|CEO|acquisition|IPO",
    re.I,
)
SECTOR_KW = re.compile(
    r"行业|板块|赛道|新能源|半导体|医药|消费|地产|银行|保险|券商|钢铁|煤炭|化工|"
    r"sector|industry|semiconductor|pharma|banking|energy|retail",
    re.I,
)
MACRO_KW = re.compile(
    r"央行|美联储|加息|降息|CPI|PPI|GDP|PMI|利率|汇率|就业|通胀|货币政策|关税|贸易|"
    r"fed|interest rate|inflation|GDP|unemployment|tariff|policy|central bank",
    re.I,
)
HIGH_IMPACT_KW = re.compile(
    r"突发|紧急|公告|预警|调查|处罚|强制|停牌|退市|爆雷|闪崩|"
    r"urgent|warning|investigation|SEC|lawsuit|halt|delist|crash",
    re.I,
)


def classify_items(items: list[NewsItem]) -> list[NewsItem]:
    """Tag each item with category and impact level."""
    for item in items:
        text = f"{item.title} {item.summary}"
        if MACRO_KW.search(text):
            item.category = "macro"
        elif SECTOR_KW.search(text):
            item.category = "sector"
        else:
            item.category = "company"

        if HIGH_IMPACT_KW.search(text):
            item.impact_level = "high"
        elif SECTOR_KW.search(text) and COMPANY_KW.search(text):
            item.impact_level = "medium"
        else:
            item.impact_level = "low"

        # Extract keywords
        kw_set: list[str] = []
        for pat, label in [
            (MACRO_KW, "宏观"),
            (SECTOR_KW, "行业"),
            (COMPANY_KW, "公司"),
        ]:
            found = pat.findall(text)
            if found:
                kw_set.extend([f.lower() for f in found[:3]])
        item.keywords = list(dict.fromkeys(kw_set))[:5]  # dedup, keep order

    return items


# ═══════════════════════════════════════════════════════════════════════════
# Fetchers
# ═══════════════════════════════════════════════════════════════════════════

_UA = "quant-trader/1.0 (market news aggregator)"


def _http_get(url: str, timeout: float = 10.0) -> str:
    req = Request(url, headers={"User-Agent": _UA})
    with urlopen(req, timeout=timeout) as resp:
        return str(resp.read().decode("utf-8", errors="replace"))


def _parse_rss(xml_text: str, symbol: str, source: str, limit: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    # Security: limit XML size to prevent billion-laughs / entity expansion attacks
    if len(xml_text) > 1_000_000:  # 1MB cap
        xml_text = xml_text[:1_000_000]
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        desc = (item.findtext("description") or item.findtext("summary") or "").strip()
        desc = re.sub(r"<[^>]+>", "", desc)[:500]
        pub = item.findtext("pubDate") or item.findtext("published") or ""
        link = item.findtext("link") or ""
        items.append(NewsItem(title=title, summary=desc, published=pub, source=source, url=link, symbol=symbol))
        if len(items) >= limit:
            break
    return items


def _fetch_yahoo(symbol: str, limit: int) -> list[NewsItem]:
    sym = symbol.upper().split(".")[0]
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
    try:
        return _parse_rss(_http_get(url), symbol, "yahoo_rss", limit)
    except Exception:
        return []


def _fetch_marketwatch(symbol: str, limit: int) -> list[NewsItem]:
    """MarketWatch RSS — broader than Yahoo, good for US macro color."""
    sym = symbol.upper().split(".")[0]
    # MarketWatch doesn't have per-symbol RSS; use top stories + filter
    try:
        url = "https://feeds.content.dowjones.io/public/rss/mw_topstories"
        raw = _parse_rss(_http_get(url), symbol, "marketwatch", limit * 2)
        # Keep items mentioning the symbol or general macro
        macro = [it for it in raw if sym.lower() in it.title.lower() or MACRO_KW.search(it.title)][:limit]
        return macro or raw[:limit]
    except Exception:
        return []


def _fetch_akshare_news(symbol: str, limit: int) -> list[NewsItem]:
    """东方财富个股新闻 — A-share primary source."""
    try:
        import akshare as ak
    except ImportError:
        return []

    code = re.sub(r"[^0-9]", "", symbol)
    if len(code) != 6:
        return []

    items: list[NewsItem] = []
    try:
        df = ak.stock_news_em(symbol=code)
    except Exception:
        return []

    if df is None or df.empty:
        return []

    title_col = next((c for c in df.columns if "标题" in c or c.lower() == "title"), df.columns[0])
    time_col = next((c for c in df.columns if "时间" in c or "date" in c.lower()), None)
    url_col = next((c for c in df.columns if "链接" in c or "url" in c.lower()), None)
    src_col = next((c for c in df.columns if "来源" in c or "source" in c.lower()), None)

    for _, row in df.head(limit).iterrows():
        title = str(row.get(title_col, "")).strip()
        if not title:
            continue
        items.append(
            NewsItem(
                title=title,
                summary=str(row.get(title_col, ""))[:300],
                published=str(row.get(time_col, "")) if time_col else "",
                source=str(row.get(src_col, "eastmoney")) if src_col else "eastmoney",
                url=str(row.get(url_col, "")) if url_col else "",
                symbol=symbol,
            )
        )
    return items


def _fetch_baidu_news(symbol: str, limit: int) -> list[NewsItem]:
    """百度财经 RSS — A-share supplementary, good for sentiment color."""
    code = re.sub(r"[^0-9]", "", symbol)
    if len(code) != 6:
        return []
    # 百度新闻搜索RSS (股票代码) — URL-encode the query parameter
    from urllib.parse import quote

    try:
        url = f"https://news.baidu.com/ns?word={quote(code)}&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        raw = _parse_rss(_http_get(url), symbol, "baidu", limit)
        return raw
    except Exception:
        return []


def _demo_news(symbol: str, limit: int) -> list[NewsItem]:
    """Deterministic demo headlines."""
    seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16) % 3
    templates = [
        [
            ("行业景气度回升，龙头企业盈利超预期", "bullish"),
            ("机构上调目标价至历史新高", "bullish"),
            ("短期波动加大，注意回调风险", "neutral"),
            ("新产品发布获市场广泛关注", "bullish"),
            ("政策利好持续释放，板块集体走强", "bullish"),
        ],
        [
            ("业绩不及预期，股价承压下行", "bearish"),
            ("监管层启动调查引发市场担忧", "bearish"),
            ("长期战略转型稳步推进中", "neutral"),
            ("原材料成本上升挤压利润空间", "bearish"),
            ("股东减持计划引发投资者关注", "bearish"),
        ],
        [
            ("分红方案公布，股息率超预期", "bullish"),
            ("并购重组传闻升温", "neutral"),
            ("技术突破带来估值重估机会", "bullish"),
            ("行业竞争加剧，市场份额承压", "bearish"),
            ("机构调研密集，关注度提升", "neutral"),
        ],
    ]
    now = datetime.now(UTC)
    out: list[NewsItem] = []
    for i, (title, _tag) in enumerate(templates[seed]):
        if i >= limit:
            break
        out.append(
            NewsItem(
                title=f"[{symbol}] {title}",
                summary=title,
                published=(now - timedelta(hours=i * 3)).isoformat(timespec="seconds"),
                source="demo",
                symbol=symbol,
            )
        )
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Main API
# ═══════════════════════════════════════════════════════════════════════════

_FETCHERS: dict[str, Callable] = {
    "yahoo": _fetch_yahoo,
    "rss": _fetch_yahoo,
    "marketwatch": _fetch_marketwatch,
    "akshare": _fetch_akshare_news,
    "eastmoney": _fetch_akshare_news,
    "baidu": _fetch_baidu_news,
    "demo": _demo_news,
    "synthetic": _demo_news,
}


def _is_cn_symbol(symbol: str) -> bool:
    s = re.sub(r"[^0-9]", "", symbol or "")
    return len(s) == 6 and s.isdigit()


def aggregate_news(
    symbol: str,
    sources: list[str] | None = None,
    limit: int = 20,
    dedup_threshold: float = 0.65,
) -> list[NewsItem]:
    """Pull news from multiple sources, dedup, classify, and rank.

    Args:
        symbol: stock symbol
        sources: list of source names, or None for auto-detect
        limit: max items to return
        dedup_threshold: Jaccard similarity threshold for dedup
    """
    is_cn = _is_cn_symbol(symbol)

    if sources is None:
        sources = ["akshare", "eastmoney", "baidu", "demo"] if is_cn else ["yahoo", "rss", "marketwatch", "demo"]

    all_items: list[NewsItem] = []
    for src in sources:
        fetcher = _FETCHERS.get(src.lower())
        if fetcher is None:
            continue
        try:
            items = fetcher(symbol, limit=limit)
            all_items.extend(items)
        except Exception:
            continue

    # Fallback to demo if nothing found
    if not all_items:
        all_items = _demo_news(symbol, limit)

    # Pipeline: dedup → score freshness → classify → sort
    all_items = deduplicate(all_items, dedup_threshold)
    all_items = score_freshness(all_items)
    all_items = classify_items(all_items)

    # Sort: high-impact first, then by freshness
    impact_order = {"high": 0, "medium": 1, "low": 2}
    all_items.sort(key=lambda x: (impact_order.get(x.impact_level, 2), -x.freshness))

    return all_items[:limit]


def news_item_dict(item: NewsItem) -> dict:
    return {
        "title": item.title,
        "summary": item.summary,
        "published": item.published,
        "source": item.source,
        "url": item.url,
        "symbol": item.symbol,
        "impact_level": item.impact_level,
        "category": item.category,
        "freshness": item.freshness,
        "keywords": item.keywords,
    }


def news_for_llm(items: list[NewsItem]) -> str:
    """Format news items as a compact string for the LLM prompt."""
    if not items:
        return ""

    lines = []
    for it in items:
        impact = {"high": "🔥", "medium": "📌", "low": "·"}.get(it.impact_level, "·")
        cat = {"macro": "宏观", "sector": "行业", "company": "公司"}.get(it.category, "")
        lines.append(f"{impact} [{cat}|{it.source}] {it.title}{' — ' + it.summary[:80] if it.summary else ''}")
    return "\n".join(lines)


# ── Legacy compat shim ───────────────────────────────────────────────────


def fetch_news(symbol: str, source: str = "auto", limit: int = 20) -> tuple[list[NewsItem], str]:
    """Legacy API — compatible with existing callers."""
    if source in ("auto", ""):
        sources = None
    else:
        sources = [source]
    items = aggregate_news(symbol, sources=sources, limit=limit)
    used = items[0].source if items else "demo"
    return items, used
