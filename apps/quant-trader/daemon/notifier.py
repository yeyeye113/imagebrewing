"""通知系统 - 支持 WeChat Work / DingTalk / Telegram / 日志。"""

import logging

import requests


class Notifier:
    """Send trade alerts via webhook (WeChat Work / DingTalk / Telegram)."""

    def __init__(self, webhook_url: str = "", channel: str = ""):
        self.url = webhook_url.strip()
        self.channel = (channel or self._detect(webhook_url)).lower()

    @staticmethod
    def _detect(url: str) -> str:
        if not url:
            return "log"
        if "qyapi.weixin" in url:
            return "wecom"
        if "dingtalk" in url or "oapi.dingtalk" in url:
            return "dingtalk"
        if "telegram" in url or "t.me" in url:
            return "telegram"
        return "generic"

    def send(self, text: str, level: str = "info") -> bool:
        """Send a notification. Falls back to console log if no webhook."""
        if not self.url:
            logging.getLogger("daemon").info(f"  [通知:{level}] {text}")
            return True
        try:
            if self.channel == "wecom":
                return self._send_wecom(text)
            if self.channel == "dingtalk":
                return self._send_dingtalk(text, level)
            if self.channel == "telegram":
                return self._send_telegram(text)
            return self._send_generic(text)
        except ImportError:
            logging.getLogger("daemon").info(f"  [通知:{level}] {text}")
            return True
        except Exception:
            return False

    def _send_wecom(self, text: str) -> bool:
        try:
            resp = requests.post(
                self.url,
                json={
                    "msgtype": "markdown",
                    "markdown": {"content": text},
                },
                timeout=10,
            )
            return bool(resp.ok)
        except Exception:
            return False

    def _send_dingtalk(self, text: str, level: str) -> bool:
        prefix = {"critical": "🚨", "trade": "📊", "info": "ℹ️"}.get(level, "")
        try:
            resp = requests.post(
                self.url,
                json={
                    "msgtype": "text",
                    "text": {"content": f"{prefix} {text}"},
                },
                timeout=10,
            )
            return bool(resp.ok)
        except Exception:
            return False

    def _send_telegram(self, text: str) -> bool:
        try:
            resp = requests.post(
                self.url,
                json={
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            return bool(resp.ok)
        except Exception:
            return False

    def _send_generic(self, text: str) -> bool:
        try:
            resp = requests.post(self.url, json={"text": text, "level": "info"}, timeout=10)
            return bool(resp.ok)
        except Exception:
            return False
