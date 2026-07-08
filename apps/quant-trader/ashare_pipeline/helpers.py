"""共享工具函数: 新闻获取、行情归一化、缓存包装、SSE 推送."""
from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..log import get_logger
from .constants import (
    _CACHE_MAX_SIZE,
    _CACHE_TTL_S,
    _PRICE_CACHE,
    PipelineProfile,
    resolve_pipeline_profile,
)
from .dataclasses import PipelineResult
from .scoring import score_one_round2

logger = get_logger("pipeline")


# ── Price normalization ─────────────────────────────────────────────

def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """归一化行情列名 + 清洗."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = df.dropna(subset=["close"])
    return df


# ── News helper ─────────────────────────────────────────────────────

def news_for_symbol(symbol: str) -> dict:
    """拉取单只标的新闻情绪 (带超时)."""
    from ..news.feeds import fetch_news
    from ..news.parser import analyze_items

    def _fetch() -> dict:
        try:
            items, _ = fetch_news(symbol, "auto", 8)
            if not items:
                return {"score": 50.0, "label": "neutral", "count": 0, "sentiment_raw": 0.0}
            sent = analyze_items(items)
            return {"score": max(0.0, min(100.0, 50.0 + sent.score * 40.0)),
                    "label": sent.label, "count": len(items), "sentiment_raw": sent.score}
        except Exception:
            return {"score": 50.0, "label": "neutral", "count": 0, "sentiment_raw": 0.0}

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_fetch)
        try:
            return fut.result(timeout=6)
        except Exception:
            return {"score": 50.0, "label": "neutral", "count": 0, "sentiment_raw": 0.0}


# ── Cache wrapper ───────────────────────────────────────────────────

def cached_loader(loader_fn: Callable[[str], pd.DataFrame | None]) -> Callable[[str], pd.DataFrame | None]:
    """进程内行情缓存，重复运行秒开."""
    def load(code: str) -> pd.DataFrame | None:
        now = time.time()
        hit = _PRICE_CACHE.get(code)
        if hit and now - hit[0] < _CACHE_TTL_S:
            return hit[1]
        df = loader_fn(code)
        if df is not None and not df.empty:
            if len(_PRICE_CACHE) >= _CACHE_MAX_SIZE:
                oldest_key = min(_PRICE_CACHE, key=lambda k: _PRICE_CACHE[k][0])
                del _PRICE_CACHE[oldest_key]
            _PRICE_CACHE[code] = (now, df)
        return df
    return load


# ── Estimate pipeline seconds ───────────────────────────────────────

def estimate_pipeline_seconds(
    kind: str = "stock",
    pool_size: int = 50,
    top_n: int = 10,
    use_news: bool = False,
    profile="fast",
) -> float:
    """预估管线耗时 (秒)，供前端倒计时."""
    prof = profile if isinstance(profile, PipelineProfile) else resolve_pipeline_profile(
        profile if isinstance(profile, str) else "fast",
    )
    per_symbol = 0.45 if kind == "future" else 0.55
    pool = min(pool_size, prof.pool_cap)
    news_factor = 1.1 if use_news and not prof.force_no_news else 1.0
    scan = pool * per_symbol * news_factor * 0.12
    depth = max(top_n, 1) * 0.45
    overhead = 1.5 if kind == "stock" else 1.0
    return round(max(4.0, scan + depth + overhead), 0)


# ── Apply round2 result ─────────────────────────────────────────────

def apply_round2_result(r: PipelineResult, prices_map: dict, loader_fn) -> None:
    """对单个 PipelineResult 执行深度分析 (Round2)."""
    try:
        prices = prices_map.get(r.symbol) or loader_fn(r.symbol)
        if prices is None:
            return
        r2 = score_one_round2(prices)
        if r2 is None:
            return
        for k, v in r2.items():
            setattr(r, k, v)
    except Exception:
        pass


# ── Refresh row depth fields ────────────────────────────────────────

def refresh_row_depth_fields(r: PipelineResult) -> None:
    """深度分析完成后刷新单行的预测字段 (供流式推送)."""
    from .scoring import make_prediction, tech_score
    if r.round2_score is None:
        return
    r.tech_score = tech_score(r)
    r.prediction_3d = make_prediction(r.win_rate_3d, r.avg_return_3d)
    r.prediction_5d = make_prediction(r.win_rate_5d, r.avg_return_5d)
    r.prediction_7d = make_prediction(r.win_rate_7d, r.avg_return_7d)
    r.prediction_30d = make_prediction(r.win_rate_30d, r.avg_return_30d)
