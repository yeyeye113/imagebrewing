"""Unified A-share scanner engine — single entry point for all scanning modes.

Replaces the split logic in __init__.py and lite.py with a unified engine.
Supports modes: lite (fast, Sina API), full (akshare), backtest (historical).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from .ai_enhance import ai_enhance
from .common import (
    ScanConfig,
    safe_float,
)
from .regime import MarketRegimeDetector, MoneyFlowDetector, apply_dynamic_weights
from .sectors import SectorDetector

logger = logging.getLogger("quanttrader.scanner.engine")


# ══════════════════════════════════════════════════════════════════
# 数据获取
# ══════════════════════════════════════════════════════════════════

_SINA_URL = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
_SINA_KLINE_URL = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var/CN_MarketDataService.getKLineData"


def _ensure_no_proxy() -> None:
    """Append Sina domains to no_proxy without deleting any env vars."""
    for key in ("no_proxy", "NO_PROXY"):
        cur = os.environ.get(key, "")
        if "sina.com.cn" not in cur:
            os.environ[key] = cur + ",sina.com.cn,sinajs.cn,eastmoney.com"


def _make_session() -> requests.Session:
    _ensure_no_proxy()
    s = requests.Session()
    s.trust_env = False
    s.verify = True
    return s


def fetch_spot_sina(config: ScanConfig, retries: int = 3) -> list[dict[str, Any]]:
    """Fetch top N A-shares by turnover from Sina. Retries on failure."""
    _ensure_no_proxy()
    import time

    # Fetch enough pages to cover kline_fetch_ratio * top_n
    pages_needed = max(1, int(config.kline_fetch_ratio * config.top_n / 100) + 1)
    all_stocks: list[dict[str, Any]] = []

    for page in range(1, pages_needed + 1):
        for attempt in range(retries):
            try:
                session = _make_session()
                r = session.get(
                    _SINA_URL,
                    params={
                        "page": page,
                        "num": 100,
                        "sort": "amount",
                        "asc": 0,
                        "node": "hs_a",
                    },
                    timeout=20,
                )
                if r.status_code != 200:
                    logger.warning("Sina spot API returned %d", r.status_code)
                    break
                data = r.json()
                if not data:
                    break
                all_stocks.extend(data)
                break  # success, move to next page
            except Exception as e:
                logger.warning("Sina spot fetch attempt %d/%d page %d failed: %s", attempt + 1, retries, page, e)
                if attempt < retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                else:
                    break

    if not all_stocks:
        logger.error("No stocks returned from Sina API after %d retries", retries)
    return all_stocks


def fetch_kline_batch(
    codes: list[str], days: int = 30, config: ScanConfig | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Fetch daily kline for a batch of codes from Sina.

    Returns {code: [{day, open, high, low, close, volume}, ...]}.
    """
    session = _make_session()
    results: dict[str, list[dict[str, Any]]] = {}
    for code in codes:
        try:
            r = session.get(
                _SINA_KLINE_URL,
                params={"symbol": code, "scale": "240", "ma": "no", "datalen": days},
                timeout=10,
            )
            if r.status_code != 200:
                continue
            text = r.text.strip()
            start = text.find("([")
            end = text.rfind("])")
            if start == -1 or end == -1:
                continue
            json_str = text[start + 1 : end + 1]
            klines = json.loads(json_str)
            if isinstance(klines, list) and len(klines) >= 5:
                results[code] = klines
        except Exception as e:
            logger.debug("Kline fetch failed for %s: %s", code, e)
            continue
    logger.debug("Kline fetched: %d/%d codes", len(results), len(codes))
    return results


# ══════════════════════════════════════════════════════════════════
# 过滤门控
# ══════════════════════════════════════════════════════════════════


def gate_stocks(
    raw: list[dict[str, Any]], config: ScanConfig
) -> list[dict[str, Any]]:
    """Apply gating filters to raw Sina data."""
    valid = []
    for st in raw:
        try:
            price = safe_float(st.get("trade", 0))
            chg_pct = safe_float(st.get("changepercent", 0))
            amount = safe_float(st.get("amount", 0))
            turnover = safe_float(st.get("turnoverratio", 0))
            name = str(st.get("name", ""))
            code = str(st.get("code", ""))

            # Price gate
            if price < config.min_price or price > config.max_price:
                continue
            # Turnover gate
            if turnover < config.min_turnover_pct:
                continue
            # Amount gate
            if amount < config.min_amount_yi * 1e8:
                continue
            # Limit up/down gate
            if config.block_limit_up and chg_pct > config.limit_threshold:
                continue
            if config.block_limit_down and chg_pct < -config.limit_threshold:
                continue
            # ST / delisted gate
            if any(kw in name for kw in config.st_keywords):
                continue

            valid.append(
                {
                    "code": str(st.get("symbol", code)),
                    "name": name,
                    "price": price,
                    "chg_pct": chg_pct,
                    "amount_yi": amount / 1e8,
                    "turnover": turnover,
                    "vol_ratio": 1.0,
                    "mom_5d": chg_pct,
                    "mom_20d": 0.0,
                    "trend_pct": 0.0,
                    "industry": str(st.get("mkt", "")),
                }
            )
        except Exception as e:
            logger.debug("Parse error for stock %s: %s", st.get("code", "?"), e)
            continue

    return valid


