"""Prediction routes: /predict/*."""
from __future__ import annotations

import json as _json
import os

from fastapi.responses import Response, StreamingResponse

from ...prediction_service import (
    PredictionRequest,
    estimate_request,
    flow_self_check,
    persist_prediction_batch,
    run_prediction_batch,
    system_status,
)
from ...screening_journal import ScreeningWeights
from ..schemas import CorrectedPredictionItem, CorrectedPredictionResponse


def _sse_default(obj):
    if hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")


def _sse_json(payload: dict) -> str:
    return _json.dumps(payload, ensure_ascii=False, default=_sse_default)


def register_predict_routes(app, shared, auth):
    """Register prediction endpoints."""

    @app.get("/predict", deprecated=True)
    def predict(n_stocks: int = 5, n_futures: int = 5):
        from datetime import datetime

        from ...predict import rank_futures, rank_stocks, to_dict

        now = datetime.now().isoformat()
        try:
            stocks = rank_stocks(top_n=n_stocks)
        except Exception:
            stocks = []
        try:
            futures = rank_futures(top_n=n_futures)
        except Exception:
            futures = []

        shared.prediction_logger.log_predictions(stocks, futures, now)

        return CorrectedPredictionResponse(
            stocks=[CorrectedPredictionItem(**to_dict(s)) for s in stocks],
            futures=[CorrectedPredictionItem(**to_dict(f)) for f in futures],
            generated_at=now,
            logged=len(stocks) + len(futures),
        )

    @app.get("/predict/system")
    def predict_system():
        return system_status()

    @app.get("/predict/flow-check")
    def predict_flow_check():
        return flow_self_check()

    @app.get("/predict/estimate")
    def predict_estimate(
        n_stocks: int = 10,
        n_futures: int = 10,
        use_news: bool = False,
        profile: str = "fast",
        scope: str = "",
        top_n: int | None = None,
    ):
        req = PredictionRequest.from_scope(
            scope=scope, top_n=top_n, n_stocks=n_stocks, n_futures=n_futures,
            use_news=use_news, profile=profile,
        )
        return estimate_request(req)

    def _predict_run_sse(
        req: PredictionRequest,
        *,
        weight_tech: float | None = None,
        weight_news: float | None = None,
        weight_wuxing: float | None = None,
        weight_meta: float | None = None,
        save_weights_note: str = "api predict/run",
    ):
        import queue
        import threading

        sw = shared.screening_journal.load_weights()
        if any(v is not None for v in (weight_tech, weight_news, weight_wuxing, weight_meta)):
            sw = ScreeningWeights(
                tech=weight_tech if weight_tech is not None else sw.tech,
                news=weight_news if weight_news is not None else sw.news,
                wuxing=weight_wuxing if weight_wuxing is not None else sw.wuxing,
                meta=weight_meta if weight_meta is not None else sw.meta,
            ).normalized()
            shared.screening_journal.save_weights(sw, note=save_weights_note)
        req.weights = sw

        est = estimate_request(req)
        q: queue.Queue = queue.Queue()
        heartbeat_sec = float(os.environ.get("QT_SSE_HEARTBEAT", "8"))

        def _stage_cb():
            def cb(stage: str, items: list, meta: dict):
                kind = meta.get("_pipeline_kind") or ("stock" if req.n_futures <= 0 else "future")
                clean = {k: v for k, v in meta.items() if k != "_pipeline_kind"}
                q.put({"event": "stage", "stage": stage, "kind": kind, "items": items, **clean})
            return cb

        api_logger = shared.prediction_logger  # reuse for logging

        def _worker():
            try:
                batch = run_prediction_batch(PredictionRequest(
                    n_stocks=req.n_stocks, n_futures=req.n_futures,
                    use_news=req.use_news, use_wuxing=req.use_wuxing,
                    wuxing_weight=req.wuxing_weight, profile=req.profile,
                    apply_correction=req.apply_correction,
                    correction_weight=req.correction_weight,
                    weights=sw, on_stage=_stage_cb(),
                ))
                q.put({
                    "event": "stage", "stage": "finalizing", "partial": True, "step": 6,
                    "message": "写入日志与汇总…",
                })
                payload = persist_prediction_batch(
                    batch, shared.pred_deps,
                    apply_correction=req.apply_correction,
                    correction_weight=req.correction_weight,
                )
                payload["event"] = "complete"
                payload["stage"] = "complete"
                payload["partial"] = False
                payload["estimate_seconds"] = est
                q.put(payload)
            except Exception as exc:
                q.put({"event": "error", "stage": "error", "message": str(exc)})
            finally:
                q.put(None)

        threading.Thread(target=_worker, daemon=True).start()

        def _generate():
            yield "retry: 3000\n\n"
            accepted = {
                "event": "accepted",
                "stage": "accepted",
                "partial": True,
                "profile": est.get("profile", req.profile),
                "estimate_seconds": est,
                "api": "predict/run",
            }
            yield f"data: {_sse_json(accepted)}\n\n"
            while True:
                try:
                    item = q.get(timeout=heartbeat_sec)
                except queue.Empty:
                    yield f"data: {_sse_json({'event': 'heartbeat', 'stage': 'heartbeat'})}\n\n"
                    continue
                if item is None:
                    break
                try:
                    yield f"data: {_sse_json(item)}\n\n"
                except Exception:
                    yield f"data: {_sse_json({'event': 'error', 'stage': 'error', 'message': 'serialize failed'})}\n\n"
                    break

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/predict/run")
    def predict_run(
        scope: str = "",
        n_stocks: int = 10,
        n_futures: int = 10,
        top_n: int | None = None,
        use_news: bool = False,
        use_wuxing: bool = False,
        wuxing_weight: float = 0.05,
        apply_correction: bool = False,
        profile: str = "fast",
        weight_tech: float | None = None,
        weight_news: float | None = None,
        weight_wuxing: float | None = None,
        weight_meta: float | None = None,
    ):
        req = PredictionRequest.from_scope(
            scope=scope, top_n=top_n, n_stocks=n_stocks, n_futures=n_futures,
            use_news=use_news, use_wuxing=use_wuxing, wuxing_weight=wuxing_weight,
            apply_correction=apply_correction, profile=profile,
        )
        return _predict_run_sse(
            req,
            weight_tech=weight_tech, weight_news=weight_news,
            weight_wuxing=weight_wuxing, weight_meta=weight_meta,
        )

    @app.get("/predict/stream")
    def predict_stream(
        scope: str = "",
        n_stocks: int = 10,
        n_futures: int = 10,
        top_n: int | None = None,
        use_news: bool = False,
        use_wuxing: bool = False,
        wuxing_weight: float = 0.05,
        apply_correction: bool = False,
        profile: str = "fast",
        weight_tech: float | None = None,
        weight_news: float | None = None,
        weight_wuxing: float | None = None,
        weight_meta: float | None = None,
    ):
        req = PredictionRequest.from_scope(
            scope=scope, n_stocks=n_stocks, n_futures=n_futures, top_n=top_n,
            use_news=use_news, use_wuxing=use_wuxing, wuxing_weight=wuxing_weight,
            apply_correction=apply_correction, profile=profile,
        )
        return _predict_run_sse(
            req,
            weight_tech=weight_tech, weight_news=weight_news,
            weight_wuxing=weight_wuxing, weight_meta=weight_meta,
            save_weights_note="api predict/stream",
        )

    @app.get("/predict/enhanced")
    def predict_enhanced(
        n_stocks: int = 10,
        n_futures: int = 10,
        use_news: bool = False,
        use_wuxing: bool = False,
        wuxing_weight: float = 0.05,
        apply_correction: bool = False,
        profile: str = "fast",
        scope: str = "",
        top_n: int | None = None,
        weight_tech: float | None = None,
        weight_news: float | None = None,
        weight_wuxing: float | None = None,
        weight_meta: float | None = None,
    ):
        sw = shared.screening_journal.load_weights()
        if any(v is not None for v in (weight_tech, weight_news, weight_wuxing, weight_meta)):
            sw = ScreeningWeights(
                tech=weight_tech if weight_tech is not None else sw.tech,
                news=weight_news if weight_news is not None else sw.news,
                wuxing=weight_wuxing if weight_wuxing is not None else sw.wuxing,
                meta=weight_meta if weight_meta is not None else sw.meta,
            ).normalized()
            shared.screening_journal.save_weights(sw, note="api predict/enhanced")

        req = PredictionRequest.from_scope(
            scope=scope, top_n=top_n, n_stocks=n_stocks, n_futures=n_futures,
            use_news=use_news, use_wuxing=use_wuxing, wuxing_weight=wuxing_weight,
            apply_correction=apply_correction, profile=profile, weights=sw,
        )
        batch = run_prediction_batch(req)
        payload = persist_prediction_batch(
            batch, shared.pred_deps,
            apply_correction=req.apply_correction,
            correction_weight=req.correction_weight,
        )
        payload["note"] = "6步预测管线。推荐 /predict/run 获得更快首屏。不构成投资建议。"
        payload["flags"] = {
            "use_news": batch.effective_news,
            "use_wuxing": batch.effective_wuxing,
            "wuxing_weight": wuxing_weight,
            "apply_correction": apply_correction,
            "profile": batch.profile.name,
        }
        payload["event"] = "complete"
        payload["stage"] = "complete"
        return Response(
            content=_json.dumps(payload, ensure_ascii=False, default=_sse_default),
            media_type="application/json; charset=utf-8",
        )

    @app.get("/predict/growth_ranking")
    def predict_growth_ranking(
        n_stocks: int = 10,
        n_futures: int = 10,
        use_news: bool = False,
        use_wuxing: bool = False,
        profile: str = "fast",
        scope: str = "",
    ):
        req = PredictionRequest.from_scope(
            scope=scope, n_stocks=n_stocks, n_futures=n_futures,
            use_news=use_news, use_wuxing=use_wuxing, profile=profile,
        )
        batch = run_prediction_batch(req)
        all_items = batch.all_items

        groups: dict[str, list[dict]] = {"short": [], "medium": [], "long": []}
        for r in all_items:
            hb = getattr(r, "horizon_best", "medium")
            entry = {
                "symbol": r.symbol, "name": r.name, "type": r.type,
                "sector": r.sector, "horizon_best": hb,
                "final_score": r.final_score,
                "win_rate_3d": r.win_rate_3d, "avg_return_3d": r.avg_return_3d,
                "win_rate_7d": r.win_rate_7d, "avg_return_7d": r.avg_return_7d,
                "win_rate_30d": r.win_rate_30d, "avg_return_30d": r.avg_return_30d,
                "prediction_3d": r.prediction_3d, "prediction_7d": r.prediction_7d,
                "prediction_30d": r.prediction_30d,
                "signal": r.signal, "confidence": r.confidence,
                "last_price": r.last_price,
            }
            bucket = hb if hb in groups else "medium"
            groups[bucket].append(entry)

        for k in groups:
            groups[k].sort(key=lambda x: x["final_score"], reverse=True)
            groups[k] = groups[k][:5]

        return {
            "short_term_3d": {
                "label": "短线 (3天)",
                "items": groups["short"],
                "count": len(groups["short"]),
            },
            "medium_term_7d": {
                "label": "中线 (7天)",
                "items": groups["medium"],
                "count": len(groups["medium"]),
            },
            "long_term_30d": {
                "label": "长线 (30天)",
                "items": groups["long"],
                "count": len(groups["long"]),
            },
            "total": len(all_items),
            "note": "按最佳增长周期分组，每组取综合评分 Top5。不构成投资建议。",
        }
