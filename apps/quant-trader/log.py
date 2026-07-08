"""Unified logging framework for quant-trader.

Replaces ad-hoc ``print()`` calls with a proper ``logging`` hierarchy:

- Console handler: human-readable, INFO level by default
- File handler: JSONL format, DEBUG level, daily rotation
- Configurable via environment variables: QT_LOG_LEVEL, QT_LOG_FILE, QT_LOG_FILE_LEVEL, QT_LOG_FMT

Usage::

    from quanttrader.log import get_logger, setup_logging

    setup_logging()                # once at entry point
    logger = get_logger(__name__)  # per module
    logger.info("backtest done, sharpe=%.2f", 1.5)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

# ── Environment-driven config ────────────────────────────────────────

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


QT_LOG_LEVEL = _env("QT_LOG_LEVEL", "INFO").upper()
QT_LOG_FILE = os.environ.get("QT_LOG_FILE", "").strip()
QT_LOG_FILE_LEVEL = _env("QT_LOG_FILE_LEVEL", "DEBUG").upper()
QT_LOG_FMT = _env("QT_LOG_FMT", "text").lower()  # "text" | "json"

# Default log directory — sibling to the package root
_DEFAULT_LOG_DIR = Path(__file__).resolve().parent / "logs"

# Guard to ensure handlers aren't attached more than once.
_setup_done = False
_root_initialized = False


# ── Structured log records (for JSONL output) ────────────────────────

@dataclass
class TradeLog:
    """Standardized trade/order log entry."""
    timestamp: str = ""
    log_type: str = "trade"
    order_id: str = ""
    symbol: str = ""
    side: str = ""              # buy | sell
    qty: float = 0.0
    notional: float = 0.0
    price: float = 0.0
    fees: float = 0.0
    status: str = ""            # filled | rejected | pending
    note: str = ""
    cash_after: float = 0.0
    equity_after: float = 0.0

    def to_line(self) -> str:
        d = asdict(self)
        d["timestamp"] = datetime.now().isoformat()
        return json.dumps(d, ensure_ascii=False)


@dataclass
class LLMCallLog:
    """Standardized LLM call log entry."""
    timestamp: str = ""
    log_type: str = "llm_call"
    provider: str = ""
    model: str = ""
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    signal: int = 0
    confidence: float = 0.0
    ok: bool = True
    error: str = ""

    def to_line(self) -> str:
        d = asdict(self)
        d["timestamp"] = datetime.now().isoformat()
        return json.dumps(d, ensure_ascii=False)


# ── Structured JSON formatter ────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            obj["error"] = str(record.exc_info[1])
        # Merge extra dict if present
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            obj.update(record.extra)
        return json.dumps(obj, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable coloured output for terminal use."""

    LEVEL_COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"
    GREY = "\033[90m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelname, "")
        level = f"{color}{record.levelname:<7}{self.RESET}"
        ts = f"{self.GREY}{datetime.now().strftime('%H:%M:%S')}{self.RESET}"
        name = f"{self.GREY}{record.name}{self.RESET}"
        return f"{ts}  {level}  {name}  {record.getMessage()}"


# ── Daily rotating file handler ──────────────────────────────────────

class DailyRotatingHandler(logging.FileHandler):
    """A file handler that switches to a new file when the date changes.

    Automatically deletes old log files beyond ``max_files`` (default 30 days).
    """

    def __init__(self, log_dir: str, level: int = logging.DEBUG, max_files: int = 30):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._current_date = ""
        self._level = level
        self._max_files = max_files
        super().__init__(self._today_path(), encoding="utf-8", delay=False)
        self.setLevel(level)
        if max_files > 0:
            self._cleanup()

    def _today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _today_path(self) -> str:
        return str(self._log_dir / f"trader_{self._today_str()}.log")

    def _cleanup(self) -> None:
        """Remove old log files keeping at most ``_max_files`` newest ones."""
        try:
            files = sorted(self._log_dir.glob("trader_*.log"))
            if len(files) > self._max_files:
                for old in files[: len(files) - self._max_files]:
                    try:
                        old.unlink()
                    except OSError:
                        pass
        except Exception:
            pass

    def emit(self, record: logging.LogRecord) -> None:
        today = self._today_str()
        if today != self._current_date:
            self._current_date = today
            self.close()
            self.baseFilename = self._today_path()
            self._open()
            if self._max_files > 0:
                self._cleanup()
        super().emit(record)


