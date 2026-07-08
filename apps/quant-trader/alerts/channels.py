"""告警渠道实现 — 六种推送通道统一接口。

每个通道继承 ChannelBase，实现 send(text, title, level) -> bool。
所有通道共用 requests 做 HTTP 调用，超时 10 秒，失败静默不阻断。
"""

from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests

logger = logging.getLogger("quanttrader.alerts.channels")

_LEVEL_EMOJI = {"INFO": "ℹ️", "WARN": "⚠️", "CRITICAL": "🚨"}

_TIMEOUT = 10  # seconds


class ChannelBase(ABC):
    """推送通道基类。"""

    name: str = "base"

    @abstractmethod
    def send(self, text: str, title: str = "", level: str = "INFO") -> bool:
        """发送消息，成功返回 True。"""

    def _log_success(self, text: str) -> None:
        logger.info("[%s] 推送成功: %s", self.name, text[:80])

    def _log_fail(self, err: Exception) -> None:
        logger.warning("[%s] 推送失败: %s", self.name, err)


# ── 1. 企业微信机器人 ────────────────────────────────────────────


class WeComChannel(ChannelBase):
    """企业微信群机器人 webhook。"""

    name = "wecom"

    def __init__(self, webhook_url: str):
        self.url = webhook_url.rstrip("/")

    def send(self, text: str, title: str = "", level: str = "INFO") -> bool:
        emoji = _LEVEL_EMOJI.get(level, "")
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": f"{emoji} **{title or '告警'}**\n\n{text}"},
        }
        return self._post(payload)

    def _post(self, payload: dict) -> bool:
        try:
            r = requests.post(self.url, json=payload, timeout=_TIMEOUT)
            r.raise_for_status()
            self._log_success(str(payload["markdown"]["content"])[:50])
            return True
        except Exception as e:
            self._log_fail(e)
            return False


# ── 2. 钉钉机器人 ────────────────────────────────────────────────


class DingTalkChannel(ChannelBase):
    """钉钉群机器人 webhook。"""

    name = "dingtalk"

    def __init__(self, webhook_url: str, secret: str = ""):
        self.url = webhook_url.rstrip("/")
        self.secret = secret

    def send(self, text: str, title: str = "", level: str = "INFO") -> bool:
        emoji = _LEVEL_EMOJI.get(level, "")
        payload: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {"title": title or "告警", "text": f"{emoji} **{title or '告警'}**\n\n{text}"},
        }
        url = self._sign_url() if self.secret else self.url
        return self._post(url, payload)

    def _sign_url(self) -> str:
        import hashlib
        import hmac
        import time
        import urllib.parse

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        import base64

        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return f"{self.url}&timestamp={timestamp}&sign={sign}"

    def _post(self, url: str, payload: dict) -> bool:
        try:
            r = requests.post(url, json=payload, timeout=_TIMEOUT)
            r.raise_for_status()
            self._log_success(str(payload["markdown"]["text"])[:50])
            return True
        except Exception as e:
            self._log_fail(e)
            return False


# ── 3. Telegram Bot ──────────────────────────────────────────────


