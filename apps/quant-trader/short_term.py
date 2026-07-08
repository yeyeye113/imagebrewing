"""短期小额推荐模块 — 昨日收盘分析 + 今日短期推荐。

主人预算 ≤1000 元、持股 ≤5 个交易日。基于前一日成交额 Top100
的 A 股数据，筛选可负担标的，通过 LLM 研判给出 3-5 个具体推荐。

用法:
    from quanttrader.short_term import generate_recommendations, format_report
    results = generate_recommendations(budget=1000)
    print(format_report(results))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .scanner.common import is_limit_price, is_st_or_delisted, safe_float

# ── Gate constants (短期推荐专用，阈值更宽松) ─────────────────────
_MIN_PRICE = 1.0
_MAX_PRICE = 10.0  # ≤1000 budget / 100 shares per lot
_MIN_TURNOVER_PCT = 2.0
_MIN_AMOUNT_YI = 1.0  # 成交额 ≥ 1亿
_MAX_TO_LLM = 15  # 最多送入 LLM 的候选数
_LOT_SIZE = 100

# ── 短期推荐专用 LLM 提示词 ───────────────────────────────────────
_SHORT_TERM_SYSTEM = """You are a disciplined short-term stock picker for A-share (China) markets.
Your task: pick 3-5 stocks from the candidate list for a SHORT-TERM trade (hold ≤5 trading days,
exit by the target sell date).

RULES:
- Budget: exactly 1000 RMB total. Each A-share lot is 100 shares, so stock price × 100 is the minimum buy cost.
- Recommend only stocks where 100 shares × price ≤ available budget. You can recommend at most 1 lot per stock.
- Favor stocks with: positive short-term momentum, reasonable volume, trending upward on daily chart.
- Avoid: stocks near limit-up (>7% yesterday), extremely low volume, clear downtrend, or obvious pump-and-dump.
- Confidence below 55% = do NOT recommend.
- Prioritize DIVERSITY: don't pick all from the same sector.
- Prefer stocks where the 5-day return is positive but not overextended (>15% in 5 days = too late).

For EACH recommended stock, respond with STRICT JSON array only, no prose:
[{"code": "6-digit code", "name": "stock name", "price": float, "shares": 100,
  "total_cost": float, "exit_date": "YYYY-MM-DD", "confidence": 0.0-1.0,
  "reason": "<=150 chars in Chinese", "risk": "<=100 chars in Chinese"}]

If NO stock passes your filters, return [].