# ── Public API ───────────────────────────────────────────────────────

def setup_logging(
    console_level: str = "",
    file_level: str = "",
    log_file: str = "",
    fmt: str = "",
) -> None:
    """One-time global logging initialisation.  Safe to call more than once.

    Parameters are optional; when omitted they fall back to the environment
    variables ``QT_LOG_LEVEL``, ``QT_LOG_FILE_LEVEL``, ``QT_LOG_FILE``,
    ``QT_LOG_FMT``.
    """
    global _setup_done, _root_initialized

    console_level = (console_level or QT_LOG_LEVEL).upper()
    file_level = (file_level or QT_LOG_FILE_LEVEL).upper()
    fmt = (fmt or QT_LOG_FMT).lower()

    root = logging.getLogger()
    if _root_initialized:
        return

    root.setLevel(logging.DEBUG)  # let handlers filter

    # ── Console handler ───────────────────────────────────────────
    if console_level != "OFF":
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(getattr(logging, console_level, logging.INFO))
        if fmt == "json":
            ch.setFormatter(JsonFormatter())
        else:
            ch.setFormatter(ConsoleFormatter())
        root.addHandler(ch)

    # ── File handler ──────────────────────────────────────────────
    fh_level = getattr(logging, file_level, logging.DEBUG)
    if fh_level != logging.NOTSET:
        actual_file = log_file or QT_LOG_FILE
        if actual_file:
            fh = DailyRotatingHandler(
                str(Path(actual_file).parent),
                level=fh_level,
            )
        else:
            fh = DailyRotatingHandler(str(_DEFAULT_LOG_DIR), level=fh_level)
        if fmt == "json":
            fh.setFormatter(JsonFormatter())
        else:
            fh.setFormatter(logging.Formatter(
                "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
        root.addHandler(fh)

    # Suppress noisy third-party loggers unless in DEBUG.
    if console_level != "DEBUG":
        for noisy in ("uvicorn", "uvicorn.access", "httpx", "httpcore", "urllib3"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    _setup_done = True
    _root_initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for *name*, ensuring the global setup has run.

    Typical usage in a module::

        from quanttrader.log import get_logger
        logger = get_logger(__name__)
    """
    if not _root_initialized:
        setup_logging()
    return logging.getLogger(name)


def log_trade(logger: logging.Logger, **kwargs: Any) -> None:
    """Log a structured trade event to the file handler (as JSON extra)."""
    entry = TradeLog(**{k: v for k, v in kwargs.items() if k in TradeLog.__dataclass_fields__})
    logger.info(
        "TRADE | %s | %s %s | qty=%s notional=%s | price=%s | status=%s",
        entry.order_id, entry.side, entry.symbol,
        entry.qty, entry.notional, entry.price, entry.status,
        extra={"log_type": "trade", "data": entry.to_line()},
    )


def log_llm_call(logger: logging.Logger, **kwargs: Any) -> None:
    """Log a structured LLM call event."""
    entry = LLMCallLog(**{k: v for k, v in kwargs.items() if k in LLMCallLog.__dataclass_fields__})
    status = "OK" if entry.ok else f"FAIL({entry.error})"
    logger.info(
        "LLM | %s/%s | %.2fs | %d→%d tokens | sig=%d conf=%.2f | %s",
        entry.provider, entry.model, entry.latency_s,
        entry.prompt_tokens, entry.completion_tokens,
        entry.signal, entry.confidence, status,
        extra={"log_type": "llm_call", "data": entry.to_line()},
    )
