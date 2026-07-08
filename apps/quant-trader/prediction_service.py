"""预测系统集合体 — 统一入口 orchestrating pipeline + journals.

所有预测路径 (SSE / 同步 JSON / CLI) 应经此模块，保证:
  - 同一 profile / 有效开关 (news/wuxing)
  - 同一日志与 journal 写入链
  - 结构化错误而非静默空结果
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .ashare_pipeline import (
    FUTURES_POOL,
    PROFILE_FAST,
    STOCK_50,
    PipelineProfile,
    PipelineResult,
    StageCallback,
    estimate_pipeline_seconds,
    resolve_pipeline_profile,
    result_to_dict,
    results_for_prediction_log,
    run_futures_pipeline,
    run_stock_pipeline,
)
from .log import get_logger
from .market_schedule import market_schedule
from .screening_journal import ScreeningRunLog, ScreeningWeights

if TYPE_CHECKING:
    from .live_panel import LivePanelTracker
    from .prediction_log import DeviationTracker, PredictionLogger
    from .screening_journal import ScreeningJournal
    from .strategy_journal import StrategyJournal

logger = get_logger("prediction")


@dataclass
class PredictionRequest:
    """统一预测请求 — API / CLI / 内部调用共用."""
    n_stocks: int = 10
    n_futures: int = 10
    use_news: bool = False
    use_wuxing: bool = False
    wuxing_weight: float = 0.05
    apply_correction: bool = False
    correction_weight: float = 0.3
    profile: str = "fast"
    weights: ScreeningWeights | None = None
    on_stage: StageCallback | None = None

    @classmethod
    def from_scope(
        cls,
        scope: str = "",
        top_n: int | None = None,
        n_stocks: int = 10,
        n_futures: int = 10,
        **kwargs,
    ) -> PredictionRequest:
        scope_l = (scope or "").strip().lower()
        if scope_l == "stock":
            n_stocks = top_n if top_n is not None else n_stocks
            n_futures = 0
        elif scope_l == "future":
            n_futures = top_n if top_n is not None else n_futures
            n_stocks = 0
        elif top_n is not None:
            if n_stocks > 0 and n_futures == 0:
                n_stocks = top_n
            elif n_futures > 0 and n_stocks == 0:
                n_futures = top_n
        return cls(n_stocks=n_stocks, n_futures=n_futures, **kwargs)


@dataclass
class PredictionDeps:
    """运行时依赖 — 由 API 或 CLI 注入."""
    prediction_logger: PredictionLogger
    deviation_tracker: DeviationTracker
    screening_journal: ScreeningJournal
    live_panel: LivePanelTracker
    strategy_journal: StrategyJournal


@dataclass
class PredictionBatchResult:
    stock_results: list[PipelineResult] = field(default_factory=list)
    future_results: list[PipelineResult] = field(default_factory=list)
    stock_log: dict = field(default_factory=dict)
    future_log: dict = field(default_factory=dict)
    profile: PipelineProfile = field(default_factory=lambda: PROFILE_FAST)
    effective_news: bool = False
    effective_wuxing: bool = False
    weights: ScreeningWeights = field(default_factory=ScreeningWeights)
    errors: list[str] = field(default_factory=list)
    n_stocks: int = 0
    n_futures: int = 0

    @property
    def all_items(self) -> list[PipelineResult]:
        return self.stock_results + self.future_results

    @property
    def elapsed_seconds(self) -> dict:
        return {
            "stock": self.stock_log.get("elapsed_s"),
            "future": self.future_log.get("elapsed_s"),
        }


def effective_flags(req: PredictionRequest, prof: PipelineProfile | None = None) -> tuple[PipelineProfile, bool, bool]:
    prof = prof or resolve_pipeline_profile(req.profile)
    # 新闻/五行融合已从产品面下线，请求开关一律忽略
    return prof, False, False


def estimate_request(req: PredictionRequest) -> dict:
    prof, eff_news, _ = effective_flags(req)
    stock_est = (
        estimate_pipeline_seconds("stock", len(STOCK_50), req.n_stocks, eff_news, prof)
        if req.n_stocks > 0 else 0
    )
    future_est = (
        estimate_pipeline_seconds("future", len(FUTURES_POOL), req.n_futures, eff_news, prof)
        if req.n_futures > 0 else 0
    )
    return {
        "profile": prof.name,
        "stock_seconds": stock_est,
        "future_seconds": future_est,
        "total_seconds": stock_est + future_est,
    }


def apply_pipeline_correction(
    results: list[PipelineResult],
    tracker: DeviationTracker,
    weight: float = 0.3,
) -> list[PipelineResult]:
    if not results or weight <= 0:
        return results
    for r in results:
        cf = tracker.calibration_factor(r.symbol)
        r.correction_factor = cf
        if cf != 1.0:
            blended = r.final_score * (1.0 - weight) + r.final_score * cf * weight
            r.final_score = round(max(0.0, min(100.0, blended)), 1)
            r.corrected = True
    results.sort(key=lambda x: x.final_score, reverse=True)
    for i, r in enumerate(results, 1):
        r.rank = i
    return results


def _scoped_stage_cb(kind: str, cb: StageCallback | None) -> StageCallback | None:
    """Wrap stage callback so multiplex consumers (SSE) know stock vs future."""
    if cb is None:
        return None

    def wrapped(stage: str, items: list, meta: dict) -> None:
        cb(stage, items, {**meta, "_pipeline_kind": kind})

    return wrapped


def run_prediction_batch(req: PredictionRequest) -> PredictionBatchResult:
    """执行股票/期货管线 (可带 on_stage 流式回调)."""
    prof, eff_news, eff_wuxing = effective_flags(req)
    sw = (req.weights or ScreeningWeights()).normalized()
    out = PredictionBatchResult(
        profile=prof,
        effective_news=eff_news,
        effective_wuxing=eff_wuxing,
        weights=sw,
        n_stocks=req.n_stocks,
        n_futures=req.n_futures,
    )
    stock_cb = _scoped_stage_cb("stock", req.on_stage)
    future_cb = _scoped_stage_cb("future", req.on_stage)

    if req.n_stocks > 0:
        try:
            out.stock_results, out.stock_log = run_stock_pipeline(
                top_n=req.n_stocks,
                use_news=eff_news,
                use_wuxing=eff_wuxing,
                wuxing_weight=req.wuxing_weight,
                weights=sw,
                on_stage=stock_cb,
                profile=prof,
            )
        except Exception as exc:
            logger.exception("stock pipeline failed")
            out.errors.append(f"stock: {exc}")
            out.stock_results, out.stock_log = [], {"error": str(exc)}

    if req.n_futures > 0:
        try:
            out.future_results, out.future_log = run_futures_pipeline(
                top_n=req.n_futures,
                use_news=eff_news,
                use_wuxing=eff_wuxing,
                wuxing_weight=req.wuxing_weight,
                weights=sw,
                on_stage=future_cb,
                profile=prof,
            )
        except Exception as exc:
            logger.exception("future pipeline failed")
            out.errors.append(f"future: {exc}")
            out.future_results, out.future_log = [], {"error": str(exc)}

    return out


def persist_prediction_batch(
    batch: PredictionBatchResult,
    deps: PredictionDeps,
    *,
    apply_correction: bool = False,
    correction_weight: float = 0.3,
    timestamp: str | None = None,
) -> dict:
    """写入 prediction_log + screening + live_panel + strategy journals."""
    now = timestamp or datetime.now().isoformat()
    stocks = list(batch.stock_results)
    futures = list(batch.future_results)

    if apply_correction:
        stocks = apply_pipeline_correction(stocks, deps.deviation_tracker, correction_weight)
        futures = apply_pipeline_correction(futures, deps.deviation_tracker, correction_weight)

    stocks_log = results_for_prediction_log(stocks)
    futures_log = results_for_prediction_log(futures)
    if apply_correction:
        for d in stocks_log + futures_log:
            cf = deps.deviation_tracker.calibration_factor(d.get("symbol", ""))
            if cf and cf != 1.0:
                d["corrected_score"] = min(100.0, d.get("score", 0) * cf)

    deps.prediction_logger.log_predictions(stocks_log, futures_log, now)
    all_items = stocks + futures

    deps.screening_journal.log_run(ScreeningRunLog(
        timestamp=now,
        kind="both",
        weights=batch.weights.to_dict(),
        n_results=len(all_items),
        avg_final_score=round(sum(r.final_score for r in all_items) / max(len(all_items), 1), 1),
        avg_tech_score=round(sum(r.tech_score for r in all_items) / max(len(all_items), 1), 1),
        top_symbols=[r.symbol for r in all_items[:5]],
        note=f"news={batch.effective_news} wuxing={batch.effective_wuxing} profile={batch.profile.name}",
    ))

    sched = market_schedule()
    gstats = deps.deviation_tracker.compute_global_stats()
    live_snap = deps.live_panel.record_from_results(
        all_items,
        timestamp=now,
        calibrated_accuracy=gstats.get("direction_accuracy"),
        session_window=sched.current_window,
        note=f"n={len(all_items)}",
    )
    n_strategy_signals = deps.strategy_journal.log_signals_from_results(all_items, timestamp=now)
    strategy_light = deps.strategy_journal.update_summary_light()

    est = estimate_request(PredictionRequest(
        n_stocks=batch.n_stocks,
        n_futures=batch.n_futures,
        use_news=batch.effective_news,
        use_wuxing=batch.effective_wuxing,
        profile=batch.profile.name,
    ))

    return {
        "profile": batch.profile.name,
        "screening_weights": batch.weights.to_dict(),
        "live_panel": live_snap.to_dict(),
        "market_schedule": sched.to_dict(),
        "strategy_signals_logged": n_strategy_signals,
        "strategy_primary": strategy_light.get("primary_strategy"),
        "stocks": {
            "items": [result_to_dict(r) for r in stocks],
            "count": len(stocks),
            "pipeline_log": batch.stock_log,
        },
        "futures": {
            "items": [result_to_dict(r) for r in futures],
            "count": len(futures),
            "pipeline_log": batch.future_log,
        },
        "generated_at": now,
        "elapsed_seconds": batch.elapsed_seconds,
        "estimate_seconds": est,
        "errors": batch.errors,
        "logged": len(stocks_log) + len(futures_log),
    }


def system_status() -> dict:
    """预测子系统状态快照 — 供看板 / 运维."""
    from .ashare_pipeline import _PRICE_CACHE

    return {
        "engine": "pipeline_v1",
        "universe": {"stocks": len(STOCK_50), "futures": len(FUTURES_POOL)},
        "profiles": {
            "fast": {"default": True, "desc": "首屏优先，纯技术面管线"},
            "balanced": {"default": False, "desc": "与 fast 相同（新闻/五行已下线）"},
        },
        "endpoints": {
            "primary_sse": "/predict/run",
            "estimate": "/predict/estimate",
            "sync": "/predict/enhanced",
            "analyze": "/screening/analyze/{symbol}",
            "legacy": "/predict",
        },
        "price_cache_entries": len(_PRICE_CACHE),
    }


def flow_self_check() -> dict:
    """看板用户旅程自检 — 关键路径是否就绪."""
    est_s = estimate_pipeline_seconds("stock", len(STOCK_50), 10, False, "fast")
    est_f = estimate_pipeline_seconds("future", len(FUTURES_POOL), 10, False, "fast")
    checks = [
        {"id": "stock_universe", "ok": len(STOCK_50) >= 10, "label": f"股票池 {len(STOCK_50)} 只"},
        {"id": "future_universe", "ok": len(FUTURES_POOL) >= 5, "label": f"期货池 {len(FUTURES_POOL)} 只"},
        {"id": "estimate_stock", "ok": est_s >= 4, "label": f"股票预估 {est_s}s"},
        {"id": "estimate_future", "ok": est_f >= 4, "label": f"期货预估 {est_f}s"},
        {"id": "analyze_route", "ok": True, "label": "自选分析 /screening/analyze/{symbol}"},
    ]
    return {
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "user_flow": [
            "health → estimate → predict/run (SSE) | enhanced (降级)",
            "screening/analyze → 加入分配 → advisor/allocate",
        ],
    }
