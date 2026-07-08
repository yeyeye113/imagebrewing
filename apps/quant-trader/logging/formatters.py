"""
结构化日志格式化器

- JsonFormatter: 生产环境 JSON 结构化日志
- HumanFormatter: 开发环境可读格式（带颜色）
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import ClassVar


class JsonFormatter(logging.Formatter):
    """JSON 结构化格式化器 — 生产/分析友好"""

    # 日志级别→短标签映射
    _LEVEL_MAP: ClassVar[dict[int, str]] = {
        logging.DEBUG: "DBG",
        logging.INFO: "INF",
        logging.WARNING: "WRN",
        logging.ERROR: "ERR",
        logging.CRITICAL: "CRT",
    }

    def __init__(self, *, include_stack: bool = False, tz: str = "Asia/Shanghai"):
        super().__init__()
        self._include_stack = include_stack
        self._tz_name = tz

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat()

        doc = {
            "ts": ts,
            "level": self._LEVEL_MAP.get(record.levelno, str(record.levelno)),
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # 分类标签（由 filter 注入或用户手动设置）
        cat = getattr(record, "category", None)
        if cat:
            doc["cat"] = cat

        # trace_id（由 TraceFilter 注入）
        tid = getattr(record, "trace_id", None)
        if tid:
            doc["trace_id"] = tid

        # 模块来源
        doc["mod"] = f"{record.module}:{record.lineno}"

        # 异常信息
        if record.exc_info and record.exc_info[1]:
            doc["exc"] = self.formatException(record.exc_info)

        # 额外字段（extras dict）
        extras = getattr(record, "extras", None)
        if extras and isinstance(extras, dict):
            doc.update(extras)

        return json.dumps(doc, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    """人类友好格式化器 — 开发/控制台用"""

    COLORS: ClassVar[dict[int, str]] = {
        logging.DEBUG: "\033[36m",  # cyan
        logging.INFO: "\033[32m",  # green
        logging.WARNING: "\033[33m",  # yellow
        logging.ERROR: "\033[31m",  # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def __init__(self, color: bool = True, datefmt: str = "%H:%M:%S"):
        super().__init__(datefmt=datefmt)
        self._color = color and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, self.datefmt)
        level = record.levelname[0]  # D/I/W/E/C
        cat = getattr(record, "category", "")
        tid = getattr(record, "trace_id", "")

        # 拼装头部
        parts = [f"{ts} {level} {record.name}"]
        if cat:
            parts.append(f"[{cat}]")
        if tid:
            parts.append(f"(trace:{tid[:8]})")

        msg = record.getMessage()
        line = f"{' '.join(parts)} {msg}"

        if self._color:
            c = self.COLORS.get(record.levelno, "")
            if c:
                line = f"{c}{line}{self.RESET}"

        if record.exc_info and record.exc_info[1]:
            line += "\n" + self.formatException(record.exc_info)

        return line
