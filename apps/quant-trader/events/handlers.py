"""Predefined event handlers for the quant-trader event-driven architecture.

Provides ready-to-use handlers that connect the event bus to the existing
trading system components (broker, risk, notifications, logging, journal).

Handlers are organized by concern:
- LoggingHandler      — log all events to file/console
- RiskHandler         — react to risk events (halt trading, notify)
- OrderHandler        — execute orders via broker
- JournalHandler      — persist trade decisions to CSV
- NotificationHandler — push alerts via webhook
- ScannerHandler      — publish scanner results as events
- SelfLearningHandler — track prediction accuracy for self-learning

Usage:
    from quanttrader.events.bus import EventBus
    from quanttrader.events.handlers import (
        LoggingHandler, RiskHandler, JournalHandler,
    )

    bus = EventBus()
    bus.subscribe("*", LoggingHandler().handle)
    bus.subscribe("risk.*", RiskHandler(notifier=my_notifier).handle)
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .types import (
    Event,
    MarketEvent,
    NewsEvent,
    OrderEvent,
    RiskEvent,
    SignalEvent,
)

logger = logging.getLogger("quanttrader.events.handlers")


# ═══════════════════════════════════════════════════════════════════════════
# Logging Handler
# ═══════════════════════════════════════════════════════════════════════════


class LoggingHandler:
    """Logs every event to the quanttrader.events logger.

    Formats differently by event type for readability.
    """

    def __init__(self, level: int = logging.DEBUG):
        self.level = level
        self._log = logging.getLogger("quanttrader.events")

    def handle(self, event: Event) -> None:
        """Log an event with type-specific formatting."""
        if isinstance(event, RiskEvent):
            self._log.log(
                self.level,
                "[RISK] %s | %s | equity=$%.2f | %s",
                event.risk_type,
                event.message,
                event.equity,
                "HALT" if event.halt_until > 0 else "ACTIVE",
            )
        elif isinstance(event, OrderEvent):
            self._log.log(
                self.level,
                "[ORDER] %s %s | $%.2f x %.0f | status=%s | reason=%s",
                event.side,
                event.symbol,
                event.price,
                event.notional,
                event.status,
                event.reason,
            )
        elif isinstance(event, SignalEvent):
            self._log.log(
                self.level,
                "[SIGNAL] %s %s | conf=%.0f%% | %s",
                event.label,
                event.symbol,
                event.confidence * 100,
                event.reason[:80],
            )
        elif isinstance(event, MarketEvent):
            self._log.log(
                self.level,
                "[MARKET] %s @ %.2f | vol=%.0f",
                event.symbol,
                event.price,
                event.volume,
            )
        elif isinstance(event, NewsEvent):
            self._log.log(
                self.level,
                "[NEWS] %s | %d articles | sentiment=%s(%.2f)",
                event.symbol,
                event.article_count,
                event.sentiment,
                event.score,
            )
        else:
            self._log.log(self.level, "[%s] %s", event.event_type, event.data)


# ═══════════════════════════════════════════════════════════════════════════
# Risk Handler
# ═══════════════════════════════════════════════════════════════════════════


class RiskHandler:
    """React to risk events by halting trading and sending notifications.

    Integrates with the existing daemon's halt mechanism and Notifier.
    """

    def __init__(
        self,
        halt_callback: Callable[[float, str], None] | None = None,
        sell_callback: Callable[[str], None] | None = None,
        notify_callback: Callable[[str, str], None] | None = None,
    ):
        """
        Args:
            halt_callback:  Called with (halt_until_ts, reason) to pause trading.
            sell_callback:  Called with (symbol) to liquidate a position.
            notify_callback: Called with (message, level) for webhook alerts.
        """
        self.halt_callback = halt_callback
        self.sell_callback = sell_callback
        self.notify_callback = notify_callback

    def handle(self, event: Event) -> None:
        """Process a RiskEvent."""
        if not isinstance(event, RiskEvent):
            return

        logger.critical("RISK TRIGGER: %s — %s", event.risk_type, event.message)

        # Liquidate if symbol-specific risk (stop-loss, trailing-stop)
        if event.symbol and self.sell_callback:
            self.sell_callback(event.symbol)

        # Halt trading if halt_until is set
        if event.halt_until > 0 and self.halt_callback:
            self.halt_callback(event.halt_until, event.risk_type)

        # Notify
        if self.notify_callback:
            level = "critical" if event.risk_type in ("max_drawdown", "daily_loss", "consecutive_losses") else "trade"
            self.notify_callback(f"RISK: {event.risk_type}\n{event.message}", level)


# ═══════════════════════════════════════════════════════════════════════════
# Order Handler
# ═══════════════════════════════════════════════════════════════════════════


class OrderHandler:
    """Execute OrderEvents through a broker interface.

    Translates OrderEvent into broker.buy() / broker.sell_all() calls
    and publishes fill events back to the bus.
    """

    def __init__(
        self,
        broker: Any = None,
        publish_callback: Callable[[Event], None] | None = None,
    ):
        """
        Args:
            broker:          Broker instance with buy/sell_all methods.
            publish_callback: Callback to publish fill events back to bus.
        """
        self.broker = broker
        self.publish_callback = publish_callback

    def handle(self, event: Event) -> None:
        """Execute an OrderEvent."""
        if not isinstance(event, OrderEvent):
            return
        if event.status != "pending":
            return  # Only execute pending orders

        if not self.broker:
            logger.warning("OrderEvent received but no broker configured")
            return

        try:
            if event.side == "BUY":
                from ..broker.base import auto_buy_enabled

                if not auto_buy_enabled():
                    logger.warning(
                        "自动代买已关闭, 跳过 BUY %s (设 QT_AUTO_TRADE=1 可恢复)", event.symbol
                    )
                    if self.publish_callback:
                        self.publish_callback(
                            OrderEvent(
                                symbol=event.symbol,
                                side="BUY",
                                notional=event.notional,
                                price=event.price,
                                status="rejected",
                                reason="auto_buy_disabled",
                            )
                        )
                    return
                if event.notional > 0:
                    self.broker.buy(event.symbol, event.notional)
                logger.info("ORDER EXECUTED: BUY %s $%.2f", event.symbol, event.notional)
            elif event.side == "SELL":
                self.broker.sell_all(event.symbol)
                logger.info("ORDER EXECUTED: SELL ALL %s", event.symbol)

            # Publish fill event
            if self.publish_callback:
                fill = OrderEvent(
                    symbol=event.symbol,
                    side=event.side,
                    notional=event.notional,
                    price=event.price,
                    status="filled",
                    reason=event.reason,
                )
                self.publish_callback(fill)

        except Exception as e:
            logger.error("Order execution failed: %s", e)
            if self.publish_callback:
                reject = OrderEvent(
                    symbol=event.symbol,
                    side=event.side,
                    notional=event.notional,
                    status="rejected",
                    reason=str(e),
                )
                self.publish_callback(reject)


# ═══════════════════════════════════════════════════════════════════════════
# Journal Handler
# ═══════════════════════════════════════════════════════════════════════════


class JournalHandler:
    """Persist events to CSV journal files.

    Maintains separate CSV files for decisions and trades, matching
    the existing daemon's journal format.
    """

    def __init__(self, journal_dir: str = "logs"):
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self._init_files()

    def _init_files(self) -> None:
        """Create CSV headers if files don't exist."""
        today = datetime.now().strftime("%Y-%m-%d")
        self.decision_path = self.journal_dir / f"decisions_{today}.csv"
        self.trade_path = self.journal_dir / f"trades_{today}.csv"

        if not self.decision_path.exists():
            with open(self.decision_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    [
                        "ts",
                        "event_type",
                        "symbol",
                        "signal",
                        "label",
                        "confidence",
                        "reason",
                        "equity",
                        "action",
                    ]
                )

        if not self.trade_path.exists():
            with open(self.trade_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    [
                        "ts",
                        "symbol",
                        "side",
                        "price",
                        "notional",
                        "status",
                        "reason",
                    ]
                )

    def handle(self, event: Event) -> None:
        """Write an event to the appropriate journal file."""
        if isinstance(event, SignalEvent):
            self._append_csv(
                self.decision_path,
                [
                    event.timestamp,
                    event.event_type,
                    event.symbol,
                    event.signal,
                    event.label,
                    round(event.confidence, 4),
                    event.reason[:200],
                    "",
                    "",
                ],
            )
        elif isinstance(event, OrderEvent):
            self._append_csv(
                self.trade_path,
                [
                    event.timestamp,
                    event.symbol,
                    event.side,
                    event.price,
                    event.notional,
                    event.status,
                    event.reason,
                ],
            )
        elif isinstance(event, RiskEvent):
            self._append_csv(
                self.decision_path,
                [
                    event.timestamp,
                    event.event_type,
                    event.symbol,
                    "",
                    "",
                    "",
                    event.message[:200],
                    round(event.equity, 2),
                    event.risk_type,
                ],
            )

    @staticmethod
    def _append_csv(path: Path, row: list) -> None:
        """Append a row to a CSV file."""
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)


