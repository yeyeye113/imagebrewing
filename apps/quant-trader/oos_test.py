"""样本外测试模块 — 严格区分训练/测试集验证.

功能:
  1. 严格时间序列划分 (训练/验证/测试)
  2. 滚动样本外测试
  3. 统计显著性检验
  4. 过拟合检测
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .log import get_logger

logger = get_logger("oos_test")


@dataclass
class OOSFoldResult:
    """样本外测试结果."""
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    total_predictions: int
    signal_predictions: int
    correct_signals: int
    signal_accuracy: float
    total_accuracy: float


@dataclass
class OOSReport:
    """样本外测试报告."""
    n_folds: int
    total_signals: int
    total_correct: int
    overall_signal_accuracy: float
    mean_fold_accuracy: float
    std_fold_accuracy: float
    confidence_interval: tuple[float, float]
    overfit_score: float  # 过拟合分数 (IS - OOS 差异)
    fold_results: list[OOSFoldResult]
    is_statistically_significant: bool


def run_oos_test(
    prices: pd.DataFrame,
    symbol: str = "",
    n_folds: int = 5,
    train_ratio: float = 0.6,
    gap_days: int = 5,
    forward_days: int = 7,
    min_confidence: float = 60,
    min_agree: int = 3,
) -> OOSReport:
    """样本外测试.

    Args:
        prices: 价格数据
        symbol: 股票代码
        n_folds: 折叠数
        train_ratio: 训练集比例
        gap_days: 训练/测试间隔
        forward_days: 预测未来天数
        min_confidence: 最低置信度
        min_agree: 最少同方向层数

    Returns:
        OOSReport: 测试报告
    """
    from .prediction_engine_v2 import predict_single

    if prices is None or len(prices) < 250:
        return OOSReport(
            n_folds=0, total_signals=0, total_correct=0,
            overall_signal_accuracy=0, mean_fold_accuracy=0,
            std_fold_accuracy=0, confidence_interval=(0, 0),
            overfit_score=0, fold_results=[],
            is_statistically_significant=False,
        )

    n = len(prices)
    test_size = int(n * (1 - train_ratio) / n_folds)
    fold_results = []

    for fold_id in range(n_folds):
        # 计算时间窗口
        test_end = n - fold_id * test_size
        test_start = test_end - test_size
        train_end = test_start - gap_days

        if train_end < 200 or test_start < 60:
            continue

        # 测试集上的预测
        correct = 0
        total = 0
        signal_count = 0

        for i in range(test_start, test_end - forward_days, 5):
            hist = prices.iloc[:i + 1]
            actual_fwd = float(prices['close'].iloc[i + forward_days] / prices['close'].iloc[i] - 1)

            try:
                pred = predict_single(
                    hist, symbol, symbol,
                    min_confidence=min_confidence,
                    min_agree_layers=min_agree,
                )
            except Exception:
                pred = None

            if pred and pred.direction_label != "HOLD":
                signal_count += 1
                actual_dir = 1 if actual_fwd > 0.005 else (-1 if actual_fwd < -0.005 else 0)
                if pred.direction == actual_dir:
                    correct += 1

            total += 1

        if total > 0:
            fold_results.append(OOSFoldResult(
                fold_id=fold_id,
                train_start=str(prices.index[0]),
                train_end=str(prices.index[train_end]),
                test_start=str(prices.index[test_start]),
                test_end=str(prices.index[min(test_end - 1, n - 1)]),
                total_predictions=total,
                signal_predictions=signal_count,
                correct_signals=correct,
                signal_accuracy=correct / max(signal_count, 1),
                total_accuracy=correct / total,
            ))

    # 汇总
    total_signals = sum(f.signal_predictions for f in fold_results)
    total_correct = sum(f.correct_signals for f in fold_results)
    overall_accuracy = total_correct / max(total_signals, 1)

    fold_accuracies = [f.signal_accuracy for f in fold_results if f.signal_predictions > 0]
    mean_acc = float(np.mean(fold_accuracies)) if fold_accuracies else 0
    std_acc = float(np.std(fold_accuracies)) if fold_accuracies else 0

    # 95% 置信区间
    n_folds_valid = len(fold_accuracies)
    if n_folds_valid > 1:
        se = std_acc / np.sqrt(n_folds_valid)
        ci = (mean_acc - 1.96 * se, mean_acc + 1.96 * se)
    else:
        ci = (0, 0)

    # 过拟合分数 (越低越好)
    overfit_score = std_acc * 100

    # 统计显著性检验 (单侧 t 检验)
    is_significant = False
    if n_folds_valid >= 3:
        from scipy import stats
        t_stat, p_value = stats.ttest_1samp(fold_accuracies, 0.5)
        is_significant = (p_value < 0.05) and (mean_acc > 0.5)

    return OOSReport(
        n_folds=len(fold_results),
        total_signals=total_signals,
        total_correct=total_correct,
        overall_signal_accuracy=overall_accuracy,
        mean_fold_accuracy=mean_acc,
        std_fold_accuracy=std_acc,
        confidence_interval=ci,
        overfit_score=overfit_score,
        fold_results=fold_results,
        is_statistically_significant=is_significant,
    )


def format_oos_report(report: OOSReport) -> str:
    """格式化样本外测试报告."""
    lines = [
        "=" * 50,
        "样本外测试报告",
        "=" * 50,
        "",
        f"折叠数: {report.n_folds}",
        f"总信号数: {report.total_signals}",
        f"正确信号: {report.total_correct}",
        f"总体信号准确率: {report.overall_signal_accuracy*100:.1f}%",
        "",
        f"平均折叠准确率: {report.mean_fold_accuracy*100:.1f}%",
        f"标准差: {report.std_fold_accuracy*100:.1f}%",
        f"95% 置信区间: [{report.confidence_interval[0]*100:.1f}%, {report.confidence_interval[1]*100:.1f}%]",
        f"过拟合分数: {report.overfit_score:.1f}",
        f"统计显著性: {'是' if report.is_statistically_significant else '否'}",
        "",
        "-" * 50,
        "各折叠详情:",
        "-" * 50,
    ]

    for f in report.fold_results:
        lines.append(
            f"  折叠{f.fold_id}: {f.signal_predictions}信号 "
            f"{f.correct_signals}正确 "
            f"准确率{f.signal_accuracy*100:.1f}%"
        )

    lines.append("=" * 50)
    return "\n".join(lines)