# ══════════════════════════════════════════════════════════════════
# Kline 增强
# ══════════════════════════════════════════════════════════════════


def enrich_with_kline(
    stocks: list[dict[str, Any]], klines: dict[str, list[dict[str, Any]]]
) -> int:
    """Enrich stocks with historical kline data.

    Updates mom_5d, mom_20d, vol_ratio, trend_pct in-place.
    Returns number of stocks enriched.
    """
    hits = 0
    for s in stocks:
        kl = klines.get(s["code"])
        if not kl or len(kl) < 6:
            continue
        hits += 1
        try:
            closes = [safe_float(k.get("close", 0)) for k in kl]
            volumes = [safe_float(k.get("volume", 0)) for k in kl]
            if closes[-1] <= 0:
                continue

            # mom_5d
            if len(closes) >= 6 and closes[-6] > 0:
                s["mom_5d"] = (closes[-1] / closes[-6] - 1) * 100
            # mom_20d
            if len(closes) >= 21 and closes[-21] > 0:
                s["mom_20d"] = (closes[-1] / closes[-21] - 1) * 100
            # vol_ratio
            avg_vol = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else 0
            if avg_vol > 0 and volumes[-1] > 0:
                s["vol_ratio"] = volumes[-1] / avg_vol
            # trend_pct (vs SMA10)
            if len(closes) >= 10:
                sma10 = sum(closes[-10:]) / 10
                if sma10 > 0:
                    s["trend_pct"] = (closes[-1] / sma10 - 1) * 100
        except Exception as e:
            logger.debug("Kline calc error for %s: %s", s["code"], e)

    return hits


# ══════════════════════════════════════════════════════════════════
# 评分引擎 (统一)
# ══════════════════════════════════════════════════════════════════


def compute_scores(
    stocks: list[dict[str, Any]], config: ScanConfig
) -> list[dict[str, Any]]:
    """统一评分函数 — 排名百分位 + 维度加权 + 排名加速。

    Dimensions:
      成交额 rank  (config.w_amount)  — 资金关注度
      换手率 rank  (config.w_turnover)  — 活跃度
      动量绝对值    (config.w_momentum)  — 涨跌幅强度
      方向分        (config.w_direction)  — 上涨>下跌
      量比分        (config.w_vol_ratio)  — 量比>1.5爆破加分
    """
    if not stocks:
        return stocks

    n = len(stocks)
    max_chg = max(abs(s["chg_pct"]) for s in stocks)

    # ── 排名百分位 ──
    by_amt = sorted(stocks, key=lambda x: x["amount_yi"], reverse=True)
    for rank, s in enumerate(by_amt):
        s["_rank_amt"] = 1.0 - rank / max(n - 1, 1)

    by_turn = sorted(stocks, key=lambda x: x["turnover"], reverse=True)
    for rank, s in enumerate(by_turn):
        s["_rank_turn"] = 1.0 - rank / max(n - 1, 1)

    # ── 逐股评分 ──
    for s in stocks:
        # 成交额排名百分位 → 0-w_amount
        amt_score = s["_rank_amt"] * config.w_amount

        # 换手率排名百分位 → 0-w_turnover
        turn_score = s["_rank_turn"] * config.w_turnover

        # 动量绝对值 → 0-w_momentum
        mom_score = min(abs(s["chg_pct"]) / max(max_chg, 1), 1.0) * config.w_momentum

        # 方向分 → 0-w_direction
        chg = s["chg_pct"]
        if chg > 7:
            dir_norm = 1.0
        elif chg > 5:
            dir_norm = 0.93
        elif chg > 3:
            dir_norm = 0.8
        elif chg > 1.5:
            dir_norm = 0.67
        elif chg > 0.5:
            dir_norm = 0.53
        elif chg > -0.5:
            dir_norm = 0.33
        elif chg > -2:
            dir_norm = 0.2
        else:
            dir_norm = 0.0
        dir_score = dir_norm * config.w_direction

        # 量比分 → 0-w_vol_ratio
        vr = s.get("vol_ratio", 1.0)
        if vr >= 3.0:
            vr_norm = 1.0
        elif vr >= 2.0:
            vr_norm = 0.8
        elif vr >= 1.5:
            vr_norm = 0.5
        elif vr >= 1.0:
            vr_norm = 0.2
        else:
            vr_norm = 0.0
        vr_score = vr_norm * config.w_vol_ratio

        base = amt_score + turn_score + mom_score + dir_score + vr_score

        # ── 排名加速 ──
        avg_rank = (s["_rank_amt"] + s["_rank_turn"]) / 2
        if avg_rank >= 0.9:
            boost = config.boost_top10
        elif avg_rank >= 0.75:
            boost = config.boost_top25
        elif avg_rank >= 0.5:
            boost = config.boost_top50
        else:
            boost = 0

        s["score"] = round(min(base + boost, 100))

    return stocks


