from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Bar(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarsResponse(BaseModel):
    symbol: str
    source: str
    interval: str
    bars: list[Bar]


class PriceResponse(BaseModel):
    symbol: str
    price: float
    source: str


class BacktestRequest(BaseModel):
    symbol: str = "AAPL"
    source: str = "synthetic"
    start: str = "2022-01-01"
    end: str = "2024-01-01"
    interval: str = "1d"
    strategy: str = "sma_cross"
    # Empty = use the chosen strategy's own defaults (e.g. sma_cross 20/50).
    params: dict = Field(default_factory=dict)
    cash: float = 100_000.0
    order_size: float = 0.25
    commission: float = 0.0005
    slippage: float = 0.0005
    lot_size: int = 1
    risk: dict = Field(default_factory=dict)
    sizing: dict = Field(
        default_factory=lambda: {
            "max_position_pct": 0.30,
            "max_total_exposure": 0.80,
            "cash_reserve_pct": 0.20,
            "max_weight_per_symbol": 0.25,
        }
    )
    horizon: str = "medium"
    use_news: bool = False
    news_source: str = "auto"
    apply_horizon_preset: bool = True
    engine: Literal["equity", "futures"] = "equity"
    futures: dict = Field(
        default_factory=lambda: {"leverage": 1.0, "cost": 0.0003, "target_vol": None}
    )


class BacktestResponse(BaseModel):
    symbol: str
    source: str
    strategy: str
    n_bars: int
    n_trades: int
    risk_events: int
    stats: dict
    buy_and_hold: float
    equity_curve: list[dict]
    tips: list[dict]
    risk_analysis: dict = Field(default_factory=dict)
    horizon: str = "medium"
    news: dict = Field(default_factory=dict)
    fills: list[dict] = Field(default_factory=list)
    signals: list[dict] = Field(default_factory=list)
    engine: str = "equity"


class PortfolioBacktestRequest(BaseModel):
    symbols: list[str]
    source: str = "synthetic"
    start: str = "2022-01-01"
    end: str = "2024-01-01"
    interval: str = "1d"
    strategy: str = "sma_cross"
    params: dict = Field(default_factory=dict)
    allocation: str = "equal"  # "equal" | "inverse_vol" | "risk_parity" | "min_variance"
    cash: float = 100_000.0
    order_size: float = 0.25
    commission: float = 0.0005
    slippage: float = 0.0005
    lot_size: int = 1
    risk: dict = Field(default_factory=dict)
    sizing: dict = Field(
        default_factory=lambda: {
            "max_position_pct": 0.30,
            "max_total_exposure": 0.80,
            "cash_reserve_pct": 0.20,
            "max_weight_per_symbol": 0.25,
        }
    )


class PortfolioBacktestResponse(BaseModel):
    symbols: list[str]
    source: str
    strategy: str
    allocation: str
    weights: dict
    stats: dict
    per_symbol: dict
    equity_curve: list[dict]
    tips: list[dict]


class OptimizeRequest(BaseModel):
    symbol: str = "DEMO"
    source: str = "synthetic"
    start: str = "2022-01-01"
    end: str = "2024-01-01"
    interval: str = "1d"
    strategy: str = "sma_cross"
    grid: dict = Field(default_factory=dict)  # empty -> use DEFAULT_GRIDS[strategy]
    metric: str = "sharpe"
    n_splits: int = 4
    cash: float = 100_000.0
    risk: dict = Field(default_factory=dict)
    engine: Literal["equity", "futures"] = "equity"
    futures: dict = Field(default_factory=lambda: {"leverage": 1.0, "cost": 0.0003})
    min_trades: int = 2  # 过滤交易样本不足(<2 笔)的组合，杜绝零成交/单笔持有伪装的假最优


class OptimizeResponse(BaseModel):
    symbol: str
    source: str
    strategy: str
    metric: str
    best_params: dict
    best_score: float
    top: list[dict]
    walk_forward: dict


class OrderRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    notional: float | None = Field(default=None, description="Dollar amount (buy).")
    qty: float | None = Field(default=None, description="Share quantity (sell, or buy-by-qty).")
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = None
    source: str = "synthetic"
    note: str = ""


class OrderResponse(BaseModel):
    order: dict
    account: dict


class OrdersListResponse(BaseModel):
    orders: list[dict]


class SignalRequest(BaseModel):
    symbol: str
    signal: Literal[-1, 0, 1]
    notional: float | None = None
    source: str = "synthetic"


class AccountResponse(BaseModel):
    cash: float
    equity: float
    positions: list[dict]
    is_live: bool = False


class RiskAssessRequest(BaseModel):
    mode: Literal["trade", "portfolio"] = "trade"
    symbol: str = "DEMO"
    symbols: list[str] = Field(default_factory=list)
    source: str = "synthetic"
    start: str = "2022-01-01"
    end: str = "2024-01-01"
    interval: str = "1d"
    allocation: str = "equal"
    cash: float = 100_000.0
    equity: float | None = None
    position_value: float = 0.0
    order_size: float = 0.25
    commission: float = 0.0005
    slippage: float = 0.0005
    risk: dict = Field(
        default_factory=lambda: {
            "stop_loss": 0.08,
            "trailing_stop": 0.15,
            "max_drawdown": 0.25,
            "risk_per_trade": 0.01,
        }
    )
    sizing: dict = Field(
        default_factory=lambda: {
            "max_position_pct": 0.30,
            "max_total_exposure": 0.80,
            "cash_reserve_pct": 0.20,
            "max_weight_per_symbol": 0.25,
        }
    )


class RiskAssessResponse(BaseModel):
    mode: str
    source: str
    assessment: dict


class NewsAnalyzeRequest(BaseModel):
    symbol: str = "DEMO"
    source: str = "auto"
    limit: int = 20
    horizon: str = "medium"
    text: str = ""  # optional: analyze custom headline/text instead of fetching


class NewsAnalyzeResponse(BaseModel):
    symbol: str
    source: str
    horizon: str
    items: list[dict]
    sentiment: dict
    horizon_fit: dict
    recommendation: str
    keywords: list[str]


class SettingsUpdateRequest(BaseModel):
    broker: str | None = None  # paper | cn_paper | alpaca
    api_key: str | None = None  # broker API key
    api_secret: str | None = None  # broker API secret
    paper: bool | None = None  # alpaca: paper vs live
    allow_live: bool | None = None  # confirm real-money trading
    cash: float | None = None  # starting cash for paper brokers
    ai_endpoint: str | None = None  # external AI strategy HTTP endpoint
    ai_api_key: str | None = None  # bearer token for the AI endpoint
    llm_provider: str | None = None  # built-in LLM brain: deepseek | gpt
    llm_api_key: str | None = None  # LLM provider API key
    llm_model: str | None = None  # optional model override


class SettingsResponse(BaseModel):
    broker: str
    paper: bool
    live: bool
    has_broker_keys: bool
    cash: float
    ai_endpoint: str
    has_ai_key: bool
    llm_provider: str
    llm_model: str
    has_llm_key: bool


class PlaybookRequest(BaseModel):
    playbook: str = "short_momentum_news"
    symbols: list[str]
    news_symbols: list[str] | None = None
    source: str = "synthetic"
    start: str = "2022-01-01"
    end: str = "2024-01-01"
    interval: str = "1d"
    cash: float = 100_000.0
    commission: float = 0.0005
    slippage: float = 0.0005
    lot_size: int = 1
    use_news: bool = False  # pull live news sentiment into the news sleeve
    sentiment: float | None = None  # or inject a sentiment scenario (-1..1)


class PlaybookResponse(BaseModel):
    playbook: str
    label: str
    description: str
    source: str
    stats: dict
    weights: dict
    idle_cash_pct: float
    per_sleeve: dict
    equity_curve: list[dict]
    tips: list[dict]
    news: dict | None = None


class LLMRunRequest(BaseModel):
    symbol: str = "DEMO"
    source: str = "synthetic"
    use_news: bool = False
    execute: bool = False
    notional: float | None = None


class LLMRunResponse(BaseModel):
    symbol: str
    provider: str
    model: str
    signal: int
    label: str
    confidence: float
    reason: str
    executed: bool
    account: dict


class AIRunRequest(BaseModel):
    symbol: str = "DEMO"
    source: str = "synthetic"
    execute: bool = False
    notional: float | None = None


class AIRunResponse(BaseModel):
    symbol: str
    signal: int
    label: str
    executed: bool
    endpoint: str
    account: dict


# == 融合自工作区版: 预测/预测日志/Wuxing/增强预测 schemas ==
class PredictionItem(BaseModel):
    symbol: str
    name: str = ""
    score: float = 0.0
    signal: str = "HOLD"          # BUY/HOLD/SELL 策略共识方向
    sma_score: float = 0.0        # 双均线策略得分
    rsi_score: float = 0.0        # RSI 策略得分
    boll_score: float = 0.0       # 布林带策略得分
    mom_score: float = 0.0        # 动量策略得分
    last_price: float = 0.0
    change_1w_pct: float = 0.0
    change_1m_pct: float = 0.0
    sharpe: float = 0.0           # 平均 Sharpe
    total_return_pct: float = 0.0 # 平均回测收益
    max_drawdown_pct: float = 0.0 # 平均最大回撤
    # v0.5: 新闻 + 五行 + 矫正
    news_sentiment: float = 0.0    # −1..+1
    news_label: str = ""
    wuxing_score: float = 50.0     # 五行得分 0–100
    wuxing_element: str = ""       # 木/火/土/金/水
    wuxing_relation: str = ""      # 相比和/生我/我克/克我/我生
    corrected_score: float = 0.0   # 偏差矫正后最终得分


class PredictionResponse(BaseModel):
    stocks: list[PredictionItem]
    futures: list[PredictionItem]
    generated_at: str = ""
    note: str = "用软件自有 4 套策略(双均线/RSI/布林带/动量)回测打分，得分越高=未来一周上涨潜力越强。"
    correction_summary: dict = Field(default_factory=dict)
    errors_count: int = 0


# ── Prediction log / deviation tracking ──────────────────────────

class PredictionLogEntry(BaseModel):
    """Single prediction log record as returned by the API.

    Fields match the ``PredictionLog.to_dict()`` output exactly so
    ``PredictionLogEntry(**entry.to_dict())`` always works.
    """
    timestamp: str = ""
    symbol: str = ""
    name: str = ""
    type: str = "stock"      # "stock" | "future"
    score: float = 0.0
    signal: str = "HOLD"
    sma_score: float = 0.0
    rsi_score: float = 0.0
    boll_score: float = 0.0
    mom_score: float = 0.0
    last_price: float = 0.0
    change_1w_pct: float = 0.0
    change_1m_pct: float = 0.0
    sharpe: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    news_sentiment: float = 0.0
    news_label: str = ""
    wuxing_score: float = 50.0
    wuxing_element: str = ""
    wuxing_relation: str = ""
    corrected_score: float = 0.0
    actual_price_1w: float | None = None
    actual_price_1m: float | None = None
    actual_return_1w: float | None = None
    actual_return_1m: float | None = None
    deviation_1w: float | None = None
    deviation_1m: float | None = None
    filled: bool = False


class PredictionLogResponse(BaseModel):
    """Paginated / filtered prediction log response."""
    entries: list[PredictionLogEntry] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    symbol: str = ""
    kind: str = ""           # "stock" | "future" | ""


class FillActualsResponse(BaseModel):
    """Response after backfilling actual returns."""
    n_processed: int = 0
    n_filled: int = 0
    n_skipped: int = 0
    n_errors: int = 0
    message: str = ""


class DeviationResponse(BaseModel):
    """Per-symbol or global deviation statistics."""
    symbol: str = ""
    name: str = ""
    n_samples: int = 0
    rmse_1w: float = 0.0
    mae_1w: float = 0.0
    direction_accuracy_1w: float = 0.0
    mean_bias_1w: float = 0.0
    rmse_1m: float = 0.0
    mae_1m: float = 0.0
    direction_accuracy_1m: float = 0.0
    mean_bias_1m: float = 0.0
    calibration_factor: float = 1.0
    last_updated: str = ""


class GlobalDeviationResponse(BaseModel):
    """Aggregate deviation stats across all symbols."""
    n_total: int = 0
    n_filled: int = 0
    avg_rmse_1w: float = 0.0
    avg_mae_1w: float = 0.0
    mean_bias_1w: float = 0.0
    direction_accuracy: float = 0.0
    by_type: dict = Field(default_factory=dict)


class CorrectedPredictionItem(BaseModel):
    """Prediction item with optional correction applied.

    Fields must match ``apply_correction()`` output dict keys so
    ``CorrectedPredictionItem(**corrected_dict)`` always works.
    """
    symbol: str
    name: str = ""
    score: float = 0.0
    corrected_score: float = 0.0
    correction_factor: float = 1.0
    calibrated: bool = False
    signal: str = "HOLD"
    sma_score: float = 0.0
    rsi_score: float = 0.0
    boll_score: float = 0.0
    mom_score: float = 0.0
    last_price: float = 0.0
    change_1w_pct: float = 0.0
    change_1m_pct: float = 0.0
    sharpe: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    # v0.5: 新闻 + 五行
    news_sentiment: float = 0.0
    news_label: str = ""
    wuxing_score: float = 50.0
    wuxing_element: str = ""
    wuxing_relation: str = ""


class CorrectedPredictionResponse(BaseModel):
    """Prediction result with correction applied."""
    stocks: list[CorrectedPredictionItem]
    futures: list[CorrectedPredictionItem]
    generated_at: str = ""
    logged: int = 0              # number of entries written to log
    correction_summary: dict = Field(default_factory=dict)
    note: str = "⚠️ 量化技术面评分，不构成投资建议。得分越高=未来一周上涨的技术面信号越强。"


# ═══════════════════════════════════════════════════════════════════════
# 五行 (Wuxing) API schemas (v0.5)
# ═══════════════════════════════════════════════════════════════════════

class WuxingPowerItem(BaseModel):
    """五行力量单项."""
    element: str       # 木/火/土/金/水
    power: float       # 0..1 力量系数
    label: str = ""    # 旺/相/休/囚/死


class WuxingTodayResponse(BaseModel):
    """当日五行全貌."""
    date: str
    year_gan: str      # 年干
    year_zhi: str      # 年支
    month_gan: str     # 月干
    month_zhi: str     # 月支
    day_gan: str       # 日干
    day_zhi: str       # 日支
    day_element: str   # 日主五行
    season: str
    reigning: str      # 当令五行
    powers: list[WuxingPowerItem]  # 五行力量列表
    clash: str         # 日支相冲
    harmony: str       # 日支六合
    favorable_sectors: list[str]
    unfavorable_sectors: list[str]
    note: str


class WuxingSymbolResponse(BaseModel):
    """单个标的五行评分."""
    symbol: str
    name: str = ""
    element: str           # 木/火/土/金/水
    day_element: str       # 日主五行
    score: float           # 五行得分 0–100
    relation: str          # 相比和/生我/我克/克我/我生(泄)
    detail: str            # 可读解释


class EnhancedPredictRequest(BaseModel):
    """完整 6 步预测管线请求."""
    n_stocks: int = 5
    n_futures: int = 5
    use_news: bool = False
    use_wuxing: bool = False
    wuxing_weight: float = 0.15
    apply_correction: bool = False
    correction_weight: float = 0.3
