"""管线子包 — 从原 pipeline.py 单体文件拆分而来.

所有公开符号在此重导出, 保证外部 import 路径不变:
  from .pipeline import run_stock_pipeline, PipelineResult, ...
"""
from __future__ import annotations

# ── Analysis (enhanced pipeline) ────────────────────────────────────
from .analysis import analyze_single_future, analyze_single_stock, analyze_with_factors, run_enhanced_pipeline

# ── Constants & Config ──────────────────────────────────────────────
from .constants import (
    _CACHE_MAX_SIZE,
    _CACHE_TTL_S,
    _LOADER_TIMEOUT_S,
    _PRICE_CACHE,
    _STAGES_PENDING,
    FUTURES_POOL,
    INITIAL_STRATEGIES,
    PROFILE_BALANCED,
    PROFILE_FAST,
    PROFILE_PRECISE,
    PROFILE_RESEARCH,
    RESONANCE_CORE_STRATEGIES,
    RESONANCE_WINDOWS,
    ROUND2_CORE_STRATEGIES,
    ROUND2_STRATEGIES,
    SECTOR_TO_WUXING,
    STOCK_50,
    STRATEGIES,
    TIME_WINDOWS,
    PipelineProfile,
    StageCallback,
    resolve_pipeline_profile,
)

# ── Dataclass ───────────────────────────────────────────────────────
from .dataclasses import PipelineResult

# ── Engine (main pipeline) ──────────────────────────────────────────
from .engine import (
    _apply_news_batch,
    _collect_screen_futures,
    _emit_stage,
    _precise_pred_to_pipeline_result,
    _prefetch_and_screen,
    _preview_items,
    _run_pipeline,
    _run_precise_futures_pipeline,
    _run_precise_stock_pipeline,
    _screen_one_symbol,
    result_to_stage_dict,
    run_futures_pipeline,
    run_stock_pipeline,
)

# ── Gates ───────────────────────────────────────────────────────────
from .gates import (
    check_resonance,
    check_trend,
    check_wuxing_gate,
    sector_preselect,
)

# ── Helpers ─────────────────────────────────────────────────────────
from .helpers import (
    apply_round2_result,
    news_for_symbol,
    normalize,
    refresh_row_depth_fields,
)

# ── Loaders ─────────────────────────────────────────────────────────
from .loaders import (
    _load_futures_prices,
    _load_stock_prices,
    cached_loader,
    estimate_pipeline_seconds,
    prefetch_prices,
)

# ── Scoring ─────────────────────────────────────────────────────────
from .scoring import (
    confidence_v2,
    finalize,
    forward_win_rates,
    horizon_guidance,
    make_prediction,
    pick_elite,
    quality_final_score,
    resonance_and_score,
    score_one_round1,
    score_one_round2,
    tech_score,
)

# ── Serialize ───────────────────────────────────────────────────────
from .serialize import result_to_dict, results_for_prediction_log

# ── Wuxing helpers ──────────────────────────────────────────────────
from .wuxing_helpers import resolve_future_meta, resolve_stock_meta

# ── Backwards compat aliases ────────────────────────────────────────
# Some code may import these with underscore prefix from the old monolith
_normalize = normalize
_news_for_symbol = news_for_symbol
_apply_round2_result = apply_round2_result
_refresh_row_depth_fields = refresh_row_depth_fields
_check_trend = check_trend
_check_wuxing_gate = check_wuxing_gate
_resonance_and_score = resonance_and_score
_sector_preselect = sector_preselect
_load_stock_prices = _load_stock_prices
_load_futures_prices = _load_futures_prices
_estimate_pipeline_seconds = estimate_pipeline_seconds
_pick_elite = pick_elite
_quality_final_score = quality_final_score
_finalize = finalize
_check_resonance = check_resonance

__all__ = [
    "FUTURES_POOL",
    "INITIAL_STRATEGIES",
    "PROFILE_BALANCED",
    "PROFILE_FAST",
    "PROFILE_PRECISE",
    "PROFILE_RESEARCH",
    "RESONANCE_CORE_STRATEGIES",
    "RESONANCE_WINDOWS",
    "ROUND2_CORE_STRATEGIES",
    "ROUND2_STRATEGIES",
    "SECTOR_TO_WUXING",
    "STOCK_50",
    "STRATEGIES",
    "TIME_WINDOWS",
    "_CACHE_MAX_SIZE",
    "_CACHE_TTL_S",
    "_LOADER_TIMEOUT_S",
    "_PRICE_CACHE",
    "_STAGES_PENDING",
    "PipelineProfile",
    "PipelineResult",
    "StageCallback",
    "_apply_news_batch",
    "_check_trend",
    "_check_wuxing_gate",
    "_collect_screen_futures",
    "_emit_stage",
    "_estimate_pipeline_seconds",
    "_load_futures_prices",
    "_load_stock_prices",
    "_news_for_symbol",
    "_normalize",
    "_precise_pred_to_pipeline_result",
    "_prefetch_and_screen",
    "_preview_items",
    "_refresh_row_depth_fields",
    "_resonance_and_score",
    "_run_pipeline",
    "_run_precise_futures_pipeline",
    "_run_precise_stock_pipeline",
    "_screen_one_symbol",
    "analyze_with_factors",
    "apply_round2_result",
    "cached_loader",
    "check_resonance",
    "check_trend",
    "check_wuxing_gate",
    "confidence_v2",
    "estimate_pipeline_seconds",
    "finalize",
    "forward_win_rates",
    "horizon_guidance",
    "make_prediction",
    "news_for_symbol",
    "normalize",
    "pick_elite",
    "prefetch_prices",
    "quality_final_score",
    "refresh_row_depth_fields",
    "resolve_future_meta",
    "resolve_pipeline_profile",
    "resolve_stock_meta",
    "resonance_and_score",
    "result_to_dict",
    "result_to_stage_dict",
    "results_for_prediction_log",
    "run_enhanced_pipeline",
    "run_futures_pipeline",
    "run_stock_pipeline",
    "score_one_round1",
    "score_one_round2",
    "sector_preselect",
    "tech_score",
]
