"""序列化: PipelineResult ↔ dict 转换."""
from __future__ import annotations

from .dataclasses import PipelineResult


def result_to_dict(r: PipelineResult) -> dict:
    return {
        "symbol": r.symbol, "name": r.name, "type": r.type,
        "sector": r.sector, "element": r.element, "rank": r.rank,
        "round1_score": r.round1_score,
        "sma_score": r.sma_score, "rsi_score": r.rsi_score,
        "boll_score": r.boll_score, "mom_score": r.mom_score,
        "signal": r.signal, "last_price": r.last_price,
        "news_score": r.news_score, "news_label": r.news_label, "news_count": r.news_count,
        "wuxing_score": r.wuxing_score, "wuxing_element": r.wuxing_element,
        "wuxing_relation": r.wuxing_relation,
        "combined_score": r.combined_score, "selected_top10": r.selected_top10,
        "round2_score": r.round2_score,
        "win_rate_3d": r.win_rate_3d, "win_rate_5d": r.win_rate_5d,
        "win_rate_7d": r.win_rate_7d, "win_rate_30d": r.win_rate_30d,
        "avg_return_3d": r.avg_return_3d, "avg_return_5d": r.avg_return_5d,
        "avg_return_7d": r.avg_return_7d,
        "avg_return_30d": r.avg_return_30d, "sharpe_round2": r.sharpe_round2,
        "final_score": r.final_score,
        "prediction_3d": r.prediction_3d, "prediction_5d": r.prediction_5d,
        "prediction_7d": r.prediction_7d,
        "prediction_30d": r.prediction_30d, "confidence": r.confidence,
        "correction_factor": r.correction_factor, "corrected": r.corrected,
        "bazi_score": r.bazi_score, "bazi_chang_sheng": r.bazi_chang_sheng,
        "bazi_nayin": r.bazi_nayin,
        "divination_score": r.divination_score, "divination_bias": r.divination_bias,
        "divination_reading": r.divination_reading,
        "meta_score": r.meta_score,
        "tech_score": r.tech_score,
        "short_term_advice": r.short_term_advice,
        "long_term_advice": r.long_term_advice,
        "horizon_best": r.horizon_best,
        "passed_resonance": r.passed_resonance, "passed_trend": r.passed_trend,
        "passed_wuxing_gate": r.passed_wuxing_gate,
    }


def results_for_prediction_log(results: list[PipelineResult]) -> list[dict]:
    """Map pipeline results to PredictionLogger-compatible dicts."""
    out: list[dict] = []
    for r in results:
        d = result_to_dict(r)
        d["score"] = d.get("final_score", 0)
        d["corrected_score"] = d.get("final_score", 0)
        d["total_return_pct"] = d.get("total_return_pct", 0) if "total_return_pct" in d else 0
        d["sharpe"] = d.get("sharpe_round2") or 0
        d["max_drawdown_pct"] = 0
        d["change_1w_pct"] = (d.get("avg_return_7d") or 0) * 100
        d["change_1m_pct"] = (d.get("avg_return_30d") or 0) * 100
        out.append(d)
    return out
