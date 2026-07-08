from __future__ import annotations

import abc
import enum

import pandas as pd


class Signal(enum.IntEnum):
    SELL = -1
    HOLD = 0
    BUY = 1


class Strategy(abc.ABC):
    """A strategy turns a price history into a series of target signals.

    ``generate`` returns a Series (aligned to ``prices.index``) of -1/0/1
    representing the *desired position* at each bar (short/flat/long). The
    engine compares consecutive targets to decide when to trade.
    """

    name: str = "base"

    @abc.abstractmethod
    def generate(self, prices: pd.DataFrame) -> pd.Series: ...


def get_strategy(name: str, **params) -> Strategy:
    name = (name or "sma_cross").lower()
    if name in ("sma_cross", "sma", "ma_cross"):
        from .sma_cross import SmaCrossStrategy

        return SmaCrossStrategy(**params)
    if name in ("rsi",):
        from .rsi import RsiStrategy

        return RsiStrategy(**params)
    if name in ("bollinger", "boll", "bbands"):
        from .bollinger import BollingerStrategy

        return BollingerStrategy(**params)
    if name in ("momentum", "mom", "trend"):
        from .momentum import MomentumStrategy

        return MomentumStrategy(**params)
    if name in ("ai", "ai_http", "external"):
        from .ai_strategy import AIStrategy

        return AIStrategy(**params)
    if name in ("news_blend", "news", "sentiment"):
        from .news_blend import NewsBlendStrategy

        return NewsBlendStrategy(**params)
    if name in ("llm", "deepseek", "gpt", "openai"):
        from .llm_strategy import LLMStrategy

        # The provider name can double as the strategy name (deepseek/gpt).
        if name in ("deepseek", "gpt", "openai") and "provider" not in params:
            params["provider"] = name
        return LLMStrategy(**params)
    if name in ("ml", "ml_strategy", "machine_learning", "sklearn"):
        from ..ml.strategy import MLStrategy

        return MLStrategy(**params)
    # ── 高级策略 (融合自工作区版 advanced_strategies.py) ──
    if name in ("macd_cross", "macd"):
        from .advanced_strategies import MacdCrossStrategy
        return MacdCrossStrategy(**params)
    if name in ("kdj", "stochastic"):
        from .advanced_strategies import KdjStrategy
        return KdjStrategy(**params)
    if name in ("ichimoku", "cloud"):
        from .advanced_strategies import IchimokuStrategy
        return IchimokuStrategy(**params)
    if name in ("volume_breakout", "vol_break"):
        from .advanced_strategies import VolumeBreakoutStrategy
        return VolumeBreakoutStrategy(**params)
    if name in ("ma_ribbon", "ribbon"):
        from .advanced_strategies import MaRibbonStrategy
        return MaRibbonStrategy(**params)
    if name in ("vwap_cross", "vwap"):
        from .advanced_strategies import VwapCrossStrategy
        return VwapCrossStrategy(**params)
    if name in ("supertrend", "st"):
        from .advanced_strategies import SupertrendStrategy
        return SupertrendStrategy(**params)
    # ── 均值回归 (融合自工作区版 mean_reversion.py) ──
    if name in ("deep_dip", "deepdip", "mean_reversion", "dip"):
        from .mean_reversion import DeepDipReversalStrategy
        return DeepDipReversalStrategy(**params)
    # ── 双向趋势跟随 (融合自工作区版 trend_follow.py, 期货 CTA 主力信号) ──
    if name in ("trend_follow", "trend_ma", "cta_trend"):
        from .trend_follow import TrendFollowStrategy
        return TrendFollowStrategy(**params)
    raise ValueError(f"Unknown strategy: {name!r}")
