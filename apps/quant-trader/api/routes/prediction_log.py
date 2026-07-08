"""Prediction log routes: /prediction-log/*."""
from __future__ import annotations

from fastapi import Depends

from ..schemas import (
    DeviationResponse,
    FillActualsResponse,
    GlobalDeviationResponse,
    PredictionLogEntry,
    PredictionLogResponse,
)


def register_prediction_log_routes(app, shared, auth):
    """Register prediction log query endpoints."""

    @app.get("/prediction-log/recent", response_model=PredictionLogResponse, dependencies=[Depends(auth)])
    def prediction_log_recent(symbol: str = "", limit: int = 50, kind: str = ""):
        entries = shared.prediction_logger.get_recent_predictions(symbol=symbol, n=limit, kind=kind)
        return PredictionLogResponse(
            entries=[PredictionLogEntry(**e.to_dict()) for e in entries],
            total=len(entries),
            limit=limit,
            symbol=symbol,
            kind=kind,
        )

    @app.get("/prediction-log/symbol/{symbol}", response_model=PredictionLogResponse, dependencies=[Depends(auth)])
    def prediction_log_symbol(symbol: str, limit: int = 100, filled_only: bool = False):
        entries = shared.prediction_logger.get_predictions_for_symbol(symbol, filled_only=filled_only)
        return PredictionLogResponse(
            entries=[PredictionLogEntry(**e.to_dict()) for e in entries[:limit]],
            total=len(entries),
            limit=limit,
            symbol=symbol,
        )

    @app.post("/prediction-log/fill", response_model=FillActualsResponse, dependencies=[Depends(auth)])
    def prediction_log_fill():
        summary = shared.prediction_logger.fill_actuals()
        filled_logs = shared.prediction_logger.get_filled_predictions(n=500)
        n_synced = shared.strategy_journal.sync_outcomes_from_predictions(filled_logs)
        shared.strategy_journal.generate_summary(append_history=True)
        return FillActualsResponse(
            n_processed=summary["n_processed"],
            n_filled=summary["n_filled"],
            n_skipped=summary["n_skipped"],
            n_errors=summary["n_errors"],
            message=f"已处理 {summary['n_processed']} 条，填充 {summary['n_filled']} 条，"
                    f"跳过 {summary['n_skipped']} 条，出错 {summary['n_errors']} 条。"
                    f" 策略信号同步 {n_synced} 条，已更新策略总结。",
        )

    @app.get("/prediction-log/deviation", response_model=GlobalDeviationResponse, dependencies=[Depends(auth)])
    def prediction_log_deviation_global():
        stats = shared.deviation_tracker.compute_global_stats()
        return GlobalDeviationResponse(**stats)

    @app.get("/prediction-log/deviation/{symbol}", response_model=DeviationResponse, dependencies=[Depends(auth)])
    def prediction_log_deviation_symbol(symbol: str):
        stats = shared.deviation_tracker.compute_symbol_deviation(symbol)
        return DeviationResponse(**stats.to_dict())
