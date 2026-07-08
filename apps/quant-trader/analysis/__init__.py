"""分析研判中枢 — 高低点 + 时间轴 + 自由预测。

不做自动下单，只出研判报告和可执行建议。

子模块:
  highlow   — 关键高低点识别 (支撑/阻力/枢轴)
  timeline  — 交易计划时间轴 (入场/目标/止损/里程碑)
  predictor — 自由预测引擎 (LLM + 技术 + 玄学综合)
"""

from .factors import (
    FactorScore,
    mean_reversion_factor,
    momentum_factor,
    multi_factor_score,
    trend_factor,
    volatility_factor,
    volume_factor,
)
from .highlow import HighLowResult, find_highlows

# ── 合并(融合自工作区版): A股分析引擎 — 多因子/扩展指标/成交量/筛选器 ──
# 工作区版 prediction_engine_v2 / ashare_pipeline / enhanced_analysis 依赖以下符号
from .indicators import (
    calc_atr,
    calc_ichimoku,
    calc_kdj,
    calc_ma_alignment,
    calc_macd,
    calc_obv,
    calc_vwap,
    indicator_summary,
)
from .predictor import PredictionReport, free_predict
from .screener import (
    IterativeScreener,
    ScreenFilter,
    ScreenResult,
    default_screener,
)
from .timeline import TimelinePlan, build_timeline
from .volume import (
    calc_obv_slope,
    calc_volume_price_divergence,
    calc_volume_ratio,
    estimate_money_flow,
    volume_summary,
)
