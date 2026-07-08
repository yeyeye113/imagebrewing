"""每日样本收集器 — 自动收集和验证预测样本。

功能:
  - 运行全量预测
  - 记录到tracker
  - 验证昨日预测
  - 输出报告

用法:
    python -m quanttrader.collector.daily_collector
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from quanttrader.confidence.calibrator import ConfidenceCalibrator
from quanttrader.validation.signal_validator import SignalValidator

log = logging.getLogger("quanttrader.collector")


class DailyCollector:
    """每日样本收集器。"""

    def __init__(self, tracker_path: str = "logs/tracker.json"):
        self.tracker_path = Path(tracker_path)
        self.calibrator = ConfidenceCalibrator(tracker_path)
        self.validator = SignalValidator()

    def run(self):
        """运行每日收集。"""
        log.info("=" * 60)
        log.info("每日样本收集开始")
        log.info("=" * 60)

        # 1. 验证昨日预测
        verified = self._verify_yesterday()
        log.info(f"验证昨日预测: {verified} 条")

        # 2. 运行全量预测
        predictions = self._run_predictions()
        log.info(f"运行预测: {len(predictions)} 条")

        # 3. 校准置信度
        calibrated = self._calibrate_confidence(predictions)
        log.info(f"校准置信度: {len(calibrated)} 条")

        # 4. 验证信号
        validated = self._validate_signals(calibrated)
        log.info(f"验证信号: {len(validated)} 条")

        # 5. 记录到tracker
        recorded = self._record_predictions(validated)
        log.info(f"记录预测: {recorded} 条")

        # 6. 输出报告
        report = self._generate_report()
        log.info("报告生成完成")

        return report

    def _verify_yesterday(self) -> int:
        """验证昨日预测。"""
        try:
            from quanttrader.tracker import verify_predictions

            yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
            results = verify_predictions(yesterday)
            return len([r for r in results if r.get("verified")])
        except Exception as e:
            log.warning(f"验证失败: {e}")
            return 0

    def _run_predictions(self) -> list[dict]:
        """运行全量预测。"""
        try:
            from quanttrader.forecast import run_forecast

            categories = {
                "热门期货": ["I", "RB", "SC", "AU", "AG"],
                "金属板块": ["RB", "I", "HC", "CU", "AL", "ZN"],
                "能源化工": ["SC", "FU", "TA", "MA", "SA"],
                "农产品": ["M", "P", "Y", "A", "RM"],
                "金融期货": ["IF", "IC", "IH", "IM"],
            }

            all_results = []
            for cat, codes in categories.items():
                try:
                    results = run_forecast(futures=codes)
                    all_results.extend(results)
                except Exception as e:
                    log.warning(f"{cat} 预测失败: {e}")

            return [
                {
                    "symbol": r.symbol,
                    "signal": r.signal,
                    "confidence": r.confidence,
                    "forecast_price": r.forecast_price or r.high_point,
                    "reason": r.reason,
                }
                for r in all_results
            ]
        except Exception as e:
            log.error(f"预测失败: {e}")
            return []

    def _calibrate_confidence(self, predictions: list[dict]) -> list[dict]:
        """校准置信度。"""
        calibrated = []
        for pred in predictions:
            symbol = pred.get("symbol", "")
            signal = pred.get("signal", "NEUTRAL")
            raw_conf = pred.get("confidence", 0)

            # 校准
            new_conf = self.calibrator.calibrate(symbol, signal, raw_conf)
            pred["confidence"] = new_conf
            pred["raw_confidence"] = raw_conf

            calibrated.append(pred)
        return calibrated

    def _validate_signals(self, predictions: list[dict]) -> list[dict]:
        """验证信号。"""
        return self.validator.batch_validate(predictions, {})

    def _record_predictions(self, predictions: list[dict]) -> int:
        """记录预测到tracker。"""
        try:
            from quanttrader.tracker import record_prediction

            recorded = 0
            for pred in predictions:
                try:
                    record_prediction(
                        symbol=pred["symbol"],
                        market="future",
                        signal=pred["signal"],
                        confidence=pred["confidence"],
                        forecast_price=pred["forecast_price"],
                        llm_reason=pred.get("reason", ""),
                    )
                    recorded += 1
                except Exception:
                    pass
            return recorded
        except Exception as e:
            log.error(f"记录失败: {e}")
            return 0

    def _generate_report(self) -> dict:
        """生成报告。"""
        try:
            records = json.loads(self.tracker_path.read_text(encoding="utf-8"))
            verified = [r for r in records if r.get("verified")]
            correct = sum(1 for r in verified if r.get("was_correct"))

            by_signal: dict[str, dict] = {}
            report = {
                "date": dt.date.today().isoformat(),
                "total_records": len(records),
                "verified_records": len(verified),
                "correct_records": correct,
                "accuracy": correct / len(verified) if verified else 0,
                "by_signal": by_signal,
                "calibrator_stats": self.calibrator.get_stats(),
            }

            # 按信号统计
            for sig in ["LONG", "SHORT", "NEUTRAL"]:
                sig_recs = [r for r in verified if r.get("signal") == sig]
                if sig_recs:
                    sig_correct = sum(1 for r in sig_recs if r.get("was_correct"))
                    by_signal[sig] = {
                        "count": len(sig_recs),
                        "correct": sig_correct,
                        "accuracy": sig_correct / len(sig_recs),
                    }

            return report
        except Exception as e:
            log.error(f"报告生成失败: {e}")
            return {"error": str(e)}


def main():
    """主入口。"""
    logging.basicConfig(level=logging.INFO)
    collector = DailyCollector()
    report = collector.run()

    print("=" * 60)
    print("每日样本收集报告")
    print("=" * 60)
    print(f"日期: {report.get('date')}")
    print(f"总记录: {report.get('total_records')}")
    print(f"已验证: {report.get('verified_records')}")
    print(f"正确: {report.get('correct_records')}")
    print(f"准确率: {report.get('accuracy', 0) * 100:.1f}%")
    print()
    print("按信号:")
    for sig, data in report.get("by_signal", {}).items():
        print(f"  {sig}: {data['correct']}/{data['count']} = {data['accuracy'] * 100:.0f}%")


if __name__ == "__main__":
    main()
