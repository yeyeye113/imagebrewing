"""
quanttrader.logging — 结构化日志系统

统一日志入口，替换分散在 daemon/forecast/tracker 中的独立 logging 设置。

快速开始:
    from quanttrader.logging import setup_logging, get_logger, set_context

    # 初始化（daemon.py / run.py 入口调一次）
    setup_logging(log_dir="logs", level="DEBUG")

    # 各模块用法
    log = get_logger(__name__, category="trade")
    set_context(trace_id="req-123")
    log.info("买入 000001", extras={"price": 10.5, "qty": 100})

日志输出（JSON 模式）:
    {"ts": "2026-06-24T12:00:00+00:00", "level": "INF", "logger": "quanttrader.trader",
     "msg": "买入 000001", "cat": "trade", "trace_id": "req-123", "mod": "trader:42",
     "price": 10.5, "qty": 100}
"""

from .filters import (
    CATEGORIES,
    CategoryFilter,
    LevelRangeFilter,
    TraceFilter,
    get_trace_id,
    set_trace_id,
)
from .formatters import HumanFormatter, JsonFormatter
from .handlers import (
    ConsoleHandler,
    DailyRotatingHandler,
    SyslogHandler,
    WebhookHandler,
)
from .logger import (
    StructuredLogger,
    clear_context,
    get_logger,
    set_context,
    setup_logging,
)

__all__ = [
    "CATEGORIES",
    "CategoryFilter",
    "ConsoleHandler",
    # 处理器
    "DailyRotatingHandler",
    "HumanFormatter",
    # 格式化器
    "JsonFormatter",
    "LevelRangeFilter",
    # 类型
    "StructuredLogger",
    "SyslogHandler",
    # 过滤器
    "TraceFilter",
    "WebhookHandler",
    "clear_context",
    "get_logger",
    "get_trace_id",
    "set_context",
    # trace_id 管理
    "set_trace_id",
    # 核心 API
    "setup_logging",
]
