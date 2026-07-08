"""置信度校准器 — 基于历史准确率校准预测置信度。

功能:
  - 查询历史命中率
  - 校准置信度
  - 自动学习优化

用法:
    from quanttrader.confidence.calibrator import ConfidenceCalibrator
    calibrator = ConfidenceCalibrator()
    calibrated = calibrator.calibrate('RB', 'LONG', 0.75)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfidenceCalibrator:
    """置信度校准器。"""

    def __init__(self, tracker_path: str = "logs/tracker.json"):
        self.tracker_path = Path(tracker_path)
        self.history: dict[str, dict] = {}
        self._load_history()

    def _load_history(self):
        """加载历史数据。"""
        if not self.tracker_path.exists():
            return

        try:
            records = json.loads(self.tracker_path.read_text(encoding="utf-8"))
        except Exception:
            return

        # 统计每个品种+信号的历史准确率
        for rec in records:
            if not rec.get("verified") or rec.get("was_correct") is None:
                continue

            symbol = rec.get("symbol", "")
            signal = rec.get("signal", "")
            key = f"{symbol}_{signal}"

            if key not in self.history:
                self.history[key] = {"count": 0, "correct": 0, "accuracy": 0.5}

            self.history[key]["count"] += 1
            if rec["was_correct"]:
                self.history[key]["correct"] += 1

        # 计算准确率
        for key in self.history:
            h = self.history[key]
            if h["count"] > 0:
                h["accuracy"] = h["correct"] / h["count"]

    def calibrate(self, symbol: str, signal: str, raw_confidence: float) -> float:
        """校准置信度。

        Args:
            symbol: 品种代码
            signal: 信号类型 (LONG/SHORT/NEUTRAL)
            raw_confidence: 原始置信度

        Returns:
            校准后的置信度
        """
        key = f"{symbol}_{signal}"

        if key in self.history and self.history[key]["count"] >= 3:
            # 有足够样本，用历史准确率加权
            hist_acc = self.history[key]["accuracy"]
            count = self.history[key]["count"]

            # 样本越多，权重越高
            weight = min(0.6, count / 20)
            calibrated = raw_confidence * (1 - weight) + hist_acc * weight

            # 贵金属特殊处理
            if symbol in ("AU", "AG") and signal == "LONG":
                calibrated *= 0.6  # 贵金属做多降权

            return float(round(calibrated, 2))
        else:
            # 样本不足，轻度保守 (从0.7调整到0.85)
            return round(raw_confidence * 0.85, 2)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息。"""
        return {
            "total_keys": len(self.history),
            "total_records": sum(h["count"] for h in self.history.values()),
            "by_signal": {
                "LONG": self._get_signal_stats("LONG"),
                "SHORT": self._get_signal_stats("SHORT"),
                "NEUTRAL": self._get_signal_stats("NEUTRAL"),
            },
        }

    def _get_signal_stats(self, signal: str) -> dict:
        """获取某个信号的统计。"""
        count = 0
        correct = 0
        for key, h in self.history.items():
            if key.endswith(f"_{signal}"):
                count += h["count"]
                correct += h["correct"]
        return {
            "count": count,
            "correct": correct,
            "accuracy": correct / count if count > 0 else 0,
        }

    def get_recommendation(self, symbol: str, signal: str) -> str:
        """获取建议。"""
        key = f"{symbol}_{signal}"
        if key not in self.history:
            return "样本不足，建议观望"

        h = self.history[key]
        if h["count"] < 3:
            return "样本不足，建议观望"

        acc = h["accuracy"]
        if acc >= 0.7:
            return "历史表现良好，可操作"
        elif acc >= 0.5:
            return "历史表现一般，谨慎操作"
        else:
            return "历史表现差，建议观望"