CRITICAL: total_cost across ALL picks must NOT exceed 1000 RMB. With 100-share lots,
you can pick at most 3 stocks if avg price ~3.3 RMB, or 2 stocks if avg price ~5 RMB.
Pick QUALITY over quantity."""


def _build_short_term_prompt(
    candidates: list[dict[str, Any]],
    budget: float,
) -> str:
    """Build the user prompt with candidate stats and historical data."""
    import datetime as _dt

    _today = _dt.date.today()
    _weekday = _today.weekday()
    # Find next Friday (exit by)
    _days_to_fri = (4 - _weekday) % 7
    if _days_to_fri == 0:
        _days_to_fri = 7
    _next_fri = _today + _dt.timedelta(days=_days_to_fri)
    _yesterday = _today - _dt.timedelta(days=1)
    _day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][_weekday]

    lines = [
        "SHORT-TERM STOCK PICKING TASK",
        f"Budget: {budget:.0f} RMB | Lot size: 100 shares | Hold: ≤5 trading days",
        f"Today: {_today.isoformat()} ({_day_name}). Exit by: {_next_fri.isoformat()} (next Friday).",
        f"Total candidates after pre-filter: {len(candidates)}",
        "",
        f"CANDIDATE STOCKS (yesterday {_yesterday.isoformat()} close data):",
        "=" * 60,
    ]

    for i, s in enumerate(candidates, 1):
        lines.append(
            f"{i}. {s['code']} {s['name']} | "
            f"Close: ¥{s['price']:.2f} | "
            f"Chg%: {s['chg_pct']:+.2f}% | "
            f"Turnover: {s['turnover']:.1f}% | "
            f"Amount: {s['amount_yi']:.1f}亿 | "
            f"Score: {s['score']}/100"
        )
        # Historical context if available
        if s.get("ret_5d") is not None:
            ret5 = s.get("ret_5d") or 0.0
            r10 = s.get("ret_10d") or 0.0
            tr = s.get("trend", "N/A")
            vr = s.get("vol_regime", "N/A")
            lines.append(f"   5d ret: {ret5:+.2f}% | 10d ret: {r10:+.2f}% | Trend: {tr} | Vol regime: {vr}")

    lines.append("")
    lines.append("OUTPUT: JSON array of picks. Quality over quantity. Empty array if nothing good.")
    return "\n".join(lines)


def _fetch_close_data() -> list[dict[str, Any]]:
    """Fetch top stocks from Sina, filter to budget-friendly candidates."""
    from .scanner.lite import _fetch_top_100

    raw = _fetch_top_100()
    if not raw:
        print("[warn] Sina API returned no data; trying synthetic fallback.")
        return _synthetic_candidates()

    valid: list[dict[str, Any]] = []
    for st in raw:
        try:
            price = safe_float(st.get("trade", 0))
            chg_pct = safe_float(st.get("changepercent", 0))
            amount = safe_float(st.get("amount", 0))
            turnover = safe_float(st.get("turnoverratio", 0))
            name = str(st.get("name", ""))
            code = str(st.get("code", ""))

            if price < _MIN_PRICE or price > _MAX_PRICE:
                continue
            if turnover < _MIN_TURNOVER_PCT:
                continue
            if amount < _MIN_AMOUNT_YI * 1e8:
                continue
            if is_limit_price(chg_pct):
                continue
            if is_st_or_delisted(name):
                continue
            if name[:1] == "N" and len(name) <= 4:
                continue  # 新股首日

            valid.append(
                {
                    "code": code,
                    "name": name,
                    "price": price,
                    "chg_pct": chg_pct,
                    "amount_yi": amount / 1e8,
                    "turnover": turnover,
                }
            )
        except Exception:
            continue

    return valid


def _synthetic_candidates() -> list[dict[str, Any]]:
    """Fallback synthetic data when Sina is unreachable."""
    # Use a few well-known A-share tickers as fallback
    tickers = [
        ("600010", "包钢股份"),
        ("601288", "农业银行"),
        ("601398", "工商银行"),
        ("600016", "民生银行"),
        ("601818", "光大银行"),
        ("600028", "中国石化"),
        ("600795", "国电电力"),
        ("601988", "中国银行"),
        ("600022", "山东钢铁"),
    ]
    return [
        {
            "code": c,
            "name": n,
            "price": 3.0 + i * 0.5,
            "chg_pct": 0.5 + i * 0.3,
            "amount_yi": 10.0 - i,
            "turnover": 3.0 + i * 0.5,
        }
        for i, (c, n) in enumerate(tickers)
    ]


def _score_short_term(stock: dict[str, Any]) -> float:
    """Score a stock for short-term (1-week) potential. Returns 0-100."""
    score = 0.0

    # --- Momentum (40%) ---
    chg = stock["chg_pct"]
    if 0.5 < chg <= 5.0:
        score += 32 + chg * 1.6  # Gentle rise is best
    elif 0 < chg <= 0.5:
        score += 28
    elif -1.0 <= chg <= 0:
        score += 18
    elif chg > 5.0:
        score += 24  # Penalize overextended
    else:
        score += 8  # Fell too much

    # --- Turnover quality (30%) ---
    turnover = stock["turnover"]
    if 3.0 <= turnover <= 10.0:
        score += 27  # Sweet spot
    elif 2.0 <= turnover < 3.0:
        score += 20
    elif 10.0 < turnover <= 15.0:
        score += 18
    else:
        score += 10

    # --- Liquidity (20%) ---
    amount = stock["amount_yi"]
    if amount >= 10:
        score += 18
    elif amount >= 5:
        score += 14
    else:
        score += 8

    # --- Price advantage (10%) ---
    price = stock["price"]
    if 2.0 <= price <= 6.0:
        score += 9  # More room to move
    elif 6.0 < price <= 10.0:
        score += 6
    else:
        score += 3

    return score


def _enrich_with_history(candidates: list[dict]) -> list[dict]:
    """Fetch historical K-lines for top candidates via akshare."""
    from .data.akshare_cn import AkShareDataFeed, normalize_cn_symbol
    from .data.base import BarRequest

    feed = AkShareDataFeed(adjust="qfq", period="daily", retries=2)
    enriched = []

    for s in candidates:
        try:
            code = normalize_cn_symbol(s["code"])
            import datetime as _dt

            _start = (_dt.date.today() - _dt.timedelta(days=180)).isoformat()
            _end = _dt.date.today().isoformat()
            df = feed.history(BarRequest(symbol=code, start=_start, end=_end, interval="1d"))
            if df is None or df.empty or len(df) < 5:
                s["ret_5d"] = s["chg_pct"]
                s["ret_10d"] = None
                s["trend"] = "N/A"
                s["vol_regime"] = "N/A"
                enriched.append(s)
                continue

            closes = df["close"].astype(float)
            s["ret_5d"] = (
                (float(closes.iloc[-1]) / float(closes.iloc[-6]) - 1) * 100 if len(closes) >= 6 else s["chg_pct"]
            )
            s["ret_10d"] = (float(closes.iloc[-1]) / float(closes.iloc[-11]) - 1) * 100 if len(closes) >= 11 else None

            # Trend: SMA5 vs SMA10 vs SMA20
            sma5 = float(closes.tail(5).mean())
            sma10 = float(closes.tail(10).mean())
            sma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else sma10
            if sma5 > sma10 > sma20:
                s["trend"] = "bullish ↑"
            elif sma5 < sma10 < sma20:
                s["trend"] = "bearish ↓"
            else:
                s["trend"] = "mixed ~"

            # Vol regime
            pct = closes.pct_change().dropna()
            vol5 = float(pct.tail(5).std() * 100) if len(pct) >= 5 else 0
            vol20 = float(pct.tail(20).std() * 100) if len(pct) >= 20 else vol5
            if vol5 > vol20 * 1.3:
                s["vol_regime"] = "high vol"
            elif vol5 < vol20 * 0.7:
                s["vol_regime"] = "low vol"
            else:
                s["vol_regime"] = "normal"

        except Exception:
            s["ret_5d"] = s["chg_pct"]
            s["ret_10d"] = None
            s["trend"] = "N/A"
            s["vol_regime"] = "N/A"

        enriched.append(s)

    return enriched


@dataclass
class RecommendationResult:
    code: str
    name: str
    price: float
    shares: int
    total_cost: float
    exit_date: str
    confidence: float
    reason: str
    risk: str
    sentiment: str = ""  # 保留字段，兼容旧调用方


def generate_recommendations(
    budget: float = 1000,
    llm_config: Any = None,
) -> list[RecommendationResult]:
    """Generate short-term stock recommendations.

    Args:
        budget: Total budget in RMB (default 1000).
        llm_config: LLMConfig instance (None = skip LLM, use quant scoring).

    Returns:
        List of RecommendationResult, ready to format or execute.
    """
    # 1) Fetch & filter
    print("[*] 获取前日收盘数据...")
    raw = _fetch_close_data()
    if not raw:
        print("[-] 无符合条件的标的。")
        return []

    print(f"   全市场 Top100 筛选后有效候选: {len(raw)} 只")

    # 2) Score
    for s in raw:
        s["score"] = round(_score_short_term(s))

    raw.sort(key=lambda x: x["score"], reverse=True)

    # 3) Enrich top candidates with K-line history
    top = raw[:_MAX_TO_LLM]
    print(f"   分析 Top {len(top)} 只历史K线...")
    top = _enrich_with_history(top)

    # 5) LLM decision
    if llm_config:
        import json
        import re

        from .ai.llm import LLMConfig as LLC

        cfg = llm_config if isinstance(llm_config, LLC) else LLC(provider="deepseek")
        try:
            cfg = cfg.resolve()
        except Exception:
            pass

        if cfg.api_key:
            print(f"[LLM] 研判中 ({cfg.provider}/{cfg.model})...")
            try:
                prompt = _build_short_term_prompt(top, budget)
                # Use raw API call with custom system prompt (not ask_llm which is for single-stock)
                import requests

                body = {
                    "model": cfg.model,
                    "messages": [
                        {"role": "system", "content": _SHORT_TERM_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                }
                headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
                resp = requests.post(
                    f"{cfg.base_url.rstrip('/')}/chat/completions",
                    json=body,
                    headers=headers,
                    timeout=45,
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]

                # Parse JSON from response
                picks = None
                try:
                    picks = json.loads(content)
                except Exception:
                    m = re.search(r"\[.*\]", content, re.DOTALL)
                    if m:
                        try:
                            picks = json.loads(m.group(0))
                        except Exception:
                            picks = []

                if picks and isinstance(picks, list):
                    results = []
                    for p in picks:
                        try:
                            results.append(
                                RecommendationResult(
                                    code=str(p.get("code", "")),
                                    name=str(p.get("name", "")),
                                    price=float(p.get("price", 0)),
                                    shares=int(p.get("shares", 100)),
                                    total_cost=float(p.get("total_cost", 0)),
                                    exit_date=str(p.get("exit_date", "")),
                                    confidence=float(p.get("confidence", 0)),
                                    reason=str(p.get("reason", "")),
                                    risk=str(p.get("risk", "")),
                                )
                            )
                        except Exception:
                            continue
                    if results:
                        print(f"   [LLM] 选出 {len(results)} 只推荐")
                        return results

            except Exception as e:
                print(f"   [LLM] 调用失败: {e}，回退到量化评分模式。")

    # 6) Fallback: pure quant scoring picks (no LLM)
    print("[*] 量化评分模式（无 LLM）")
    results = []
    remaining = budget
    for s in top:
        if remaining < s["price"] * _LOT_SIZE:
            continue
        if s["score"] < 45:
            continue

        from datetime import date, timedelta

        exit_d = date.today() + timedelta(days=7)  # ~5 trading days

        results.append(
            RecommendationResult(
                code=s["code"],
                name=s["name"],
                price=s["price"],
                shares=_LOT_SIZE,
                total_cost=round(s["price"] * _LOT_SIZE, 2),
                exit_date=exit_d.isoformat(),
                confidence=round(min(s["score"] / 100 + 0.1, 0.85), 2),
                reason=f"量化评分 {s['score']}/100 | 涨跌 {s['chg_pct']:+.2f}% | 换手 {s['turnover']:.1f}%",
                risk=f"趋势 {s.get('trend', 'N/A')} | 波动 {s.get('vol_regime', 'N/A')}",
                sentiment="",
            )
        )
        remaining -= s["price"] * _LOT_SIZE
        if len(results) >= 3:
            break

    return results


def format_report(results: list[RecommendationResult]) -> str:
    """Format recommendations into a readable report."""
    from datetime import date

    lines = [
        "=" * 60,
        f"  短期交易推荐 | {date.today().isoformat()}",
        "=" * 60,
        "  预算: 1,000 RMB | 每手: 100股 | 持股: <=5交易日",
    ]

    if not results:
        lines.append("-" * 60)
        lines.append("  [!] 今日无符合条件的推荐。市场观望为宜。")
        lines.append("=" * 60)
        return "\n".join(lines)

    lines.append("-" * 60)
    lines.append("  >>> 推荐买入")
    lines.append("-" * 60)

    total = 0.0
    for i, r in enumerate(results, 1):
        total += r.total_cost
        conf_bar = "HIGH" if r.confidence >= 0.7 else ("MED" if r.confidence >= 0.6 else "LOW")
        lines.append(f"  {i}. {r.code}  {r.name:<12s}  价格: {r.price:.2f}  {r.shares}股  金额: {r.total_cost:.0f}")
        lines.append(f"     置信度: {conf_bar} ({r.confidence:.0%})  目标卖出: {r.exit_date}")
        lines.append(f"     理由: {r.reason}")
        if r.risk:
            lines.append(f"     风险: {r.risk}")
        lines.append("")

    lines.append("-" * 60)
    lines.append(f"  合计投入: {total:,.0f} RMB | 剩余现金: {1000 - total:,.0f} RMB")
    lines.append("-" * 60)
    lines.append("  [!] 风险提示:")
    lines.append("  - 以上为 AI 分析建议，不构成投资建议")
    lines.append("  - 短期交易风险高，请设置止损（建议 -5%）")
    lines.append("  - 实盘前先在模拟盘验证策略")
    lines.append("=" * 60)

    return "\n".join(lines)
