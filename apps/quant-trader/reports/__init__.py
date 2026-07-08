"""量化交易报告生成系统。

- daily: 每日交易报告
- weekly: 每周汇总报告
- monthly: 月度绩效报告
- generator: HTML 报告生成引擎
"""

from .daily import DailyReport
from .generator import ReportGenerator
from .monthly import MonthlyReport
from .weekly import WeeklyReport

__all__ = ["DailyReport", "MonthlyReport", "ReportGenerator", "WeeklyReport"]
