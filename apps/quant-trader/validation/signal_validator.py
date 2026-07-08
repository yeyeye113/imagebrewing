"""信号验证器 — 过滤不可靠信号。

功能:
  - 位置检查
  - 趋势检查
  - 贵金属特殊处理
  - 能化板块EIA过滤

用法:
    from quanttrader.validation.signal_validator import SignalValidator
    validator = SignalValidator()
    signal, conf = validator.validate('RB', 'LONG', 0.75, hl_result)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class SignalValidator:
    """信号验证器。"""

    def __init__(self):
        self.rules = []

    def validate(
        self,
        code: str,
        signal: str,
        confidence: float,
        hl_result: Any = None,
        reason: str = "",
    ) -> tuple[str, float, list[str]]:
        """验证信号。

        Returns:
            (signal, confidence, reasons) — 可能被修改的信号和置信度
        """
        reasons = []

        # 规则1: 贵金属做多降级
        if code in ("AU", "AG") and signal == "LONG":
            signal = "NEUTRAL"
            confidence = 0.0
            reasons.append("贵金属做多风险高")

        # 规则2: NEUTRAL低置信
        elif signal == "NEUTRAL" and confidence < 0.5:
            confidence = 0.0
            reasons.append("观望信号置信度过低")

        # 规则3: 位置过高做多
        elif signal == "LONG" and hl_result and hl_result.position_pct > 80:
            confidence *= 0.7
            reasons.append(f"位置过高({hl_result.position_pct:.0f}%)")

        # 规则4: 位置过低做空
        elif signal == "SHORT" and hl_result and hl_result.position_pct < 20:
            confidence *= 0.7
            reasons.append(f"位置过低({hl_result.position_pct:.0f}%)")

        # 规则5: 趋势冲突
        if signal == "LONG" and hl_result and "下降" in hl_result.trend:
            confidence *= 0.8
            reasons.append("趋势向下")

        if signal == "SHORT" and hl_result and "上升" in hl_result.trend:
            confidence *= 0.8
            reasons.append("趋势向上")

        # 规则6: 能化EIA过滤
        if code in ("SC", "FU", "MA", "TA", "SA"):
            now = datetime.now()
            if now.weekday() == 2 and 9 <= now.hour <= 11:
                signal = "NEUTRAL"
                confidence = 0.0
                reasons.append("EIA数据前不操作")

        # 规则7: 新闻驱动降级
        if "新闻" in reason or "美联储" in reason:
            confidence *= 0.8
            reasons.append("新闻驱动信号降权")

        # 上限封顶
        confidence = min(confidence, 0.85)

        return signal, round(confidence, 2), reasons

    def batch_validate(self, predictions: list[dict], hl_results: dict) -> list[dict]:
        """批量验证。"""
        validated = []
        for pred in predictions:
            code = pred.get("symbol", "")
            signal = pred.get("signal", "NEUTRAL")
            confidence = pred.get("confidence", 0)
            reason = pred.get("reason", "")

            hl = hl_results.get(code)
            new_signal, new_conf, reasons = self.validate(code, signal, confidence, hl, reason)

            pred["signal"] = new_signal
            pred["confidence"] = new_conf
            pred["validation_reasons"] = reasons
            validated.append(pred)

        return validated
