"""统一信号生产者门面 — 收敛 voter / prediction_v2 / deep_dip 等多入口.

新代码应通过 ``get_signal_producer(name).produce(...)`` 获取信号,
旧 voter 模块保留但标记为 legacy, 逐步迁移到此门面。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

from ..log import get_logger

logger = get_logger("signal_producer")

# legacy 入口登记 (只读文档用途, 便于 IDE/审计追踪)
LEGACY_PRODUCERS: dict[str, str] = {
    "voter": "quanttrader.engine.voter",
    "forecast": "quanttrader.forecast",
}


@dataclass
class ProducedSignal:
    """统一信号输出."""
    symbol: str
    direction: int          # -1 / 0 / +1
    confidence: float       # 0~100
    source: str
    label: str = "HOLD"
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "direction_label": self.label,
            "confidence": round(self.confidence, 2),
            "source": self.source,
            "reason": self.reason,
            "meta": self.meta,
        }


class SignalProducer(Protocol):
    name: str

    def produce(self, symbol: str, prices: pd.DataFrame, **ctx: Any) -> ProducedSignal | None: ...


class DeepDipProducer:
    """唯一实证 edge 策略 — 深超跌反转."""
    name = "deep_dip"

    def produce(self, symbol: str, prices: pd.DataFrame, **ctx: Any) -> ProducedSignal | None:
        from ..strategy.base import Signal, get_strategy

        params = ctx.get("params") or {
            "ma_long": 60, "ma_exit": 20, "entry_dev": -0.10, "max_hold": 60,
        }
        if prices is None or len(prices) < int(params.get("ma_long", 60)) + 2:
            return None
        sig = get_strategy("deep_dip", **params).generate(prices)
        latest = int(sig.iloc[-1]) if len(sig) else 0
        if latest == int(Signal.BUY):
            close = float(prices["close"].iloc[-1])
            ma60 = float(prices["close"].rolling(int(params["ma_long"])).mean().iloc[-1])
            dev = close / ma60 - 1 if ma60 else 0.0
            return ProducedSignal(
                symbol=symbol, direction=1, confidence=min(95.0, 55 + abs(dev) * 200),
                source=self.name, label="BUY",
                reason=f"深超跌 dev_MA60={dev:.1%}",
                meta={"dev_ma60": dev, "params": params},
            )
        return ProducedSignal(
            symbol=symbol, direction=0, confidence=0.0,
            source=self.name, label="HOLD", reason="无深超跌入场",
        )


class PredictionV2Producer:
    """11 层预测引擎 (production / research 档位)."""
    name = "prediction_v2"

    def produce(self, symbol: str, prices: pd.DataFrame, **ctx: Any) -> ProducedSignal | None:
        from ..prediction_engine_v2 import OOS_BENCHMARK, predict_single

        profile = ctx.get("profile", "research")
        pred = predict_single(prices, symbol, ctx.get("name", ""), profile=profile)
        if pred is None:
            return None
        return ProducedSignal(
            symbol=symbol,
            direction=pred.direction,
            confidence=pred.confidence,
            source=self.name,
            label=pred.direction_label,
            reason=f"{pred.layers_agree}/{pred.layers_total} 层同意",
            meta={"mode": pred.mode, "oos": OOS_BENCHMARK, "layers_agree": pred.layers_agree},
        )


_PRODUCERS: dict[str, type[SignalProducer]] = {
    "deep_dip": DeepDipProducer,
    "dip": DeepDipProducer,
    "prediction_v2": PredictionV2Producer,
    "precise": PredictionV2Producer,
    "v2": PredictionV2Producer,
}


def get_signal_producer(name: str) -> SignalProducer:
    key = (name or "deep_dip").strip().lower()
    cls = _PRODUCERS.get(key)
    if cls is None:
        legacy = LEGACY_PRODUCERS.get(key)
        hint = f" (legacy 模块: {legacy})" if legacy else ""
        raise ValueError(f"未知 SignalProducer: {name!r}{hint}")
    return cls()


def list_producers() -> list[str]:
    return sorted(set(_PRODUCERS) | set(LEGACY_PRODUCERS))
