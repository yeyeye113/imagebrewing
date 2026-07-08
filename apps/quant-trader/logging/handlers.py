"""
日志处理器

- DailyRotatingHandler: 按日轮转文件 + 自动清理过期日志
- ConsoleHandler: 带颜色的控制台输出
- SyslogHandler: UDP syslog 推送（可选，用于集中日志平台）
- WebhookHandler: HTTP webhook 推送（与现有 alerts 系统对接）
"""

import json
import logging
import logging.handlers
import socket
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path


class DailyRotatingHandler(logging.Handler):
    """
    按日轮转的文件处理器。

    文件命名: {base_name}_{YYYYMMDD}.log
    自动清理: 保留最近 max_days 天的日志
    编码: UTF-8（支持中文）
    """

    def __init__(
        self,
        log_dir: str | Path,
        base_name: str = "quanttrader",
        max_days: int = 30,
        level: int = logging.DEBUG,
    ):
        super().__init__(level=level)
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._base_name = base_name
        self._max_days = max_days
        self._current_date: str | None = None
        self._current_fh: logging.FileHandler | None = None
        self._cleanup_old_logs()

    def _get_log_path(self, date_str: str) -> Path:
        return self._log_dir / f"{self._base_name}_{date_str}.log"

    def _rotate_if_needed(self) -> None:
        today = datetime.now().strftime("%Y%m%d")
        if today != self._current_date:
            if self._current_fh:
                self._current_fh.close()
            path = self._get_log_path(today)
            self._current_fh = logging.FileHandler(path, encoding="utf-8")
            self._current_fh.setFormatter(logging.Formatter("%(message)s"))
            self._current_date = today

    def _cleanup_old_logs(self) -> None:
        """删除超过 max_days 天的旧日志文件"""
        cutoff = datetime.now() - timedelta(days=self._max_days)
        pattern = f"{self._base_name}_*.log"
        try:
            for f in self._log_dir.glob(pattern):
                if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink(missing_ok=True)
        except Exception:
            pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._rotate_if_needed()
            fh = self._current_fh
            stream = fh.stream if fh is not None else None
            if stream is None:  # _rotate_if_needed 恒定装配; 防御性兜底 (delay 模式 stream 可为 None)
                return
            msg = self.format(record)
            stream.write(msg + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._current_fh:
            self._current_fh.close()
        super().close()


class ConsoleHandler(logging.StreamHandler):
    """控制台处理器 — 默认输出到 stderr"""

    def __init__(self, stream=None, color: bool = True):
        super().__init__(stream or sys.stderr)
        self._use_color = color and hasattr(stream or sys.stderr, "isatty") and (stream or sys.stderr).isatty()


class SyslogHandler(logging.Handler):
    """
    UDP syslog 推送处理器。

    用于将结构化日志推送到集中式日志平台（Graylog/ELK/Fluentd）。
    默认使用 UDP，也可切换为 TCP（设置 use_tcp=True）。
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 514,
        facility: int = 1,  # user-level
        use_tcp: bool = False,
    ):
        super().__init__()
        self._host = host
        self._port = port
        self._facility = facility
        self._use_tcp = use_tcp
        self._sock: socket.socket | None = None
        self._connect()

    def _connect(self) -> None:
        sock_type = socket.SOCK_STREAM if self._use_tcp else socket.SOCK_DGRAM
        self._sock = socket.socket(socket.AF_INET, sock_type)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sock = self._sock
            if sock is None:  # __init__ 已 _connect; 防御兜底
                return
            msg = self.format(record)
            # RFC 3164 syslog header
            priority = (self._facility << 3) | record.levelno
            syslog_msg = f"<{priority}>{datetime.now().strftime('%b %d %H:%M:%S')} {socket.gethostname()} {msg}"
            payload = syslog_msg.encode("utf-8")[:4096]  # syslog 最大 4KB

            if self._use_tcp:
                sock.sendall(payload)
            else:
                sock.sendto(payload, (self._host, self._port))
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._sock:
            self._sock.close()
        super().close()


class WebhookHandler(logging.Handler):
    """
    HTTP Webhook 推送处理器。

    将 CRITICAL/FATAL 级别的日志推送到外部通知系统（企微/钉钉/Telegram）。
    内置节流：同一内容 60 秒内不重复推送。
    """

    def __init__(
        self,
        url: str,
        min_level: int = logging.CRITICAL,
        timeout: int = 5,
    ):
        super().__init__(min_level)
        self._url = url
        self._timeout = timeout
        self._last_sent: dict[str, float] = {}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            # 简单节流：相同消息 60s 内不重发
            key = f"{record.levelname}:{record.getMessage()[:50]}"
            now = time.time()
            if key in self._last_sent and (now - self._last_sent[key]) < 60:
                return
            self._last_sent[key] = now

            payload = json.dumps(
                {
                    "msgtype": "text",
                    "text": {"content": f"[{record.levelname}] {msg}"},
                }
            ).encode("utf-8")

            req = urllib.request.Request(
                self._url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=self._timeout)
        except Exception:
            self.handleError(record)
