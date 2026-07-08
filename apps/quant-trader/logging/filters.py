"""
日志过滤器

- TraceFilter: 自动注入 trace_id（基于 contextvars，跨 async/线程）
- CategoryFilter: 按日志分类过滤（trade/risk/signal/system/data）
- LevelRangeFilter: 按日志级别范围过滤
"""

import contextvars
import logging

# ─── trace_id 上下文管理 ────────────────────────────────
_trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


def set_trace_id(tid: str | None) -> None:
    """设置当前上下文的 trace_id"""
    _trace_id_ctx.set(tid)


def get_trace_id() -> str | None:
    """获取当前上下文的 trace_id"""
    return _trace_id_ctx.get()


# ─── 预定义日志分类 ─────────────────────────────────────
CATEGORIES = frozenset(
    {
        "trade",  # 买卖执行
        "risk",  # 风控触发
        "signal",  # 信号生成
        "system",  # 守护进程/系统
        "data",  # 数据源
        "llm",  # LLM 调用
        "scanner",  # 选股扫描
        "news",  # 新闻
        "backtest",  # 回测
        "portfolio",  # 组合管理
        "divination",  # 周易
    }
)


class TraceFilter(logging.Filter):
    """
    自动注入 trace_id 到每条日志记录。

    用法:
        set_trace_id("abc-123")   # 在请求/任务入口设置
        logger.info("...")        # 日志自动携带 trace_id
        set_trace_id(None)        # 任务结束清理
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


class CategoryFilter(logging.Filter):
    """
    按分类过滤日志。

    include: 只保留这些分类（空集 = 不过滤）
    exclude: 排除这些分类

    用法:
        handler.addFilter(CategoryFilter(include={"trade", "risk"}))
        handler.addFilter(CategoryFilter(exclude={"system"}))
    """

    def __init__(
        self,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ):
        super().__init__()
        self._include = frozenset(include) if include else frozenset()
        self._exclude = frozenset(exclude) if exclude else frozenset()

    def filter(self, record: logging.LogRecord) -> bool:
        cat = getattr(record, "category", None)
        if not cat:
            # 无分类记录：包含（除非 include 非空且不包含 None 语义）
            return not self._include
        if self._include and cat not in self._include:
            return False
        if self._exclude and cat in self._exclude:
            return False
        return True


class LevelRangeFilter(logging.Filter):
    """
    只保留指定级别范围内的日志。

    用法:
        handler.addFilter(LevelRangeFilter(min_level=logging.WARNING))
        handler.addFilter(LevelRangeFilter(max_level=logging.INFO))  # 只看 DEBUG+INFO
    """

    def __init__(
        self,
        min_level: int = logging.DEBUG,
        max_level: int = logging.CRITICAL,
    ):
        super().__init__()
        self._min = min_level
        self._max = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return self._min <= record.levelno <= self._max