# ═══════════════════════════════════════════════════════════════════════════
# Notification Handler
# ═══════════════════════════════════════════════════════════════════════════


class NotificationHandler:
    """Push event notifications via webhook.

    Formats events into human-readable messages for WeChat Work,
    DingTalk, Telegram, or generic webhooks.
    """

    def __init__(
        self,
        notifier: Any = None,
        levels: list[str] | None = None,
    ):
        """
        Args:
            notifier: Notifier instance with send(text, level) method.
            levels:   Event levels to notify on. Default: ["critical", "trade"].
        """
        self.notifier = notifier
        self.levels = levels or ["critical", "trade"]

    def handle(self, event: Event) -> None:
        """Send notification for qualifying events."""
        if not self.notifier:
            return

        if isinstance(event, RiskEvent):
            level = "critical"
            text = f"RISK: {event.risk_type}\n{event.message}"
        elif isinstance(event, OrderEvent):
            if event.status == "rejected":
                level = "critical"
            else:
                level = "trade"
            text = f"ORDER: {event.side} {event.symbol} ${event.notional:,.0f} | {event.status}"
        elif isinstance(event, SignalEvent):
            level = "trade"
            text = f"SIGNAL: {event.label} {event.symbol} conf={event.confidence:.0%}"
        else:
            return

        if level in self.levels:
            try:
                self.notifier.send(text, level)
            except Exception as e:
                logger.warning("Notification failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# Self-Learning Handler
# ═══════════════════════════════════════════════════════════════════════════


class SelfLearningHandler:
    """Track prediction accuracy for the self-learning loop.

    Records signal events and matches them against subsequent price
    movements to compute accuracy metrics.
    """

    def __init__(self, tracker_path: str = "logs/tracker.json"):
        self.tracker_path = Path(tracker_path)
        self._pending: dict[str, dict] = {}  # symbol -> pending prediction

    def handle(self, event: Event) -> None:
        """Record a signal for later accuracy verification."""
        if not isinstance(event, SignalEvent):
            return

        if event.signal == 0:
            return  # Don't track HOLD signals

        self._pending[event.symbol] = {
            "timestamp": event.timestamp,
            "symbol": event.symbol,
            "signal": event.signal,
            "label": event.label,
            "confidence": event.confidence,
            "target_price": event.target_price,
        }

    def verify(self, symbol: str, actual_price: float) -> dict[str, Any] | None:
        """Verify a pending prediction against actual price.

        Args:
            symbol:       Ticker symbol.
            actual_price: Actual price at verification time.

        Returns:
            Verification result dict, or None if no pending prediction.
        """
        pending = self._pending.pop(symbol, None)
        if not pending:
            return None

        signal = pending["signal"]
        target = pending.get("target_price", 0)

        # Check direction correctness
        if signal == 1:  # BUY prediction
            correct = actual_price > target if target > 0 else True
        elif signal == -1:  # SELL prediction
            correct = actual_price < target if target > 0 else True
        else:
            correct = None

        result = {
            **pending,
            "actual_price": actual_price,
            "correct": correct,
            "verified_at": datetime.now(UTC).isoformat(),
        }

        self._append_tracker(result)
        return result

    def _append_tracker(self, result: dict) -> None:
        """Append a verification result to the tracker file."""
        try:
            self.tracker_path.parent.mkdir(parents=True, exist_ok=True)
            entries: list[dict] = []
            if self.tracker_path.exists():
                entries = json.loads(self.tracker_path.read_text(encoding="utf-8"))
            entries.append(result)
            self.tracker_path.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Tracker write failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# Handler Registry
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class HandlerRegistry:
    """Convenience registry that wires up all standard handlers to a bus.

    Usage:
        registry = HandlerRegistry(broker=my_broker, notifier=my_notifier)
        registry.attach_all(bus)
    """

    broker: Any = None
    notifier: Any = None
    journal_dir: str = "logs"
    tracker_path: str = "logs/tracker.json"

    def attach_all(self, bus: Any) -> None:
        """Subscribe all standard handlers to the event bus.

        Args:
            bus: EventBus instance.
        """
        # Logging — all events
        bus.subscribe("*", LoggingHandler().handle)

        # Risk
        risk = RiskHandler(
            halt_callback=lambda until, reason: setattr(bus, "_halt_until", until),
            sell_callback=lambda symbol: logger.info("SELL signal for %s", symbol),
            notify_callback=self.notifier.send if self.notifier else None,
        )
        bus.subscribe("risk.*", risk.handle)

        # Orders
        order = OrderHandler(
            broker=self.broker,
            publish_callback=bus.publish,
        )
        bus.subscribe("order.*", order.handle)

        # Journal
        journal = JournalHandler(journal_dir=self.journal_dir)
        bus.subscribe("*", journal.handle)

        # Notifications
        if self.notifier:
            notify = NotificationHandler(notifier=self.notifier)
            bus.subscribe("risk.*", notify.handle)
            bus.subscribe("order.*", notify.handle)
            bus.subscribe("signal.*", notify.handle)

        logger.info("HandlerRegistry: all handlers attached")
