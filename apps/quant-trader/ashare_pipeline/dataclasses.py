"""PipelineResult dataclass — extracted from the old monolith pipeline.py."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PipelineResult:
    symbol: str; name: str = ""; type: str = "stock"
    sector: str = ""; element: str = ""
    round1_score: float = 0.0
    sma_score: float = 0.0; rsi_score: float = 0.0
    boll_score: float = 0.0; mom_score: float = 0.0
    signal: str = "HOLD"; last_price: float = 0.0
    news_score: float = 50.0; news_label: str = ""; news_count: int = 0
    wuxing_score: float = 50.0; wuxing_element: str = ""; wuxing_relation: str = ""
    combined_score: float = 0.0; selected_top10: bool = False
    round2_score: float | None = None
    win_rate_3d: float | None = None; win_rate_5d: float | None = None
    win_rate_7d: float | None = None
    win_rate_30d: float | None = None
    avg_return_3d: float | None = None; avg_return_5d: float | None = None
    avg_return_7d: float | None = None
    avg_return_30d: float | None = None
    sharpe_round2: float | None = None
    final_score: float = 0.0
    prediction_3d: str = "—"; prediction_5d: str = "—"; prediction_7d: str = "—"
    prediction_30d: str = "—"
    confidence: float = 0.0; rank: int = 0
    correction_factor: float = 1.0; corrected: bool = False
    # 三关标记
    passed_resonance: bool = False
    passed_trend: bool = False
    passed_wuxing_gate: bool = False
    # 玄学深度
    bazi_score: float = 50.0; bazi_chang_sheng: str = ""; bazi_nayin: str = ""
    divination_score: float = 50.0; divination_bias: str = ""; divination_reading: str = ""
    meta_score: float = 0.0
    tech_score: float = 0.0
    short_term_advice: str = ""
    long_term_advice: str = ""
    horizon_best: str = "medium"
