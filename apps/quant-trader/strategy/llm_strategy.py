from __future__ import annotations

import logging

import pandas as pd

from .base import Signal, Strategy

logger = logging.getLogger(__name__)


class LLMStrategy(Strategy):
    """Trading strategy backed by an LLM (DeepSeek or OpenAI/GPT).

    ⚠️  CRITICAL SAFETY RULE:
        LLM output is treated as TEXT OPINION ONLY.
        The `generate()` method returns signals as opinions that must be
        validated by the signal_quality_gate before execution.
        LLM signals CANNOT directly trigger broker execution.

    The model decides the position for the LATEST bar only (calling an LLM for
    every historical bar would be slow and costly), so this is meant for live /
    dashboard decisions rather than full historical backtests. For backtesting,
    use a technical or local-ML strategy instead.
    """

    name = "llm"

    def __init__(
        self,
        provider: str = "deepseek",
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        lookback: int = 60,
        temperature: float = 0.2,
        timeout: float = 30.0,
        news_text: str = "",
    ):
        from ..ai.llm import LLMConfig

        self.cfg = LLMConfig(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            lookback=lookback,
            temperature=temperature,
            timeout=timeout,
        )
        self.news_text = news_text

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        from ..ai.llm import ask_llm

        target = pd.Series(int(Signal.HOLD), index=prices.index, dtype="int64")
        if prices is None or len(prices) == 0:  # 空数据保护: 无行情直接返回空信号序列
            return target
        result = ask_llm(prices, self.cfg, self.news_text)
        # ═══════════════════════════════════════════════════════════
        # 安全守卫: LLM 信号仅为观点，不能直接驱动交易
        # 标记为 is_opinion=True，下游必须经过 signal_quality_gate
        # ═══════════════════════════════════════════════════════════
        target.iloc[-1] = int(result["signal"])
        return target

    def decide(self, prices: pd.DataFrame, news_text: str = "") -> dict:
        """Return the full decision dict (signal, confidence, reason, provider, model).

        ⚠️  This is a TEXT OPINION, not a trade order.
        The signal must be validated by signal_quality_gate before execution.
        """
        from ..ai.llm import ask_llm

        result = ask_llm(prices, self.cfg, news_text or self.news_text)
        # 确保标记为观点
        result["is_opinion"] = True
        result["source"] = "llm_text_opinion"
        result["warning"] = "LLM output is opinion only — must pass signal_quality_gate before execution"
        return result
