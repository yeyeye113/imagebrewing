"""Strategy that blends technical signals with news sentiment.

⚠️  REDESIGNED: News module now acts as RISK BLOCKER only.
    - neutral news: NO score change
    - positive news: +1 to +3 points max (not used for signal generation)
    - negative news: -5 to -15 points (risk reduction only)
    - high_risk news: BLOCK all trades
    - News never generates BUY/SELL signals on its own
"""

from __future__ import annotations

import pandas as pd

from .base import Signal, Strategy, get_strategy


class NewsBlendStrategy(Strategy):
    """Wrap a base strategy and filter signals using news risk level.

    ⚠️  CRITICAL CHANGE: News is now a RISK BLOCKER, not a signal generator.
        - neutral news: no effect
        - positive news: slight confidence boost (+1-3 points)
        - negative news: reduce position (-5-15 points)
        - high_risk news: BLOCK all BUY/SELL signals

    Parameters
    ----------
    base : underlying strategy name (sma_cross, rsi, ...)
    news_risk_level : "low" | "medium" | "high" (from assess_news_risk)
    sentiment : -1..+1 aggregate news score (for reference only, not for signal gen)
    block_high_risk : if True, block all trades when news_risk_level == "high"
    """

    name = "news_blend"

    def __init__(
        self,
        base: str = "sma_cross",
        sentiment: float = 0.0,
        news_weight: float = 0.3,
        block_bearish: bool = True,
        confirm_bullish: bool = False,  # ⚠️ DISABLED: news should not upgrade signals
        sentiment_threshold: float = 0.15,
        news_risk_level: str = "low",
        block_high_risk: bool = True,
        **base_params,
    ):
        base_params = {
            k: v
            for k, v in base_params.items()
            if k
            not in (
                "base",
                "sentiment",
                "news_weight",
                "block_bearish",
                "confirm_bullish",
                "sentiment_threshold",
                "news_risk_level",
                "block_high_risk",
                "name",
            )
        }
        self.base_strategy = get_strategy(base, **base_params)
        self.sentiment = float(sentiment)
        self.news_weight = float(news_weight)
        self.block_bearish = block_bearish
        self.confirm_bullish = confirm_bullish  # 默认关闭
        self.threshold = float(sentiment_threshold)
        self.news_risk_level = news_risk_level
        self.block_high_risk = block_high_risk

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        tech = self.base_strategy.generate(prices).reindex(prices.index).fillna(Signal.HOLD)
        out = tech.copy()
        s = self.sentiment
        th = self.threshold * (1.0 - self.news_weight * 0.5)

        # ═══════════════════════════════════════════════════════════
        # 风险否决: 高风险新闻直接阻断所有交易
        # ═══════════════════════════════════════════════════════════
        if self.block_high_risk and self.news_risk_level == "high":
            out[:] = Signal.HOLD
            return out.astype("int64").clip(-1, 1)

        # ═══════════════════════════════════════════════════════════
        # 负面新闻阻断: bearish 新闻抑制 BUY 信号
        # ═══════════════════════════════════════════════════════════
        if self.block_bearish and s < -th:
            out = out.where(out != Signal.BUY, Signal.HOLD)

        # ═══════════════════════════════════════════════════════════
        # 注意: confirm_bullish 默认关闭
        # 新闻 positive 不应升级 HOLD 为 BUY
        # ═══════════════════════════════════════════════════════════
        # if self.confirm_bullish and s > th:
        #     ma = prices["close"].rolling(20, min_periods=5).mean()
        #     boost = (prices["close"] > ma) & (out == Signal.HOLD)
        #     out = out.where(~boost, Signal.BUY)

        # 强烈负面: 双重阻断
        if s < -th * 2:
            out = out.where(out != Signal.BUY, Signal.HOLD)

        return out.astype("int64").clip(-1, 1)

    @classmethod
    def from_news_items(cls, items: list, base: str = "sma_cross", horizon: str = "medium", **params):
        from ..news.parser import analyze_items, assess_news_risk

        sent = analyze_items(items)
        risk = assess_news_risk(items, sent)

        # 新闻只作为风险过滤器，不参与信号生成
        return cls(
            base=base,
            sentiment=sent.score,
            news_risk_level=risk["risk_level"],
            block_high_risk=risk["should_block"],
            **params,
        ), sent