# ══════════════════════════════════════════════════════════════════
# 统一扫描入口
# ══════════════════════════════════════════════════════════════════


def _technical_action_advice(s: dict) -> tuple[str, str]:
    """纯技术面操作建议（不含卦象/五行）。"""
    score = int(s.get("score", 0))
    chg = float(s.get("chg_pct", 0))
    ai_action = s.get("ai_action", "")
    ai_reason = (s.get("ai_reason") or "").strip()
    vol_ratio = float(s.get("vol_ratio", 1))
    sector = s.get("sector_resonance", "")

    parts = [f"技术评分 {score}"]
    if vol_ratio >= 1.5:
        parts.append(f"量比 {vol_ratio:.1f}")
    if sector:
        parts.append(f"板块共振 {sector}")
    base = " · ".join(parts)

    if ai_action == "sell":
        return "skip", ai_reason or f"{base} · AI 偏空"
    if ai_action == "buy" and score >= 55:
        return "buy", ai_reason or f"{base} · AI 偏多"
    if score >= 75 and chg < 7:
        return "buy", f"{base} · 量价动量偏强"
    if score >= 55:
        return "watch", f"{base} · 中等强度，等待确认"
    return "skip", f"{base} · 指标偏弱"


@dataclass
class ScanResult:
    """统一扫描结果 — 兼容旧 PickResult 和 ScanResult。"""
    code: str
    name: str
    price: float
    chg_pct: float
    amount_yi: float
    turnover: float
    score: int
    # Kline维度
    mom_5d: float = 0.0
    mom_20d: float = 0.0
    vol_ratio: float = 1.0
    trend_pct: float = 0.0
    # 行业
    industry: str = ""
    sector_group: str = ""
    # 板块共振
    sector_resonance: str = ""  # "up"/"down"/"mixed"/""
    sector_bonus: float = 0.0
    # AI 增强
    ai_action: str = ""  # "buy"/"hold"/"sell"
    ai_confidence: float = 0.0
    ai_reason: str = ""
    risk_level: str = ""  # "low"/"mid"/"high"
    # 玄学 (可选)
    hexagram: str = ""
    hexagram_num: int = 0
    hexagram_sent: str = ""
    hexagram_desc: str = ""
    action: str = "watch"
    advice: str = ""
    ri_ganzhi: str = ""
    shengxiao: str = ""
    stock_wuxing: str = ""
    ri_wuxing: str = ""
    stock_ri_relation: str = ""
    hexagram_element: str = ""
    composite_reason: str = ""
    quote: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "price": round(self.price, 2),
            "chg_pct": round(self.chg_pct, 2),
            "change_pct": round(self.chg_pct, 2),
            "score": self.score,
            "mom_5d": round(self.mom_5d, 2),
            "mom_20d": round(self.mom_20d, 2),
            "vol_ratio": round(self.vol_ratio, 2),
            "trend_pct": round(self.trend_pct, 2),
            "turnover": round(self.turnover, 2),
            "amount_yi": round(self.amount_yi, 2),
            "industry": self.industry,
            "sector_group": self.sector_group,
            "sector_resonance": self.sector_resonance,
            "sector_bonus": self.sector_bonus,
            "ai_action": self.ai_action,
            "ai_confidence": self.ai_confidence,
            "ai_reason": self.ai_reason,
            "risk_level": self.risk_level,
            "action": self.action,
            "advice": self.advice,
        }


