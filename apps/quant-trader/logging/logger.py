"""
结构化日志器工厂

核心入口:
    setup_logging(config)   — 一次性初始化全局日志（root logger）
    get_logger(name, cat)   — 获取带分类标签的 logger

设计:
    - 全局配置挂在 root logger (quanttrader.*) 上
    - 各模块只管 get_logger()，不碰 handler
    - trace_id 通过 contextvars 自动传播
"""

import logging
import logging.config
from pathlib import Path
from typing import Any

from .filters import CategoryFilter, TraceFilter, set_trace_id
from .formatters import HumanFormatter, JsonFormatter
from .handlers import ConsoleHandler, DailyRotatingHandler, WebhookHandler

# ─── 默认配置 ───────────────────────────────────────────

DEFAULT_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"],
    },
    "loggers": {
        "quanttrader": {
            "level": "DEBUG",
            "propagate": True,
        },
    },
    "formatters": {
        "json": {
            "()": "quanttrader.logging.formatters.JsonFormatter",
            "include_stack": False,
        },
        "human": {
            "()": "quanttrader.logging.formatters.HumanFormatter",
            "color": True,
            "datefmt": "%H:%M:%S",
        },
    },
    "filters": {
        "trace": {
            "()": "quanttrader.logging.filters.TraceFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "human",
            "filters": ["trace"],
            "stream": "ext://sys.stdout",
        },
        "file": {
            "()": "quanttrader.logging.handlers.DailyRotatingHandler",
            "level": "DEBUG",
            "formatter": "json",
            "filters": ["trace"],
            "log_dir": "logs",
            "base_name": "quanttrader",
            "max_days": 30,
        },
    },
}


# ─── 便捷 Logger 封装 ────────────────────────────────────


class StructuredLogger:
    """
    带分类标签的 Logger 封装。

    用法:
        log = get_logger("engine.risk", category="risk")
        log.info("止损触发", extras={"symbol": "000001", "loss_pct": -5.2})

    分类在结构化日志中体现为 "cat" 字段，
    可配合 CategoryFilter 按分类路由到不同 handler。
    """

    __slots__ = ("_category", "_logger")

    def __init__(self, logger: logging.Logger, category: str | None = None):
        self._logger = logger
        self._category = category

    def _log(self, level: int, msg: str, *args, **kwargs) -> None:
        extras = kwargs.pop("extras", None)
        if args or kwargs:
            # 支持 %s 风格和 str.format 风格混合
            msg = msg % args if args else msg.format(**kwargs)

        # 创建 LogRecord 并注入 category
        record = self._logger.makeRecord(
            name=self._logger.name,
            level=level,
            fn="",
            lno=0,
            msg=msg,
            args=(),
            exc_info=kwargs.get("exc_info"),
        )
        if self._category:
            record.category = self._category
        if extras:
            record.extras = extras
        self._logger.handle(record)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs) -> None:
        kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, *args, **kwargs)

    # 透传属性
    @property
    def level(self) -> int:
        return self._logger.level

    @level.setter
    def level(self, val: int) -> None:
        self._logger.level = val

    @property
    def name(self) -> str:
        return self._logger.name

    def isEnabledFor(self, level: int) -> bool:
        return self._logger.isEnabledFor(level)


# ─── 核心初始化函数 ──────────────────────────────────────

_initialized = False


def setup_logging(
    log_dir: str = "logs",
    level: str = "DEBUG",
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    json_mode: bool = True,
    max_days: int = 30,
    webhook_url: str = "",
    webhook_min_level: str = "CRITICAL",
    categories_filter: set[str] | None = None,
) -> None:
    """
    一次性初始化全局日志系统。

    调用后所有 quanttrader.* 的 logger 自动使用统一 handler。
    幂等 — 多次调用只生效第一次。

    Args:
        log_dir: 日志文件目录
        level: root logger 最低级别
        console_level: 控制台输出最低级别
        file_level: 文件输出最低级别
        json_mode: True=JSON格式 False=人类可读格式
        max_days: 日志保留天数
        webhook_url: webhook 推送地址（空=不推送）
        webhook_min_level: webhook 触发的最低级别
        categories_filter: 只推送这些分类到 webhook（None=全部）
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # root logger
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))

    # 清理已有 handler（防止重复添加）
    root.handlers.clear()

    # 1) Console handler
    console = ConsoleHandler(color=True)
    console.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console.setFormatter(HumanFormatter(color=True))
    console.addFilter(TraceFilter())
    root.addHandler(console)

    # 2) File handler (JSON)
    file_fmt = JsonFormatter() if json_mode else HumanFormatter(color=False)
    fh = DailyRotatingHandler(
        log_dir=log_path,
        base_name="quanttrader",
        max_days=max_days,
    )
    fh.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
    fh.setFormatter(file_fmt)
    fh.addFilter(TraceFilter())
    root.addHandler(fh)

    # 3) Webhook handler (可选)
    if webhook_url:
        wh = WebhookHandler(
            url=webhook_url,
            min_level=getattr(logging, webhook_min_level.upper(), logging.CRITICAL),
        )
        wh.setFormatter(JsonFormatter())
        wh.addFilter(TraceFilter())
        if categories_filter:
            wh.addFilter(CategoryFilter(include=categories_filter))
        root.addHandler(wh)


def get_logger(name: str, category: str | None = None) -> StructuredLogger:
    """
    获取带分类标签的结构化 Logger。

    Args:
        name: logger 名称（推荐用 __name__）
        category: 日志分类（trade/risk/signal/system/data/llm/...）

    Returns:
        StructuredLogger 实例

    用法:
        log = get_logger(__name__, category="trade")
        log.info("买入 {symbol}", symbol="000001", extras={"price": 10.5})
    """
    logger = logging.getLogger(name)
    return StructuredLogger(logger, category=category)


def set_context(**kwargs: Any) -> None:
    """
    设置日志上下文（trace_id 等）。

    用法:
        set_context(trace_id="req-abc-123")
    """
    if "trace_id" in kwargs:
        set_trace_id(kwargs["trace_id"])


def clear_context() -> None:
    """清理所有日志上下文"""
    set_trace_id(None)
