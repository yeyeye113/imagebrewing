"""高低点预测v4 — hv_mult+atr_mult自适应+per-symbol"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_WEIGHTS_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "hl_method_weights.json"


@dataclass
class HighLowPrediction:
    symbol: str
    current_price: float
    predicted_high: float
    predicted_low: float
    high_confidence: float
    low_confidence: float
    method: str
    reasoning: str
    regime: str = "unknown"
    method_weights: dict | None = None


class HighLowPredictor:
    """v4: hv×mult + pivot×w + atr×mult×w, per-symbol自适应"""

    def __init__(self, weights_path: str | Path | None = None):
        self._weights_path = Path(weights_path) if weights_path else _WEIGHTS_FILE
        self._weights_data = self._load_weights()

    def _load_weights(self) -> dict:
        if self._weights_path.exists():
            try:
                data = json.loads(self._weights_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {
            "global_config": {"atr_mult": 2.0, "hv_mult": 0.65, "hv_w": 0.85, "piv_w": 0.0, "atr_w": 0.15},
            "active_per_symbol": {},
        }

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """归一到品种键：期货取字母前缀(RB2410/RB0→RB)，无字母标的(股票)保持原样。

        原实现 rstrip('0') 会错删多位合约月份(RB2410→RB241、AG2400→AG24)导致
        per-symbol 配置错配；字母前缀对连续/主力/具体合约都稳定。
        """
        s = symbol.upper().strip()
        m = re.match(r"[A-Z]+", s)
        return m.group(0) if m else s

    def _get_symbol_config(self, symbol: str) -> dict:
        per_sym = self._weights_data.get("active_per_symbol", {})
        sym_key = self._normalize_symbol(symbol)
        default = {
            "atr_mult": 2.0, "hv_mult": 0.65, "hv_w": 0.85,
            "piv_w": 0.0, "atr_w": 0.15,
        }
        # per-symbol 与 global 两个分支都用 default 补全缺失键,
        # 避免不完整的权重文件导致 predict() 内 cfg[...] KeyError。
        src = per_sym[sym_key] if sym_key in per_sym else self._weights_data.get("global_config", {})
        return {k: src.get(k, v) for k, v in default.items()}

    def predict(self, prices: pd.DataFrame, symbol: str = "", horizon: int = 1) -> HighLowPrediction:
        if prices is None or len(prices) < 20:
            return self._default_prediction(prices, symbol)

        closes = prices["close"].astype(float)
        current = float(closes.iloc[-1])
        cfg = self._get_symbol_config(symbol)

        # historical_vol
        vol_lookback = self._weights_data.get("vol_lookback", 20)
        returns = closes.pct_change().dropna()
        # 日波动率(不年化)：直接用于「振幅 ≈ 现价 × hv_mult × 日波动」估高低点。
        # horizon>1 时按 √horizon 缩放(波动随时间开方增长)，与 v530 predict_range 语义对齐；
        # horizon=1(默认)退化为原「预测下一根」行为，保持 forecast 调用向后兼容。
        vol = float(returns.tail(vol_lookback).std())
        hz = math.sqrt(horizon) if horizon and horizon > 1 else 1.0
        hv_h = current * (1 + cfg["hv_mult"] * vol * hz)
        hv_l = current * (1 - cfg["hv_mult"] * vol * hz)

        # pivot
        highs = prices["high"].astype(float)
        lows = prices["low"].astype(float)
        prev_high = float(highs.iloc[-2])
        prev_low = float(lows.iloc[-2])
        prev_close = float(closes.iloc[-2])
        pivot = (prev_high + prev_low + prev_close) / 3
        piv_h = pivot + (prev_high - prev_low)
        piv_l = pivot - (prev_high - prev_low)

        # atr
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(tr.mean())
        atr_h = current + cfg["atr_mult"] * atr14
        atr_l = current - cfg["atr_mult"] * atr14

        # 加权
        high_pred = hv_h * cfg["hv_w"] + piv_h * cfg["piv_w"] + atr_h * cfg["atr_w"]
        low_pred = hv_l * cfg["hv_w"] + piv_l * cfg["piv_w"] + atr_l * cfg["atr_w"]

        # 置信度：基于参与预测的多方法(hv/pivot/atr)估计的离散度，分歧越小越自信。
        # 改进原「仅 hv vs atr + 魔法系数3」：纳入 pivot、改用无量纲极差/现价度量。
        # 注：三法同源于价格波动、彼此相关，该值表征「方法一致性」而非命中概率；
        #     命中概率校准需接入 hl_predictions 历史误差(见 tracker.compute_hl_stats)。
        high_conf = self._consistency_conf([(hv_h, cfg["hv_w"]), (piv_h, cfg["piv_w"]), (atr_h, cfg["atr_w"])], current)
        low_conf = self._consistency_conf([(hv_l, cfg["hv_w"]), (piv_l, cfg["piv_w"]), (atr_l, cfg["atr_w"])], current)

        if high_pred < current:
            high_pred = current * 1.02
        if low_pred > current:
            low_pred = current * 0.98

        return HighLowPrediction(
            symbol=symbol, current_price=current,
            predicted_high=round(high_pred, 2), predicted_low=round(low_pred, 2),
            high_confidence=round(high_conf, 3), low_confidence=round(low_conf, 3),
            method="hv_pivot_atr_v4",
            reasoning=f"hv_mult={cfg['hv_mult']:.2f} atr_mult={cfg['atr_mult']:.1f} hv_w={cfg['hv_w']:.2f} piv={cfg['piv_w']:.2f} atr={cfg['atr_w']:.2f}",
            regime="adaptive",
            method_weights={"hv": cfg["hv_w"], "pivot": cfg["piv_w"], "atr": cfg["atr_w"]},
        )

    def _default_prediction(self, prices, symbol) -> HighLowPrediction:
        current = float(prices["close"].iloc[-1]) if prices is not None and len(prices) > 0 else 100.0
        return HighLowPrediction(
            symbol=symbol, current_price=current,
            predicted_high=current * 1.02, predicted_low=current * 0.98,
            high_confidence=0.3, low_confidence=0.3,
            method="default", reasoning="数据不足", regime="unknown",
        )

    @staticmethod
    def _consistency_conf(estimates: list[tuple[float, float]], current: float) -> float:
        """由多方法估计的离散度计算一致性置信度(0.1~0.9)。

        仅统计权重>0 的方法；极差越大(方法越分歧)置信越低。系数 10 表示
        「每 1% 分歧扣 0.1 置信」，封顶 0.9(较原 0.95 更保守)。
        """
        active = [v for v, w in estimates if w > 0]
        if current <= 0 or len(active) < 2:
            return 0.5
        spread = (max(active) - min(active)) / current
        return round(max(0.1, min(0.9, 0.9 - spread * 10)), 3)
