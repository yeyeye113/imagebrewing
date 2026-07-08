"""增强分析: 多因子评分 + 可迭代筛选 + 单标的分析 + 公开 API."""
from __future__ import annotations

import time

import pandas as pd

from ..log import get_logger
from ..screening_journal import ScreeningWeights
from .constants import FUTURES_POOL, STOCK_50
from .loaders import _load_futures_prices, _load_stock_prices
from .scoring import finalize
from .serialize import result_to_dict
from .wuxing_helpers import resolve_future_meta, resolve_stock_meta

logger = get_logger("pipeline")

# Re-export analysis subpackage
from ..analysis import default_screener, indicator_summary, multi_factor_score, volume_summary


def analyze_with_factors(
    symbol: str,
    *,
    name: str = "",
    kind: str = "stock",
    use_screener: bool = True,
    factor_weights: dict[str, float] | None = None,
) -> dict:
    """增强版单标的分析: 多因子评分 + 可迭代筛选器."""
    loader = _load_stock_prices if kind == "stock" else _load_futures_prices
    if kind == "stock":
        code, dn, sector, element = resolve_stock_meta(symbol, name)
    else:
        code, dn, sector, element = resolve_future_meta(symbol, name)

    t0 = time.time()
    prices = loader(code)
    if prices is None or len(prices) < 30:
        return {
            "symbol": code, "name": dn, "kind": kind,
            "status": "no_data", "error": "无法加载行情数据",
            "elapsed_s": round(time.time() - t0, 2),
        }

    factors = multi_factor_score(prices, factor_weights)
    indicators = indicator_summary(prices)
    volume = volume_summary(prices)

    screener_result = None
    if use_screener:
        screener = default_screener(min_pass_ratio=0.5, factor_weights=factor_weights)
        screener_result = screener.screen(code, dn, prices)

    return {
        "symbol": code, "name": dn, "kind": kind, "sector": sector, "element": element,
        "status": "ok",
        "factor_score": factors["composite"], "factor_grade": factors["grade"],
        "factor_signal": factors["signal"], "factors": factors["factors"],
        "top_signals": factors["top_signals"],
        "indicators": {
            "macd": indicators.get("macd", {}), "atr": indicators.get("atr", {}),
            "kdj": indicators.get("kdj", {}), "obv": indicators.get("obv", {}),
            "vwap": indicators.get("vwap", {}), "ma_alignment": indicators.get("ma_alignment", {}),
            "ichimoku": indicators.get("ichimoku", {}),
            "composite": indicators.get("composite_score", 50),
        },
        "volume": {
            "ratio": volume.get("volume_ratio", {}), "obv_slope": volume.get("obv_slope", {}),
            "divergence": volume.get("vp_divergence", {}), "money_flow": volume.get("money_flow", {}),
            "composite": volume.get("composite_score", 50),
        },
        "screener": screener_result.to_dict() if screener_result else None,
        "passed_screener": screener_result.passed if screener_result else None,
        "elapsed_s": round(time.time() - t0, 3),
    }


def run_enhanced_pipeline(
    kind: str = "stock",
    top_n: int = 10,
    factor_weights: dict[str, float] | None = None,
    min_factor_score: float = 55.0,
) -> tuple[list[dict], dict]:
    """增强版批量筛选管线: 多因子 + 可迭代筛选器."""
    t0 = time.time()
    symbols = STOCK_50 if kind == "stock" else FUTURES_POOL
    loader = _load_stock_prices if kind == "stock" else _load_futures_prices
    screener = default_screener(min_pass_ratio=0.5, factor_weights=factor_weights)

    results = []
    for code, name, sector, element in symbols:
        try:
            prices = loader(code)
            if prices is None or len(prices) < 60:
                continue
            factors = multi_factor_score(prices, factor_weights)
            if factors["composite"] < min_factor_score:
                continue
            screen = screener.screen(code, name, prices)
            results.append({
                "symbol": code, "name": name, "sector": sector, "element": element,
                "factor_score": factors["composite"], "factor_grade": factors["grade"],
                "factor_signal": factors["signal"],
                "screener_passed": screen.passed, "screener_score": screen.composite_score,
                "screener_grade": screen.grade, "top_signals": factors["top_signals"],
                "rejection_reasons": screen.rejection_reasons,
                "filters": [{"name": f.name, "passed": f.passed, "score": round(f.score, 1)} for f in screen.filters],
            })
        except Exception as e:
            logger.warning("[enhanced] %s %s 异常: %s", code, name, e)

    results.sort(key=lambda x: (x["screener_passed"], x["screener_score"]), reverse=True)
    results = results[:top_n]
    log = {
        "kind": kind, "total_scanned": len(symbols),
        "passed_min_score": sum(1 for r in results if r["factor_score"] >= min_factor_score),
        "passed_screener": sum(1 for r in results if r["screener_passed"]),
        "top_n": len(results), "elapsed_s": round(time.time() - t0, 2),
    }
    return results, log