class TelegramChannel(ChannelBase):
    """Telegram Bot 推送 (sendMessage API)。"""

    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id

    def send(self, text: str, title: str = "", level: str = "INFO") -> bool:
        emoji = _LEVEL_EMOJI.get(level, "")
        full = f"{emoji} **{title}**\n\n{text}" if title else f"{emoji} {text}"
        payload = {
            "chat_id": self.chat_id,
            "text": full,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(self.api, json=payload, timeout=_TIMEOUT)
            r.raise_for_status()
            self._log_success(full[:50])
            return True
        except Exception as e:
            self._log_fail(e)
            return False


# ── 4. SMTP 邮件 ─────────────────────────────────────────────────


class EmailChannel(ChannelBase):
    """SMTP 邮件推送。"""

    name = "email"

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 465,
        username: str = "",
        password: str = "",
        from_addr: str = "",
        to_addrs: list[str] | None = None,
        use_ssl: bool = True,
    ):
        self.host = smtp_host
        self.port = smtp_port
        self.user = username
        self.passwd = password
        self.from_addr = from_addr or username
        self.to_addrs = to_addrs or []
        self.use_ssl = use_ssl

    def send(self, text: str, title: str = "", level: str = "INFO") -> bool:
        if not self.to_addrs:
            logger.warning("[email] 未配置收件人，跳过")
            return False

        emoji = _LEVEL_EMOJI.get(level, "")
        subject = f"{emoji} {title or '量化交易告警'}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)

        # 纯文本 + HTML 双版本
        msg.attach(MIMEText(text, "plain", "utf-8"))
        html = text.replace("\n", "<br>")
        html_body = f"<html><body><pre style='font-family:monospace'>{html}</pre></body></html>"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            server: smtplib.SMTP  # SMTP_SSL 为其子类, 统一按基类使用
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=_TIMEOUT)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=_TIMEOUT)
                server.starttls()
            server.login(self.user, self.passwd)
            server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            server.quit()
            self._log_success(subject)
            return True
        except Exception as e:
            self._log_fail(e)
            return False


# ── 5. Server酱 (微信推送) ───────────────────────────────────────


class ServerChanChannel(ChannelBase):
    """Server酱 — 微信消息推送。"""

    name = "serverchan"

    def __init__(self, send_key: str):
        self.url = f"https://sctapi.ftqq.com/{send_key}.send"

    def send(self, text: str, title: str = "", level: str = "INFO") -> bool:
        emoji = _LEVEL_EMOJI.get(level, "")
        payload = {
            "title": f"{emoji} {title or '量化告警'}",
            "desp": text,
        }
        try:
            r = requests.post(self.url, data=payload, timeout=_TIMEOUT)
            r.raise_for_status()
            self._log_success(payload["title"])
            return True
        except Exception as e:
            self._log_fail(e)
            return False


# ── 6. Bark (iOS 推送) ───────────────────────────────────────────


class BarkChannel(ChannelBase):
    """Bark — iOS 推送通知。"""

    name = "bark"

    def __init__(self, device_key: str, server_url: str = "https://api.day.app"):
        self.base = f"{server_url.rstrip('/')}/{device_key}"

    def send(self, text: str, title: str = "", level: str = "INFO") -> bool:
        emoji = _LEVEL_EMOJI.get(level, "")
        payload = {
            "title": f"{emoji} {title or '量化告警'}",
            "body": text,
            "group": "quant-trader",
            "sound": "alarm" if level == "CRITICAL" else "bell",
        }
        try:
            r = requests.post(self.base, json=payload, timeout=_TIMEOUT)
            r.raise_for_status()
            self._log_success(payload["title"])
            return True
        except Exception as e:
            self._log_fail(e)
            return False


# ── 控制台（兜底）────────────────────────────────────────────────


class ConsoleChannel(ChannelBase):
    """仅打印到日志，无外部依赖。"""

    name = "console"

    def send(self, text: str, title: str = "", level: str = "INFO") -> bool:
        emoji = _LEVEL_EMOJI.get(level, "")
        logger.info("[Console] %s %s\n%s", emoji, title or "告警", text)
        return True


# ── 工厂 ─────────────────────────────────────────────────────────

_CHANNEL_MAP: dict[str, type[ChannelBase]] = {
    "wecom": WeComChannel,
    "dingtalk": DingTalkChannel,
    "telegram": TelegramChannel,
    "email": EmailChannel,
    "serverchan": ServerChanChannel,
    "bark": BarkChannel,
    "console": ConsoleChannel,
}


def create_channel(channel_type: str, **kwargs: Any) -> ChannelBase:
    """根据类型名创建通道实例。

    channel_type: wecom | dingtalk | telegram | email | serverchan | bark | console
    **kwargs: 传递给对应通道的构造参数。
    """
    cls = _CHANNEL_MAP.get(channel_type.lower())
    if cls is None:
        raise ValueError(f"未知通道类型: {channel_type!r}。可用: {list(_CHANNEL_MAP)}")
    return cls(**kwargs)
