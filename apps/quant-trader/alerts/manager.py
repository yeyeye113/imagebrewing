"""告警管理器 — 统一入口：去重 + 规则评估 + 多通道推送 + 历史记录。

Quick start:
    mgr = AlertManager.from_yaml("daemon.yaml")
    mgr.send(
        title="买入信号",
        text="标的: 600519 价格: 1800",
        event_type="trade",
        variables={"symbol": "600519", "price": 1800},
    )

与 daemon.py 集成:
    # 在 daemon 启动时初始化
    alert_mgr = AlertManager.from_yaml("daemon.yaml")

    # 交易信号
    alert_mgr.send_trade_signal("buy", symbol="600519", price=1800, ...)

    # 风控触发
    alert_mgr.send_risk_alert("stop_loss", symbol="600519", ...)

    # 每日总结
    alert_mgr.send_daily_summary(symbol="600519", day_trades=3, ...)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from quanttrader.alerts.channels import ChannelBase, ConsoleChannel, create_channel
from quanttrader.alerts.rules import AlertLevel, RuleEngine, default_level
from quanttrader.alerts.templates import render, render_named

logger = logging.getLogger("quanttrader.alerts")

# ── 告警历史记录 ─────────────────────────────────────────────────


@dataclass
class AlertRecord:
    """一条告警历史。"""

    timestamp: str
    event_type: str
    level: str
    title: str
    text: str
    channel_results: dict[str, bool] = field(default_factory=dict)
    dedup_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "level": self.level,
            "title": self.title,
            "text": self.text,
            "channel_results": self.channel_results,
            "dedup_key": self.dedup_key,
        }


# ── 告警管理器 ───────────────────────────────────────────────────


class AlertManager:
    """告警系统核心：去重 + 规则 + 多通道 + 历史。"""

    def __init__(
        self,
        channels: list[ChannelBase] | None = None,
        history_path: str = "logs/alert_history.json",
        max_history: int = 500,
    ):
        self.channels: list[ChannelBase] = channels or [ConsoleChannel()]
        self.rules = RuleEngine()
        self._dedup: dict[str, float] = {}  # dedup_key -> last_send_ts
        self._dedup_lock = threading.Lock()
        self._history: list[AlertRecord] = []
        self.history_path = Path(history_path)
        self.max_history = max_history
        self._default_dedup_minutes: int = 5  # 同类告警去重窗口 (from_yaml 可覆盖)
        self._load_history()

    # ── 从配置创建 ──────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, config_path: str) -> AlertManager:
        """从 daemon.yaml 或 config.yaml 读取告警配置并创建实例。

        配置结构（新增 alerts 节）:
        ```yaml
        alerts:
          enabled: true
          history_path: logs/alert_history.json
          default_dedup_minutes: 5
          channels:
            - type: wecom
              webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
            - type: telegram
              bot_token: "xxx"
              chat_id: "xxx"
            - type: email
              smtp_host: smtp.qq.com
              smtp_port: 465
              username: "xxx"
              password: "xxx"
              to_addrs: ["admin@example.com"]
        ```
        """
        p = Path(config_path)
        if not p.exists():
            logger.warning("配置文件不存在: %s，使用控制台通道", config_path)
            return cls()

        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

        # 兼容旧格式：有 webhook_url 但无 alerts 节
        alert_cfg = data.get("alerts", {})
        if not alert_cfg and data.get("webhook_url"):
            # 自动迁移旧配置
            alert_cfg = {
                "enabled": True,
                "channels": [
                    {"type": cls._guess_channel_type(data["webhook_url"]), "webhook_url": data["webhook_url"]}
                ],
            }

        if not alert_cfg or not alert_cfg.get("enabled", True):
            logger.info("告警系统已禁用")
            return cls(channels=[ConsoleChannel()])

        # 创建通道
        channels: list[ChannelBase] = []
        for ch_cfg in alert_cfg.get("channels", []):
            ch_type = ch_cfg.pop("type", "console")
            try:
                channels.append(create_channel(ch_type, **ch_cfg))
            except Exception as e:
                logger.warning("创建通道 %s 失败: %s", ch_type, e)

        if not channels:
            channels = [ConsoleChannel()]

        history_path = alert_cfg.get("history_path", "logs/alert_history.json")

        mgr = cls(channels=channels, history_path=history_path)
        mgr._default_dedup_minutes = alert_cfg.get("default_dedup_minutes", 5)
        return mgr

    @staticmethod
    def _guess_channel_type(url: str) -> str:
        """从 webhook URL 猜测通道类型。"""
        u = url.lower()
        if "qyapi.weixin.qq.com" in u:
            return "wecom"
        if "dingtalk.com" in u:
            return "dingtalk"
        if "api.telegram.org" in u:
            return "telegram"
        return "wecom"  # 默认企微

    # ── 核心发送 ────────────────────────────────────────────────

    def send(
        self,
        title: str,
        text: str,
        event_type: str = "custom",
        level: AlertLevel | str | None = None,
        variables: dict[str, Any] | None = None,
        template: str | None = None,
        dedup_minutes: int | None = None,
        force: bool = False,
    ) -> bool:
        """发送告警。

        Args:
            title:          告警标题
            text:           告警正文（若提供 template 则被覆盖）
            event_type:     事件类型（trade / risk / system / ...）
            level:          告警级别，默认从 event_type 推断
            variables:      模板变量
            template:       模板名（内置或自定义），提供后 text 被渲染结果覆盖
            dedup_minutes:  去重冷却（分钟）；None = 用配置的 default_dedup_minutes，0 = 不去重
            force:          忽略去重强制发送

        Returns:
            是否至少有一个通道发送成功。
        """
        # 0. 去重窗口默认值: 未显式指定时取 YAML 的 default_dedup_minutes
        #    (显式传 0 仍表示"不去重", 保持既有调用方语义不变)
        if dedup_minutes is None:
            dedup_minutes = self._default_dedup_minutes

        # 1. 级别推断
        if level is None:
            level = default_level(event_type)
        elif isinstance(level, str):
            level = AlertLevel(level)

        # 2. 模板渲染
        if template:
            vars_ = variables or {}
            vars_.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            try:
                text = render_named(template, vars_)
            except KeyError:
                text = render(text, vars_)

        # 3. 去重检查
        dedup_key = self._make_dedup_key(event_type, title, text, level.value)
        if not force and dedup_minutes > 0 and self._is_duplicate(dedup_key, dedup_minutes):
            logger.debug("告警去重: %s (%d分钟内)", title, dedup_minutes)
            return False

        # 4. 推送到所有通道
        channel_results: dict[str, bool] = {}
        any_success = False
        for ch in self.channels:
            ok = ch.send(text, title=title, level=level.value if isinstance(level, AlertLevel) else str(level))
            channel_results[ch.name] = ok
            any_success = any_success or ok

        # 5. 记录历史
        record = AlertRecord(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            level=level.value if isinstance(level, AlertLevel) else str(level),
            title=title,
            text=text,
            channel_results=channel_results,
            dedup_key=dedup_key,
        )
        self._add_history(record)

        # 6. 更新去重时间戳
        if dedup_minutes > 0:
            self._update_dedup(dedup_key)

        return any_success

    # ── 便捷方法 ────────────────────────────────────────────────

    def send_trade_signal(
        self,
        side: str,
        symbol: str,
        price: float,
        notional: float = 0,
        confidence: float = 0,
        strategy: str = "",
        **extra: Any,
    ) -> bool:
        """发送交易信号告警。"""
        template = "trade_buy" if side.lower() in ("buy", "long") else "trade_sell"
        variables = {
            "symbol": symbol,
            "price": f"${price:,.2f}",
            "notional": f"${notional:,.0f}" if notional else "-",
            "confidence": f"{confidence:.0%}",
            "strategy": strategy or "-",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **extra,
        }
        event = "trade_buy" if side.lower() in ("buy", "long") else "trade_sell"
        return self.send(
            title=f"{'买入' if 'buy' in side.lower() else '卖出'} {symbol}",
            text="",
            event_type=event,
            template=template,
            variables=variables,
            dedup_minutes=0,  # 交易信号不去重
            force=True,
        )

    def send_risk_alert(
        self,
        risk_type: str,
        symbol: str = "",
        entry_price: float = 0,
        current_price: float = 0,
        peak_price: float = 0,
        drawdown_pct: str = "",
        threshold_pct: str = "",
        peak_equity: float = 0,
        current_equity: float = 0,
        **extra: Any,
    ) -> bool:
        """发送风控告警。"""
        template_map = {
            "stop_loss": "risk_stop_loss",
            "take_profit": "risk_stop_loss",
            "trailing_stop": "risk_trailing_stop",
            "circuit_breaker": "risk_circuit_breaker",
        }
        template = template_map.get(risk_type, "risk_stop_loss")
        event = f"risk_{risk_type}"

        loss_pct = ""
        if entry_price and current_price:
            pct = (current_price - entry_price) / entry_price
            loss_pct = f"{pct:+.2%}"

        drop_pct = ""
        if peak_price and current_price:
            pct = (current_price - peak_price) / peak_price
            drop_pct = f"{pct:+.2%}"

        variables = {
            "symbol": symbol,
            "entry_price": f"${entry_price:,.2f}" if entry_price else "-",
            "current_price": f"${current_price:,.2f}" if current_price else "-",
            "peak_price": f"${peak_price:,.2f}" if peak_price else "-",
            "loss_pct": loss_pct,
            "drop_pct": drop_pct,
            "drawdown_pct": drawdown_pct,
            "threshold_pct": threshold_pct,
            "peak_equity": f"${peak_equity:,.0f}" if peak_equity else "-",
            "current_equity": f"${current_equity:,.0f}" if current_equity else "-",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **extra,
        }
        title_map = {
            "stop_loss": f"止损触发 {symbol}",
            "take_profit": f"止盈触发 {symbol}",
            "trailing_stop": f"移动止损 {symbol}",
            "circuit_breaker": "组合熔断",
        }
        return self.send(
            title=title_map.get(risk_type, f"风控告警 {symbol}"),
            text="",
            event_type=event,
            template=template,
            variables=variables,
            dedup_minutes=5,
        )

    def send_system_alert(
        self,
        alert_type: str,
        error: str = "",
        crash_count: int = 0,
        reason: str = "",
        downtime: str = "",
        **extra: Any,
    ) -> bool:
        """发送系统异常告警。"""
        template_map = {
            "crash": "system_crash",
            "restart": "system_restart",
            "cooldown": "system_cooldown",
        }
        template = template_map.get(alert_type, "system_crash")
        event = f"system_{alert_type}"

        variables = {
            "error": error,
            "crash_count": str(crash_count),
            "reason": reason,
            "downtime": downtime,
            "status": "冷却中" if alert_type == "cooldown" else "异常",
            "cooldown_minutes": str(extra.get("cooldown_minutes", 30)),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **extra,
        }
        return self.send(
            title=f"系统{alert_type}",
            text="",
            event_type=event,
            template=template,
            variables=variables,
            dedup_minutes=10,
        )

    def send_daily_summary(
        self,
        symbol: str = "",
        date: str = "",
        day_trades: int = 0,
        day_pnl: float = 0,
        total_pnl: float = 0,
        win_rate: str = "",
        position: str = "",
        **extra: Any,
    ) -> bool:
        """发送每日交易总结。"""
        variables = {
            "symbol": symbol,
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "day_trades": str(day_trades),
            "day_pnl": f"${day_pnl:,.2f}",
            "total_pnl": f"${total_pnl:,.2f}",
            "win_rate": win_rate or "-",
            "position": position or "空仓",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **extra,
        }
        return self.send(
            title=f"每日总结 {variables['date']}",
            text="",
            event_type="daily_summary",
            template="daily_summary",
            variables=variables,
            dedup_minutes=60,
        )

    def send_custom(
        self,
        title: str,
        text: str,
        level: AlertLevel = AlertLevel.INFO,
        dedup_minutes: int = 0,
        **variables: Any,
    ) -> bool:
        """发送自定义告警。"""
        if variables:
            text = render(text, variables)
        return self.send(
            title=title,
            text=text,
            event_type="custom",
            level=level,
            dedup_minutes=dedup_minutes,
        )

    # ── 测试接口 ────────────────────────────────────────────────

    def test_channel(self, channel_name: str = "") -> dict[str, bool]:
        """测试所有或指定通道的连通性。

        Returns:
            {通道名: 是否成功}
        """
        results: dict[str, bool] = {}
        test_title = "告警系统测试"
        test_text = "这是一条来自量化交易系统的测试告警。\n时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for ch in self.channels:
            if channel_name and ch.name != channel_name:
                continue
            ok = ch.send(test_text, title=test_title, level="INFO")
            results[ch.name] = ok

        return results

    # ── 规则引擎接口 ────────────────────────────────────────────

    def evaluate_and_send(
        self,
        event_type: str,
        data: dict[str, Any],
        default_title: str = "",
        default_text: str = "",
    ) -> list[bool]:
        """评估规则并发送触发的告警。

        Returns:
            每个触发规则的发送结果列表。
        """
        # 先评估自定义规则
        triggered = self.rules.evaluate(event_type, data)
        results: list[bool] = []

        for rule in triggered:
            text = render(rule.message, data)
            ok = self.send(
                title=default_title or f"规则触发: {rule.name}",
                text=text,
                event_type=event_type,
                level=rule.level,
                dedup_minutes=rule.cooldown_minutes,
            )
            results.append(ok)

        return results

    # ── 历史记录 ────────────────────────────────────────────────

    def get_history(
        self,
        limit: int = 50,
        event_type: str = "",
        level: str = "",
    ) -> list[dict[str, Any]]:
        """获取告警历史。"""
        records = self._history
        if event_type:
            records = [r for r in records if r.event_type == event_type]
        if level:
            records = [r for r in records if r.level == level]
        return [r.to_dict() for r in records[-limit:]]

    def clear_history(self) -> int:
        """清空历史并返回清除条数。"""
        count = len(self._history)
        self._history.clear()
        self._save_history()
        return count

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _make_dedup_key(event_type: str, title: str, text: str, level: str) -> str:
        """生成去重 key（同事件类型+标题+级别 = 相同告警）。"""
        raw = f"{event_type}:{title}:{level}"
        # 仅作去重指纹, 非安全用途
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]

    def _is_duplicate(self, key: str, minutes: int) -> bool:
        with self._dedup_lock:
            last = self._dedup.get(key, 0)
            return (time.time() - last) < minutes * 60

    def _update_dedup(self, key: str) -> None:
        with self._dedup_lock:
            self._dedup[key] = time.time()

    def _add_history(self, record: AlertRecord) -> None:
        self._history.append(record)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history :]
        # 异步写盘（不阻塞）
        try:
            self._save_history()
        except Exception:
            pass

    def _load_history(self) -> None:
        if self.history_path.exists():
            try:
                data = json.loads(self.history_path.read_text(encoding="utf-8"))
                self._history = [AlertRecord(**item) for item in data[-self.max_history :]]
            except Exception:
                self._history = []

    def _save_history(self) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self._history[-self.max_history :]]
        self.history_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