# ═══════════════════════════════════════════════════════════════════════
# 单标的分析 (自选股票 / 期货)
# ═══════════════════════════════════════════════════════════════════════

def _trend_gate_detail(prices: pd.DataFrame, kind: str = "stock") -> dict:
    from .gates import check_trend
    passed, trend_s = check_trend(prices, kind=kind)
    close = prices["close"]
    ret_20d = float(close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0.0
    ma60 = close.rolling(60).mean()
    above_ma = (
        float(close.iloc[-1]) > float(ma60.iloc[-1])
        if len(ma60) > 0 and pd.notna(ma60.iloc[-1]) else False
    )
    if passed:
        detail = f"20日 {ret_20d*100:+.1f}% · 价在 MA60 之上"
    elif ret_20d <= 0:
        detail = f"20日涨幅 {ret_20d*100:+.1f}% 未为正"
    elif not above_ma:
        detail = f"收盘价低于 MA60（20日 {ret_20d*100:+.1f}%）"
    else:
        detail = "趋势条件未满足"
    return {"id": "trend", "label": "趋势", "passed": passed, "score": round(trend_s, 1), "detail": detail}


def _resonance_gate_detail(prices: pd.DataFrame, kind: str = "stock", min_score: float = 72.0) -> dict:
    from .scoring import resonance_and_score
    passed_r, ind = resonance_and_score(prices, kind=kind)
    if not ind:
        return {
            "id": "resonance", "label": "策略共振", "passed": False,
            "score": None, "detail": "多策略未形成多头共振（需 ≥3 策略同向看多）",
        }
    sig = ind.get("signal", "HOLD")
    score = ind.get("score", 0)
    ok = passed_r and score >= min_score and sig == "BUY"
    if ok:
        detail = f"共振通过 · 初筛分 {score:.0f} · {sig}"
    elif sig != "BUY":
        detail = f"信号 {sig}，非 BUY（初筛分 {score:.0f}）"
    elif score < min_score:
        detail = f"初筛分 {score:.0f} 低于门槛 {min_score:.0f}"
    else:
        detail = "策略共振不足"
    return {"id": "resonance", "label": "策略共振", "passed": ok, "score": round(score, 1), "detail": detail}


def _wuxing_gate_detail(
    code: str, name: str, sector: str, element: str,
    kind: str = "stock", use_wuxing: bool = True,
    div_reading=None, bazi_reading=None,
) -> dict:
    _ = (code, name, sector, element, kind, use_wuxing, div_reading, bazi_reading)
    return {"id": "wuxing", "label": "五行/卦象", "passed": True, "skipped": True, "detail": "已下线"}


def _analyze_one(
    code: str, name: str, sector: str, element: str,
    loader_fn, kind: str,
    *, use_news: bool, use_wuxing: bool,
    weights: ScreeningWeights | None,
    round1_min_score: float,
    in_pool: bool,
) -> dict:
    """单标的完整分析 — 与批量管线同一套闸门 + 深度回测."""
    from ..advisor import invest_advice_for_symbol
    from .engine import _screen_one_symbol
    from .helpers import apply_round2_result, news_for_symbol, refresh_row_depth_fields

    sw = (weights or ScreeningWeights()).normalized()
    t0 = time.time()
    gates: list[dict] = []

    prices = loader_fn(code)
    if prices is None or len(prices) < 60:
        gates.append({"id": "data", "label": "行情数据", "passed": False, "detail": "无法加载 ≥60 日 K 线，请检查代码或稍后重试"})
        return {
            "symbol": code, "name": name, "kind": kind, "in_pool": in_pool,
            "status": "no_data", "passes_pipeline": False,
            "gates": gates, "item": None, "advice": [],
            "elapsed_s": round(time.time() - t0, 2),
        }

    gates.append(_trend_gate_detail(prices, kind=kind))
    gates.append(_resonance_gate_detail(prices, kind=kind, min_score=round1_min_score))

    div_reading = bazi_reading = None

    gates.append(_wuxing_gate_detail(
        code, name, sector, element, kind=kind, use_wuxing=use_wuxing,
        div_reading=div_reading, bazi_reading=bazi_reading,
    ))

    r, _ = _screen_one_symbol(
        code, name, sector, element, prices, kind,
        use_wuxing, round1_min_score, sw, div_reading, bazi_reading,
    )
    if r is None:
        return {
            "symbol": code, "name": name, "kind": kind, "in_pool": in_pool,
            "status": "filtered", "passes_pipeline": False,
            "gates": gates, "item": None, "advice": [],
            "summary": "未通过三关筛选，可参考上方闸门明细调整预期。",
            "elapsed_s": round(time.time() - t0, 2),
        }

    if use_news:
        ns = news_for_symbol(code)
        r.news_score = ns["score"]
        r.news_label = ns["label"]
        r.news_count = ns["count"]
        if ns["label"] == "bearish" and ns["sentiment_raw"] < -0.3:
            r.combined_score = max(0.0, r.combined_score - 3.0)
        elif ns["label"] == "bullish":
            r.combined_score = min(100.0, r.combined_score + 2.0)
        r.combined_score = r.combined_score * (1.0 - sw.news) + r.news_score * sw.news
        gates.append({
            "id": "news", "label": "新闻情绪", "passed": True,
            "score": round(r.news_score, 1),
            "detail": f"{r.news_label or '—'} · {r.news_count or 0} 条",
        })
    else:
        gates.append({"id": "news", "label": "新闻情绪", "passed": True, "skipped": True, "detail": "未启用（与左侧参数一致）"})

    prices_map = {code: prices}
    r.selected_top10 = True
    apply_round2_result(r, prices_map, loader_fn)
    refresh_row_depth_fields(r)
    finalize([r], sw)

    passes = r.signal == "BUY" and (r.final_score or 0) >= 72
    advice = invest_advice_for_symbol(
        code, r.name, r.horizon_best or "short",
        r.tech_score or 0,
        r.prediction_7d or r.prediction_3d or "—",
        r.prediction_30d or "—",
        r.confidence or 0,
    )
    summary = (
        f"综合分 {r.final_score:.0f} · 技术 {r.tech_score:.0f} · 置信 {((r.confidence or 0)*100):.0f}%"
        if passes else
        f"分析完成但未达优选门槛（综合分 {r.final_score:.0f}）"
    )
    return {
        "symbol": code, "name": r.name, "kind": kind, "in_pool": in_pool,
        "status": "ok", "passes_pipeline": passes,
        "gates": gates, "item": result_to_dict(r), "advice": advice,
        "summary": summary,
        "elapsed_s": round(time.time() - t0, 2),
    }


def analyze_single_stock(
    symbol: str,
    *,
    name: str = "",
    use_news: bool = True,
    use_wuxing: bool = True,
    weights: ScreeningWeights | None = None,
    round1_min_score: float = 72.0,
) -> dict:
    code, dn, sector, element = resolve_stock_meta(symbol, name)
    in_pool = any(c == code for c, *_ in STOCK_50)
    return _analyze_one(
        code, dn, sector, element, _load_stock_prices, "stock",
        use_news=use_news, use_wuxing=use_wuxing,
        weights=weights, round1_min_score=round1_min_score, in_pool=in_pool,
    )


def analyze_single_future(
    symbol: str,
    *,
    name: str = "",
    use_news: bool = True,
    use_wuxing: bool = True,
    weights: ScreeningWeights | None = None,
    round1_min_score: float = 70.0,
) -> dict:
    code, dn, sector, element = resolve_future_meta(symbol, name)
    in_pool = any(c == code for c, *_ in FUTURES_POOL)
    return _analyze_one(
        code, dn, sector, element, _load_futures_prices, "future",
        use_news=use_news, use_wuxing=use_wuxing,
        weights=weights, round1_min_score=round1_min_score, in_pool=in_pool,
    )
