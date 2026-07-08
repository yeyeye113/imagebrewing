"""分析日志系统 — 可迭代记录每次分析, 支持复盘和回测.

核心功能:
  - 记录每次分析的完整数据
  - 支持按标的/时间/信号查询
  - 计算预测准确率
  - 生成复盘报告
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════
# 日志数据结构
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class AnalysisRecord:
    """单次分析记录 (增强版)."""
    id: str                      # 唯一ID: {symbol}_{timestamp}
    timestamp: str               # ISO格式时间
    symbol: str
    name: str
    kind: str                    # "stock" | "future"
    price_at_analysis: float     # 分析时价格
    # 分析结果
    composite_score: float
    grade: str
    signal: str
    action: str                  # 建议操作
    time_horizon: str            # 时间维度
    confidence: float
    # 关键指标
    tech_score: float = 0
    momentum_score: float = 0
    volume_score: float = 0
    risk_score: float = 0
    # 建议详情
    entry_price: float = 0
    stop_loss: float = 0
    take_profit: float = 0
    position_pct: str = ""
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    # 进出场建议
    entry_timing: str = ""
    exit_timing: str = ""
    best_entry_window: str = ""
    holding_period: str = ""
    # 预测数据
    target_1d: float | None = None
    target_3d: float | None = None
    target_7d: float | None = None
    target_30d: float | None = None
    expected_return_1d: float | None = None
    expected_return_3d: float | None = None
    expected_return_7d: float | None = None
    expected_return_30d: float | None = None
    prob_up_1d: float | None = None
    prob_up_3d: float | None = None
    prob_up_7d: float | None = None
    prob_up_30d: float | None = None
    # 后验数据 (事后填入)
    price_after_1d: float | None = None
    price_after_3d: float | None = None
    price_after_7d: float | None = None
    price_after_30d: float | None = None
    actual_return_1d: float | None = None
    actual_return_3d: float | None = None
    actual_return_7d: float | None = None
    actual_return_30d: float | None = None
    # 预测准确
    direction_correct_1d: bool | None = None
    direction_correct_3d: bool | None = None
    direction_correct_7d: bool | None = None
    direction_correct_30d: bool | None = None
    # 预测偏差
    deviation_1d: float | None = None   # 实际vs预测偏差
    deviation_3d: float | None = None
    deviation_7d: float | None = None
    deviation_30d: float | None = None
    # 验证状态
    verified_1d: bool = False
    verified_3d: bool = False
    verified_7d: bool = False
    verified_30d: bool = False
    # 原始数据
    factors: dict = field(default_factory=dict)
    indicators: dict = field(default_factory=dict)
    volume_info: dict = field(default_factory=dict)
    report_text: str = ""        # 完整报告文本

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JournalStats:
    """日志统计 (增强版)."""
    total_analyses: int = 0
    unique_symbols: int = 0
    date_range: str = ""
    # 信号分布
    buy_count: int = 0
    hold_count: int = 0
    sell_count: int = 0
    watch_count: int = 0
    # 评分分布
    avg_score: float = 0
    grade_distribution: dict = field(default_factory=dict)
    # 准确率 (有后验数据的)
    accuracy_1d: float | None = None
    accuracy_3d: float | None = None
    accuracy_7d: float | None = None
    accuracy_30d: float | None = None
    total_with_outcome: int = 0
    # 收益统计
    avg_return_1d: float | None = None
    avg_return_3d: float | None = None
    avg_return_7d: float | None = None
    avg_return_30d: float | None = None
    win_rate: float | None = None
    # 按评分区间统计
    accuracy_by_score: dict = field(default_factory=dict)  # {"high": 0.65, "mid": 0.52, "low": 0.45}
    return_by_score: dict = field(default_factory=dict)     # {"high": 0.03, "mid": 0.01, "low": -0.02}
    # 预测偏差统计
    avg_deviation_1d: float | None = None
    avg_deviation_7d: float | None = None
    deviation_std_1d: float | None = None
    deviation_std_7d: float | None = None
    # 调整建议
    adjustment_notes: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# 日志管理器
# ═══════════════════════════════════════════════════════════════════════

class AnalysisJournal:
    """分析日志管理器.

    用法:
        journal = AnalysisJournal("data/analysis_journal.jsonl")
        journal.add(record)
        records = journal.query(symbol="600519", days=30)
        stats = journal.stats()
    """

    def __init__(self, path: str = "data/analysis_journal.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[AnalysisRecord] = []
        self._load()

    def _load(self):
        """从文件加载历史记录."""
        if not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        self._records.append(AnalysisRecord(**data))
                    except Exception:
                        continue
        except Exception:
            pass

    def _save(self):
        """保存记录到文件."""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                for record in self._records:
                    f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def add(self, record: AnalysisRecord):
        """添加分析记录."""
        # 检查是否已存在 (同标的同时间)
        existing_idx = None
        for i, r in enumerate(self._records):
            if r.id == record.id:
                existing_idx = i
                break

        if existing_idx is not None:
            self._records[existing_idx] = record
        else:
            self._records.append(record)

        self._save()

    def query(
        self,
        symbol: str | None = None,
        kind: str | None = None,
        signal: str | None = None,
        days: int | None = None,
        min_score: float | None = None,
        limit: int = 100,
    ) -> list[AnalysisRecord]:
        """查询分析记录."""
        results = self._records

        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if kind:
            results = [r for r in results if r.kind == kind]
        if signal:
            results = [r for r in results if r.signal == signal]
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            results = [r for r in results if r.timestamp >= cutoff]
        if min_score is not None:
            results = [r for r in results if r.composite_score >= min_score]

        # 按时间倒序
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:limit]

    def get_latest(self, symbol: str) -> AnalysisRecord | None:
        """获取某标的最新分析."""
        records = self.query(symbol=symbol, limit=1)
        return records[0] if records else None

    def update_outcome(
        self,
        record_id: str,
        price_1d: float | None = None,
        price_3d: float | None = None,
        price_7d: float | None = None,
        price_30d: float | None = None,
    ):
        """更新后验数据 (实际价格) 并计算偏差."""
        for record in self._records:
            if record.id == record_id:
                base = record.price_at_analysis

                def _update_period(price, target, expected_return, prob, period):
                    """更新单个周期的数据."""
                    if price is None:
                        return
                    actual_return = (price - base) / base
                    setattr(record, f"price_after_{period}", price)
                    setattr(record, f"actual_return_{period}", actual_return)
                    setattr(record, f"verified_{period}", True)

                    # 方向判断
                    direction_correct = (
                        (record.signal in ("强烈看多", "偏多") and price > base) or
                        (record.signal in ("强烈看空", "偏空") and price < base) or
                        (record.signal == "中性")
                    )
                    setattr(record, f"direction_correct_{period}", direction_correct)

                    # 预测偏差 (实际收益 vs 预测收益)
                    if expected_return is not None:
                        deviation = actual_return - expected_return
                        setattr(record, f"deviation_{period}", deviation)

                _update_period(price_1d, record.target_1d, record.expected_return_1d, record.prob_up_1d, "1d")
                _update_period(price_3d, record.target_3d, record.expected_return_3d, record.prob_up_3d, "3d")
                _update_period(price_7d, record.target_7d, record.expected_return_7d, record.prob_up_7d, "7d")
                _update_period(price_30d, record.target_30d, record.expected_return_30d, record.prob_up_30d, "30d")

                self._save()
                return
        raise KeyError(f"Record {record_id} not found")

    def stats(self, days: int | None = None) -> JournalStats:
        """生成日志统计 (增强版)."""
        records = self.query(days=days, limit=10000)

        if not records:
            return JournalStats()

        # 信号分布
        buy_count = sum(1 for r in records if r.action in ("买入", "加仓"))
        hold_count = sum(1 for r in records if r.action == "持有")
        sell_count = sum(1 for r in records if r.action in ("卖出", "减仓"))
        watch_count = sum(1 for r in records if r.action in ("观望", "回避"))

        # 评分分布
        scores = [r.composite_score for r in records]
        grades: dict[str, int] = {}
        for r in records:
            grades[r.grade] = grades.get(r.grade, 0) + 1

        # 准确率
        with_1d = [r for r in records if r.direction_correct_1d is not None]
        with_3d = [r for r in records if r.direction_correct_3d is not None]
        with_7d = [r for r in records if r.direction_correct_7d is not None]
        with_30d = [r for r in records if r.direction_correct_30d is not None]

        accuracy_1d = sum(1 for r in with_1d if r.direction_correct_1d) / len(with_1d) if with_1d else None
        accuracy_3d = sum(1 for r in with_3d if r.direction_correct_3d) / len(with_3d) if with_3d else None
        accuracy_7d = sum(1 for r in with_7d if r.direction_correct_7d) / len(with_7d) if with_7d else None
        accuracy_30d = sum(1 for r in with_30d if r.direction_correct_30d) / len(with_30d) if with_30d else None

        # 收益
        returns_1d = [r.actual_return_1d for r in records if r.actual_return_1d is not None]
        returns_3d = [r.actual_return_3d for r in records if r.actual_return_3d is not None]
        returns_7d = [r.actual_return_7d for r in records if r.actual_return_7d is not None]
        returns_30d = [r.actual_return_30d for r in records if r.actual_return_30d is not None]

        win_count = sum(1 for r in returns_1d if r > 0) if returns_1d else 0

        # 按评分区间统计准确率
        high_score = [r for r in with_7d if r.composite_score >= 70]
        mid_score = [r for r in with_7d if 50 <= r.composite_score < 70]
        low_score = [r for r in with_7d if r.composite_score < 50]

        accuracy_by_score = {}
        return_by_score = {}
        if high_score:
            accuracy_by_score["high"] = sum(1 for r in high_score if r.direction_correct_7d) / len(high_score)
            high_returns = [r.actual_return_7d for r in high_score if r.actual_return_7d is not None]
            return_by_score["high"] = sum(high_returns) / len(high_returns) if high_returns else 0
        if mid_score:
            accuracy_by_score["mid"] = sum(1 for r in mid_score if r.direction_correct_7d) / len(mid_score)
            mid_returns = [r.actual_return_7d for r in mid_score if r.actual_return_7d is not None]
            return_by_score["mid"] = sum(mid_returns) / len(mid_returns) if mid_returns else 0
        if low_score:
            accuracy_by_score["low"] = sum(1 for r in low_score if r.direction_correct_7d) / len(low_score)
            low_returns = [r.actual_return_7d for r in low_score if r.actual_return_7d is not None]
            return_by_score["low"] = sum(low_returns) / len(low_returns) if low_returns else 0

        # 预测偏差统计
        deviations_1d = [r.deviation_1d for r in records if r.deviation_1d is not None]
        deviations_7d = [r.deviation_7d for r in records if r.deviation_7d is not None]

        avg_dev_1d = sum(deviations_1d) / len(deviations_1d) if deviations_1d else None
        avg_dev_7d = sum(deviations_7d) / len(deviations_7d) if deviations_7d else None
        std_dev_1d = (sum((d - avg_dev_1d)**2 for d in deviations_1d) / len(deviations_1d)) ** 0.5 if deviations_1d and avg_dev_1d else None
        std_dev_7d = (sum((d - avg_dev_7d)**2 for d in deviations_7d) / len(deviations_7d)) ** 0.5 if deviations_7d and avg_dev_7d else None

        # 计算胜率
        win_rate = win_count / len(returns_1d) if returns_1d else None

        # 生成调整建议
        adjustment_notes = []
        if accuracy_7d is not None and accuracy_7d < 0.50:
            adjustment_notes.append("7日方向准确率低于50%, 建议提高筛选门槛")
        if accuracy_by_score.get("high", 0) < accuracy_by_score.get("mid", 0):
            adjustment_notes.append("高评分标的准确率反而低于中评分, 评分模型需调整")
        if avg_dev_1d is not None and abs(avg_dev_1d) > 0.02:
            adjustment_notes.append(f"1日预测偏差{avg_dev_1d*100:+.1f}%, 预测过于{'乐观' if avg_dev_1d > 0 else '悲观'}")
        if win_rate and win_rate < 0.45:
            adjustment_notes.append("胜率低于45%, 建议收紧入场条件")

        # 唯一标的
        unique_symbols = len(set(r.symbol for r in records))

        # 日期范围
        dates = sorted(set(r.timestamp[:10] for r in records))
        date_range = f"{dates[0]} ~ {dates[-1]}" if dates else ""

        return JournalStats(
            total_analyses=len(records),
            unique_symbols=unique_symbols,
            date_range=date_range,
            buy_count=buy_count,
            hold_count=hold_count,
            sell_count=sell_count,
            watch_count=watch_count,
            avg_score=sum(scores) / len(scores) if scores else 0,
            grade_distribution=grades,
            accuracy_1d=accuracy_1d,
            accuracy_3d=accuracy_3d,
            accuracy_7d=accuracy_7d,
            accuracy_30d=accuracy_30d,
            total_with_outcome=len(with_1d),
            avg_return_1d=sum(returns_1d) / len(returns_1d) if returns_1d else None,
            avg_return_3d=sum(returns_3d) / len(returns_3d) if returns_3d else None,
            avg_return_7d=sum(returns_7d) / len(returns_7d) if returns_7d else None,
            avg_return_30d=sum(returns_30d) / len(returns_30d) if returns_30d else None,
            win_rate=win_count / len(returns_1d) if returns_1d else None,
            accuracy_by_score=accuracy_by_score,
            return_by_score=return_by_score,
            avg_deviation_1d=avg_dev_1d,
            avg_deviation_7d=avg_dev_7d,
            deviation_std_1d=std_dev_1d,
            deviation_std_7d=std_dev_7d,
            adjustment_notes=adjustment_notes,
        )

    def review(
        self,
        symbol: str | None = None,
        days: int = 30,
    ) -> list[dict]:
        """生成复盘报告."""
        records = self.query(symbol=symbol, days=days)
        reviews = []

        for r in records:
            review = {
                "id": r.id,
                "date": r.timestamp[:10],
                "symbol": r.symbol,
                "name": r.name,
                "price_then": r.price_at_analysis,
                "signal": r.signal,
                "action": r.action,
                "score": r.composite_score,
                "grade": r.grade,
                "reasons": r.reasons,
            }

            # 后验收益
            if r.actual_return_1d is not None:
                review["return_1d"] = f"{r.actual_return_1d*100:+.2f}%"
                review["correct_1d"] = r.direction_correct_1d
            if r.actual_return_7d is not None:
                review["return_7d"] = f"{r.actual_return_7d*100:+.2f}%"
                review["correct_7d"] = r.direction_correct_7d

            reviews.append(review)

        return reviews

    def top_performers(self, days: int = 30, min_analyses: int = 3) -> list[dict]:
        """表现最好的标的."""
        records = self.query(days=days, limit=10000)

        # 按标的分组
        by_symbol: dict[str, list[AnalysisRecord]] = {}
        for r in records:
            if r.actual_return_7d is not None:
                by_symbol.setdefault(r.symbol, []).append(r)

        results: list[dict[str, Any]] = []
        for symbol, recs in by_symbol.items():
            if len(recs) < min_analyses:
                continue
            # by_symbol 只收录 actual_return_7d 非 None 的记录, or 0.0 仅为类型收窄
            avg_return = sum(r.actual_return_7d or 0.0 for r in recs) / len(recs)
            accuracy = sum(1 for r in recs if r.direction_correct_7d) / len(recs)
            results.append({
                "symbol": symbol,
                "name": recs[0].name,
                "analyses": len(recs),
                "avg_return_7d": round(avg_return * 100, 2),
                "accuracy_7d": round(accuracy * 100, 1),
                "avg_score": round(sum(r.composite_score for r in recs) / len(recs), 1),
            })

        results.sort(key=lambda x: x["avg_return_7d"], reverse=True)
        return results


# ═══════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════

def create_record_from_analysis(
    symbol: str,
    name: str,
    kind: str,
    price: float,
    analysis_result: dict,
    advice_report: dict,
) -> AnalysisRecord:
    """从分析结果创建日志记录."""
    now = datetime.now()
    record_id = f"{symbol}_{now.strftime('%Y%m%d_%H%M%S')}"

    return AnalysisRecord(
        id=record_id,
        timestamp=now.isoformat(),
        symbol=symbol,
        name=name,
        kind=kind,
        price_at_analysis=price,
        composite_score=advice_report.get("overall_score", 50),
        grade=advice_report.get("overall_grade", "C"),
        signal=advice_report.get("overall_signal", "中性"),
        action=advice_report.get("advice_medium", {}).get("action", "观望"),
        time_horizon="中线",
        confidence=advice_report.get("advice_medium", {}).get("confidence", 0.5),
        tech_score=advice_report.get("tech_score", 50),
        momentum_score=advice_report.get("momentum_score", 50),
        volume_score=advice_report.get("volume_score", 50),
        risk_score=advice_report.get("risk_score", 50),
        entry_price=advice_report.get("advice_medium", {}).get("entry_price", price),
        stop_loss=advice_report.get("advice_medium", {}).get("stop_loss", price * 0.95),
        take_profit=advice_report.get("advice_medium", {}).get("take_profit", price * 1.10),
        position_pct=advice_report.get("advice_medium", {}).get("position_pct", "10%"),
        reasons=advice_report.get("advice_medium", {}).get("reasons", []),
        risks=advice_report.get("advice_medium", {}).get("risks", []),
        factors=advice_report.get("key_metrics", {}),
        indicators=analysis_result.get("indicators", {}),
        volume_info=analysis_result.get("volume_info", {}),
    )


def format_stats_text(stats: JournalStats) -> str:
    """格式化统计文本 (增强版)."""
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║  分析日志统计",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        f"📊 总分析次数: {stats.total_analyses}",
        f"📊 覆盖标的: {stats.unique_symbols} 只",
        f"📊 日期范围: {stats.date_range}",
        "",
        "┌─ 信号分布 ─────────────────────────────────────────────────┐",
        f"│ 买入/加仓: {stats.buy_count}  持有: {stats.hold_count}  卖出/减仓: {stats.sell_count}  观望/回避: {stats.watch_count}",
        "└──────────────────────────────────────────────────────────┘",
        "",
        f"📊 平均评分: {stats.avg_score:.1f}/100",
    ]

    if stats.accuracy_1d is not None:
        lines.extend([
            "",
            "┌─ 预测准确率 ───────────────────────────────────────────────┐",
            f"│ 1日方向准确率: {stats.accuracy_1d*100:.1f}%",
            f"│ 3日方向准确率: {stats.accuracy_3d*100:.1f}%" if stats.accuracy_3d else "",
            f"│ 7日方向准确率: {stats.accuracy_7d*100:.1f}%" if stats.accuracy_7d else "",
            f"│ 30日方向准确率: {stats.accuracy_30d*100:.1f}%" if stats.accuracy_30d else "",
            f"│ 胜率: {stats.win_rate*100:.1f}%" if stats.win_rate else "",
            "└──────────────────────────────────────────────────────────┘",
        ])

    if stats.avg_return_1d is not None:
        lines.extend([
            "",
            "┌─ 平均收益 ─────────────────────────────────────────────────┐",
            f"│ 1日: {stats.avg_return_1d*100:+.2f}%",
            f"│ 3日: {stats.avg_return_3d*100:+.2f}%" if stats.avg_return_3d else "",
            f"│ 7日: {stats.avg_return_7d*100:+.2f}%" if stats.avg_return_7d else "",
            f"│ 30日: {stats.avg_return_30d*100:+.2f}%" if stats.avg_return_30d else "",
            "└──────────────────────────────────────────────────────────┘",
        ])

    if stats.accuracy_by_score:
        lines.extend([
            "",
            "┌─ 按评分区间统计 ───────────────────────────────────────────┐",
            f"│ 高评分(≥70): 准确率{stats.accuracy_by_score.get('high', 0)*100:.1f}%  平均收益{stats.return_by_score.get('high', 0)*100:+.2f}%",
            f"│ 中评分(50-70): 准确率{stats.accuracy_by_score.get('mid', 0)*100:.1f}%  平均收益{stats.return_by_score.get('mid', 0)*100:+.2f}%",
            f"│ 低评分(<50): 准确率{stats.accuracy_by_score.get('low', 0)*100:.1f}%  平均收益{stats.return_by_score.get('low', 0)*100:+.2f}%",
            "└──────────────────────────────────────────────────────────┘",
        ])

    if stats.avg_deviation_1d is not None:
        dev_lines = [
            "",
            "┌─ 预测偏差 ─────────────────────────────────────────────────┐",
        ]
        if stats.deviation_std_1d:
            dev_lines.append(f"│ 1日平均偏差: {stats.avg_deviation_1d*100:+.2f}% (标准差{stats.deviation_std_1d*100:.2f}%)")
        if stats.deviation_std_7d and stats.avg_deviation_7d is not None:
            dev_lines.append(f"│ 7日平均偏差: {stats.avg_deviation_7d*100:+.2f}% (标准差{stats.deviation_std_7d*100:.2f}%)")
        dev_lines.append("└──────────────────────────────────────────────────────────┘")
        lines.extend(dev_lines)

    if stats.adjustment_notes:
        lines.extend([
            "",
            "┌─ 调整建议 ─────────────────────────────────────────────────┐",
            *[f"│ ⚠️ {note}" for note in stats.adjustment_notes],
            "└──────────────────────────────────────────────────────────┘",
        ])

    return "\n".join(lines)