def run(config: ScanConfig | None = None) -> list[ScanResult]:
    """统一扫描入口。

    Args:
        config: 扫描配置, None则用默认值

    Returns:
        按score降序排列的ScanResult列表
    """
    cfg = config or ScanConfig()
    t0 = time.time()

    # 1. 获取实时数据
    raw = fetch_spot_sina(cfg)
    logger.info("Sina fetched: %d raw stocks", len(raw))

    # 2. 门控过滤
    valid = gate_stocks(raw, cfg)
    logger.info("Gated: %d → %d valid stocks", len(raw), len(valid))

    if not valid:
        logger.warning("No valid stocks after gating")
        return []

    # 2.5 市场环境检测 + 动态权重
    regime_detector = MarketRegimeDetector()
    regime_signal = regime_detector.detect_from_batch(valid)
    logger.info(
        "Market regime: %s (conf=%.0f%%, breadth=%.0f%%) — %s",
        regime_signal.regime.value,
        regime_signal.confidence * 100,
        regime_signal.breadth * 100,
        regime_signal.reasoning,
    )
    cfg = apply_dynamic_weights(cfg, regime_signal.regime)

    # 3. 获取K线数据
    by_amount = sorted(valid, key=lambda x: x["amount_yi"], reverse=True)
    kline_count = min(int(cfg.top_n * cfg.kline_fetch_ratio), len(valid))
    kline_codes = [s["code"] for s in by_amount[:kline_count]]
    klines = fetch_kline_batch(kline_codes, days=cfg.kline_days)
    hits = enrich_with_kline(valid, klines)
    logger.info("Kline enriched: %d/%d stocks", hits, len(kline_codes))

    # 4. 板块共振检测
    sector_detector = SectorDetector(threshold=3)
    resonances = sector_detector.detect(valid)
    if resonances:
        logger.info(
            "Sector resonance: %s",
            ", ".join(
                f"{r.sector}({r.direction}×{r.count})"
                for r in resonances.values()
            ),
        )

    # 5. 评分
    compute_scores(valid, cfg)

    # 5.5 资金流向检测 + 加分
    mf_detector = MoneyFlowDetector()
    money_flows = mf_detector.detect(valid)
    for s in valid:
        mf_bonus = mf_detector.get_bonus(s["code"], money_flows)
        s["score"] = round(min(max(s["score"] + mf_bonus, 0), 100))

    # 6. 板块共振加分
    for s in valid:
        bonus = sector_detector.get_bonus(s["code"], resonances)
        s["sector_bonus"] = bonus
        s["score"] = round(min(max(s["score"] + bonus, 0), 100))

        # 补充行业信息
        sector = sector_detector.industry_map.get_sector(
            s["code"], s.get("industry", "")
        )
        s["industry"] = sector
        s["sector_group"] = sector_detector.industry_map.get_sector_group(s["code"])

        # 标记共振状态
        res = resonances.get(sector)
        if res and res.direction != "mixed":
            s["sector_resonance"] = res.direction
        else:
            s["sector_resonance"] = ""

    # 6.5 AI 增强: 对 top 候选运行 LLM 批量研判
    if cfg.use_ai:
        regime_desc = f"{regime_signal.regime.value}(breadth={regime_signal.breadth:.0%})"
        valid.sort(key=lambda x: x["score"], reverse=True)
        ai_enhance(valid, klines, cfg, regime=regime_desc)

    # 7. 排序 + 取 top_n
    valid.sort(key=lambda x: x["score"], reverse=True)
    picks = valid[: cfg.top_n]

    # 8. 构造结果
    results: list[ScanResult] = []
    for s in picks:
        action, advice = _technical_action_advice(s)
        results.append(
            ScanResult(
                code=s["code"],
                name=s["name"],
                price=s["price"],
                chg_pct=s["chg_pct"],
                amount_yi=s["amount_yi"],
                turnover=s["turnover"],
                score=s["score"],
                mom_5d=round(s.get("mom_5d", 0), 2),
                mom_20d=round(s.get("mom_20d", 0), 2),
                vol_ratio=round(s.get("vol_ratio", 1.0), 2),
                trend_pct=round(s.get("trend_pct", 0), 2),
                industry=s.get("industry", ""),
                sector_group=s.get("sector_group", ""),
                sector_resonance=s.get("sector_resonance", ""),
                sector_bonus=round(s.get("sector_bonus", 0), 1),
                ai_action=s.get("ai_action", ""),
                ai_confidence=s.get("ai_confidence", 0.0),
                ai_reason=s.get("ai_reason", ""),
                risk_level=s.get("risk_level", ""),
                action=action,
                advice=advice,
            )
        )

    elapsed = time.time() - t0
    logger.info(
        "Scan complete: %d candidates in %.1fs, avg_score=%d",
        len(results),
        elapsed,
        sum(r.score for r in results) // max(len(results), 1),
    )

    return results


def diff_results(
    prev: list[ScanResult], curr: list[ScanResult]
) -> dict[str, list[ScanResult]]:
    """对比两次扫描结果，返回新增/移除/持续的标的。"""
    prev_codes = {p.code for p in prev}
    curr_codes = {p.code for p in curr}
    new_codes = curr_codes - prev_codes
    gone_codes = prev_codes - curr_codes
    return {
        "new": [p for p in curr if p.code in new_codes],
        "gone": [p for p in prev if p.code in gone_codes],
        "staying": [p for p in curr if p.code in prev_codes],
    }
