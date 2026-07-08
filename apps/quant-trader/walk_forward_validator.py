"""Walk-forward 验证器 — 滚动窗口 OOS 测试.

用正确的 out-of-sample 方法测量预测引擎的真实精度。
每个 fold 只用滚动窗口内的数据做预测，用窗口外的数据验证。

用法:
  from .walk_forward_validator import walk_forward_validate, WalkForwardConfig
  config = WalkForwardConfig(train_window=250, test_window=20)
  folds = walk_forward_validate(prices_map, config)
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .log import get_logger

logger = get_logger("walk_forward")


@dataclass
class WalkForwardConfig:
    """Walk-forward 配置."""
    train_window: int = 250      # 训练窗口 (交易日)
    test_window: int = 20        # 测试窗口 (每 fold 覆盖天数)
    step: int = 5                # 每隔几天做一次预测
    forward_days: int = 7        # 预测未来几天的方向
    min_confidence: float = 85.0 # 最低置信度
    min_agree_layers: int = 6    # 最少同方向层数


@dataclass
class FoldResult:
    """单个 fold 的结果."""
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    total_predictions: int = 0
    correct_predictions: int = 0
    precision: float = 0.0
    avg_confidence: float = 0.0
    bullish_count: int = 0
    bullish_correct: int = 0
    bearish_count: int = 0
    bearish_correct: int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class WalkForwardReport:
    """Walk-forward 总体报告."""
    total_folds: int = 0
    total_predictions: int = 0
    total_correct: int = 0
    overall_precision: float = 0.0
    precision_ci_lower: float = 0.0  # 95% CI 下限
    precision_ci_upper: float = 0.0  # 95% CI 上限
    avg_confidence: float = 0.0
    bullish_precision: float = 0.0
    bearish_precision: float = 0.0
    folds: list[FoldResult] = field(default_factory=list)
    config: WalkForwardConfig = field(default_factory=WalkForwardConfig)
    elapsed_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_folds": self.total_folds,
            "total_predictions": self.total_predictions,
            "total_correct": self.total_correct,
            "overall_precision": round(self.overall_precision, 4),
            "precision_ci_lower": round(self.precision_ci_lower, 4),
            "precision_ci_upper": round(self.precision_ci_upper, 4),
            "avg_confidence": round(self.avg_confidence, 1),
            "bullish_precision": round(self.bullish_precision, 4),
            "bearish_precision": round(self.bearish_precision, 4),
            "elapsed_s": round(self.elapsed_s, 2),
            "config": {
                "train_window": self.config.train_window,
                "test_window": self.config.test_window,
                "step": self.config.step,
                "forward_days": self.config.forward_days,
                "min_confidence": self.config.min_confidence,
                "min_agree_layers": self.config.min_agree_layers,
            },
        }


def _bootstrap_ci(correct: list[bool], n_bootstrap: int = 1000,
                  alpha: float = 0.05) -> tuple[float, float]:
    """Bootstrap 计算精度的置信区间."""
    if len(correct) < 5:
        return 0.0, 1.0

    arr = np.array(correct, dtype=float)
    n = len(arr)
    means = []

    rng = np.random.RandomState(42)
    for _ in range(n_bootstrap):
        sample = rng.choice(arr, size=n, replace=True)
        means.append(float(np.mean(sample)))

    means.sort()
    lower = means[int(alpha / 2 * n_bootstrap)]
    upper = means[int((1 - alpha / 2) * n_bootstrap)]
    return round(lower, 4), round(upper, 4)


def walk_forward_validate(
    prices_map: dict[str, pd.DataFrame],
    config: WalkForwardConfig | None = None,
    min_agree_layers: int | None = None,
) -> WalkForwardReport:
    """Walk-forward 验证: 滚动窗口 OOS 测试.

    Args:
        prices_map: {symbol: prices_df}
        config: 验证配置
        min_agree_layers: 最少同方向层数 (覆盖 config)

    Returns:
        WalkForwardReport
    """
    from .prediction_engine_v2 import predict_single

    if config is None:
        config = WalkForwardConfig()
    if min_agree_layers is not None:
        config.min_agree_layers = min_agree_layers

    t0 = _time.time()
    all_folds: list[FoldResult] = []
    all_correct: list[bool] = []
    all_confidences: list[float] = []
    bullish_correct: list[bool] = []
    bearish_correct: list[bool] = []

    fold_id = 0

    for symbol, prices in prices_map.items():
        n = len(prices)
        if n < config.train_window + config.test_window + config.forward_days:
            continue

        # 滚动窗口: 每 test_window 天一个 fold
        for fold_start in range(config.train_window,
                                n - config.forward_days - config.test_window,
                                config.test_window):
            fold_correct: list[bool] = []
            fold_confs: list[float] = []
            fold_bull: list[bool] = []
            fold_bear: list[bool] = []

            for i in range(fold_start, fold_start + config.test_window, config.step):
                if i + config.forward_days >= n:
                    break

                # 滚动窗口 (非累积)
                train_start = max(0, i - config.train_window)
                train_data = prices.iloc[train_start:i + 1].copy()

                if len(train_data) < 60:
                    continue

                try:
                    pred = predict_single(
                        train_data, symbol,
                        min_confidence=config.min_confidence,
                    )
                    if pred is None:
                        continue
                    if pred.layers_agree < config.min_agree_layers:
                        continue

                    # 验证: 用未来 forward_days 的实际收益
                    actual_return = float(
                        prices["close"].iloc[i + config.forward_days]
                        / prices["close"].iloc[i] - 1
                    )
                    actual_up = actual_return > 0
                    pred_up = pred.direction == 1
                    correct = pred_up == actual_up

                    fold_correct.append(correct)
                    fold_confs.append(pred.confidence)

                    if pred_up:
                        fold_bull.append(correct)
                    else:
                        fold_bear.append(correct)

                except Exception as e:
                    logger.debug("walk_forward 预测 %s @%d 异常: %s", symbol, i, e)

            # 记录 fold
            if fold_correct:
                ts_idx = prices.index[fold_start] if hasattr(prices.index[fold_start], 'strftime') else str(prices.index[fold_start])
                te_idx = prices.index[min(fold_start + config.test_window - 1, n - 1)]
                if hasattr(ts_idx, 'strftime'):
                    ts_str = ts_idx.strftime("%Y-%m-%d")
                    te_str = te_idx.strftime("%Y-%m-%d") if hasattr(te_idx, 'strftime') else str(te_idx)
                else:
                    ts_str = str(ts_idx)
                    te_str = str(te_idx)

                fold = FoldResult(
                    fold_id=fold_id,
                    train_start=str(prices.index[train_start])[:10],
                    train_end=str(prices.index[i])[:10],
                    test_start=ts_str,
                    test_end=te_str,
                    total_predictions=len(fold_correct),
                    correct_predictions=sum(fold_correct),
                    precision=sum(fold_correct) / len(fold_correct),
                    avg_confidence=float(np.mean(fold_confs)),
                    bullish_count=len(fold_bull),
                    bullish_correct=sum(fold_bull),
                    bearish_count=len(fold_bear),
                    bearish_correct=sum(fold_bear),
                )
                all_folds.append(fold)
                all_correct.extend(fold_correct)
                all_confidences.extend(fold_confs)
                bullish_correct.extend(fold_bull)
                bearish_correct.extend(fold_bear)
                fold_id += 1

    # 汇总
    total_pred = len(all_correct)
    total_correct = sum(all_correct)
    precision = total_correct / total_pred if total_pred > 0 else 0.0

    ci_lower, ci_upper = _bootstrap_ci(all_correct) if total_pred >= 5 else (0.0, 1.0)

    bull_prec = sum(bullish_correct) / len(bullish_correct) if bullish_correct else 0.0
    bear_prec = sum(bearish_correct) / len(bearish_correct) if bearish_correct else 0.0

    elapsed = _time.time() - t0

    return WalkForwardReport(
        total_folds=len(all_folds),
        total_predictions=total_pred,
        total_correct=total_correct,
        overall_precision=round(precision, 4),
        precision_ci_lower=ci_lower,
        precision_ci_upper=ci_upper,
        avg_confidence=round(float(np.mean(all_confidences)), 1) if all_confidences else 0.0,
        bullish_precision=round(bull_prec, 4),
        bearish_precision=round(bear_prec, 4),
        folds=all_folds,
        config=config,
        elapsed_s=round(elapsed, 2),
    )


def format_walk_forward_report(report: WalkForwardReport) -> str:
    """格式化 walk-forward 报告."""
    lines = [
        "=" * 60,
        "Walk-Forward OOS 精度验证报告",
        "=" * 60,
        "",
        f"配置: 训练窗口={report.config.train_window}天, "
        f"测试窗口={report.config.test_window}天, "
        f"前瞻={report.config.forward_days}天",
        f"最低置信度: {report.config.min_confidence:.0f}%",
        f"最少数层同意: {report.config.min_agree_layers}",
        "",
        "--- 总体结果 ---",
        f"总预测次数: {report.total_predictions}",
        f"正确预测: {report.total_correct}",
        f"OOS 精度: {report.overall_precision*100:.1f}%",
        f"95% 置信区间: [{report.precision_ci_lower*100:.1f}%, {report.precision_ci_upper*100:.1f}%]",
        f"平均置信度: {report.avg_confidence:.1f}%",
        "",
        "--- 分方向 ---",
        f"看多精度: {report.bullish_precision*100:.1f}%",
        f"看空精度: {report.bearish_precision*100:.1f}%",
        "",
    ]

    # Fold 明细
    if report.folds:
        lines.append("--- Fold 明细 ---")
        lines.append(f"{'Fold':<5} {'样本':<6} {'正确':<6} {'精度':<8} {'置信度':<8}")
        lines.append("-" * 40)
        for f in report.folds:
            lines.append(
                f"{f.fold_id:<5} {f.total_predictions:<6} "
                f"{f.correct_predictions:<6} "
                f"{f.precision*100:>5.1f}%  "
                f"{f.avg_confidence:>5.1f}%"
            )
        lines.append("")

    # 达标判断
    if report.overall_precision >= 0.90:
        lines.append("✅ OOS 精度达标 (≥ 90%)")
    elif report.overall_precision >= 0.80:
        lines.append("⚠️ OOS 精度接近目标 (≥ 80%, 目标 90%)")
    else:
        lines.append(f"❌ OOS 精度未达标 ({report.overall_precision*100:.1f}%, 目标 90%)")

    if report.precision_ci_lower >= 0.85:
        lines.append("✅ 95% CI 下限达标 (≥ 85%)")

    lines.append(f"\n耗时: {report.elapsed_s:.1f}s")
    lines.append("=" * 60)
    return "\n".join(lines)
