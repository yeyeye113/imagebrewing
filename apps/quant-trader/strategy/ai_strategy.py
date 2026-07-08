from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from .base import Signal, Strategy


class AIStrategy(Strategy):
    """Delegate signal generation to an external AI "brain".

    Two plug-in modes:

    1. HTTP endpoint (``endpoint=``): the engine POSTs recent OHLCV bars as JSON
       and the AI service returns trading signals. This lets *any* external AI
       (LLM agent, ML model, another service) drive the strategy over the
       network without touching this codebase.

    2. Python callable (``fn=``): an in-process function
       ``fn(prices: DataFrame) -> Series|list[int]`` for embedding a model
       directly.

    Expected AI response (HTTP, JSON) — either form is accepted:
        {"signals": [-1, 0, 1, ...]}   # aligned to the bars sent (full history)
        {"signal": 1}                  # decision for the latest bar only

    Signal values: 1 = go long, 0 = flat, -1 = exit/short.
    """

    name = "ai"

    def __init__(
        self,
        endpoint: str | None = None,
        fn: Callable[[pd.DataFrame], pd.Series | list[int]] | None = None,
        lookback: int = 200,
        timeout: float = 15.0,
        api_key: str | None = None,
    ):
        if not endpoint and not fn:
            raise ValueError("AIStrategy needs either an `endpoint` URL or a `fn` callable.")
        self.endpoint = endpoint
        self.fn = fn
        self.lookback = int(lookback)
        self.timeout = timeout
        self.api_key = api_key

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        if self.fn is not None:
            raw = self.fn(prices)
            return self._coerce(raw, prices)
        return self._generate_http(prices)

    def _generate_http(self, prices: pd.DataFrame) -> pd.Series:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise ImportError("`requests` is required for HTTP AIStrategy. pip install requests") from exc

        window = prices.tail(self.lookback)
        payload = {
            "bars": [{"time": str(ts), **{k: float(v) for k, v in row.items()}} for ts, row in window.iterrows()]
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        target = pd.Series(Signal.HOLD, index=prices.index, dtype="int64")
        if "signals" in data:
            sig = self._coerce(data["signals"], window)
            target.loc[sig.index] = sig.values
        elif "signal" in data:
            target.iloc[-1] = int(data["signal"])
        else:
            raise ValueError("AI response must contain 'signals' (list) or 'signal' (int).")
        return target.clip(-1, 1)

    @staticmethod
    def _coerce(raw, prices: pd.DataFrame) -> pd.Series:
        if isinstance(raw, pd.Series):
            s = raw.reindex(prices.index).fillna(Signal.HOLD)
        else:
            vals = list(raw)
            if len(vals) != len(prices):
                # Right-align: assume the AI returned signals for the tail bars.
                vals = ([Signal.HOLD] * (len(prices) - len(vals)) + vals)[-len(prices) :]
            s = pd.Series(vals, index=prices.index)
        return s.astype("int64").clip(-1, 1)
