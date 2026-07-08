"""实盘模拟对比系统 — 记录交易决策、回测vs模拟收益对比、归因分析。"""

from .analyzer import ComparisonAnalyzer, ComparisonResult, TradeComparison
from .attribution import AttributionAnalyzer, AttributionEntry
from .recorder import SimulationRecord, TradeDecision, TradeRecorder
from .reporter import ComparisonReporter

__all__ = [
    "AttributionAnalyzer",
    "AttributionEntry",
    "ComparisonAnalyzer",
    "ComparisonReporter",
    "ComparisonResult",
    "SimulationRecord",
    "TradeComparison",
    "TradeDecision",
    "TradeRecorder",
]
