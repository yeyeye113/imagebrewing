"""数据质量检查 — 缺失值、异常值、时间连续性。"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class QualityIssue:
    """单条质量问题。"""

    level: str  # "error" | "warning" | "info"
    category: str  # "missing" | "anomaly" | "gap" | "stale"
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.level == "error"


@dataclass
class QualityReport:
    """某只股票的数据质量报告。"""

    symbol: str
    rows: int = 0
    issues: list[QualityIssue] = field(default_factory=list)
    score: float = 100.0  # 0-100，100 = 完美

    @property
    def errors(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.level == "warning"]

    def summary(self) -> str:
        status = "PASS" if not self.errors else "FAIL"
        return (
            f"[{status}] {self.symbol}: score={self.score:.0f}/100, "
            f"rows={self.rows}, errors={len(self.errors)}, warnings={len(self.warnings)}"
        )


def check_quality(df: pd.DataFrame, symbol: str = "") -> QualityReport:
    """对 DataFrame 执行全面数据质量检查。

    检查项：
      1. 空数据集
      2. 缺失值（NaN）
      3. 零值 / 负值（价格不应为零或负）
      4. 成交量为零
      5. 价格跳变异常（单日涨跌 > 20%）
      6. 时间间隙（交易日缺失 > 3 天）
      7. 数据时效性（最新数据是否超过 5 天）
    """
    issues: list[QualityIssue] = []
    score = 100.0

    # 1. 空数据
    if df is None or df.empty:
        return QualityReport(
            symbol=symbol,
            rows=0,
            issues=[QualityIssue(level="error", category="missing", message="DataFrame is empty")],
            score=0,
        )

    rows = len(df)

    # 2. 缺失值
    if "close" in df.columns:
        nan_count = int(df["close"].isna().sum())
        if nan_count > 0:
            pct = nan_count / rows * 100
            level = "error" if pct > 5 else "warning"
            score -= min(pct * 2, 30)
            issues.append(
                QualityIssue(
                    level=level,
                    category="missing",
                    message=f"{nan_count} NaN in close ({pct:.1f}%)",
                    details={"count": nan_count, "pct": round(pct, 2)},
                )
            )

    # 3. 零值 / 负值
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            continue
        bad = int((df[col] <= 0).sum())
        if bad > 0:
            score -= min(bad * 5, 20)
            issues.append(
                QualityIssue(
                    level="error",
                    category="anomaly",
                    message=f"{bad} zero/negative values in {col}",
                    details={"col": col, "count": bad},
                )
            )

    # 4. 成交量为零
    if "volume" in df.columns:
        zero_vol = int((df["volume"] == 0).sum())
        if zero_vol > 0:
            pct = zero_vol / rows * 100
            score -= min(pct, 15)
            issues.append(
                QualityIssue(
                    level="warning",
                    category="anomaly",
                    message=f"{zero_vol} bars with zero volume ({pct:.1f}%)",
                    details={"count": zero_vol},
                )
            )

    # 5. 价格跳变（单日涨跌 > 20%）
    if "close" in df.columns and rows > 1:
        returns = df["close"].pct_change().abs()
        spikes = int((returns > 0.20).sum())
        if spikes > 0:
            score -= min(spikes * 10, 25)
            issues.append(
                QualityIssue(
                    level="warning",
                    category="anomaly",
                    message=f"{spikes} price spikes (> 20% daily move)",
                    details={"count": spikes},
                )
            )

    # 6. 时间间隙（超过 5 个自然日无数据）
    if hasattr(df.index, "to_pydatetime"):
        dates = pd.Series(df.index.to_pydatetime())
        if len(dates) > 1:
            gaps = dates.diff().dt.days
            # 超过 8 个自然日（跳过周末 + 假期，8 天合理阈值）
            big_gaps = int((gaps > 8).sum())
            if big_gaps > 0:
                score -= min(big_gaps * 5, 20)
                max_gap = int(gaps.max())
                issues.append(
                    QualityIssue(
                        level="warning",
                        category="gap",
                        message=f"{big_gaps} gaps > 8 calendar days (max: {max_gap}d)",
                        details={"gaps": big_gaps, "max_days": max_gap},
                    )
                )

    # 7. 数据时效性
    if hasattr(df.index, "to_pydatetime") and len(df) > 0:
        last_date = df.index[-1]
        if hasattr(last_date, "to_pydatetime"):
            last_dt = last_date.to_pydatetime()
        else:
            last_dt = pd.Timestamp(last_date).to_pydatetime()
        age_days = (_dt.datetime.now() - last_dt).days
        if age_days > 5:
            score -= min((age_days - 5) * 2, 15)
            issues.append(
                QualityIssue(
                    level="info",
                    category="stale",
                    message=f"Data is {age_days} days old (last: {last_dt.date()})",
                    details={"age_days": age_days, "last_date": str(last_dt.date())},
                )
            )

    score = max(0.0, min(100.0, score))
    return QualityReport(symbol=symbol, rows=rows, issues=issues, score=score)
