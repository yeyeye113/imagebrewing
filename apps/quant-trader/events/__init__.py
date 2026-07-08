"""QuantTrader Event-Driven Architecture.

A publish/subscribe event system that decouples trading components:
data feeds, LLM strategies, risk management, order execution, and
notifications communicate through typed events on a central bus.

Quick start:
    from quanttrader.events import EventBus, RiskEvent, SignalEvent

    bus = EventBus()

    @bus.on("risk.*")
    def on_risk(event: RiskEvent):
        print(f"Risk: {event.risk_type}")

    bus.publish(RiskEvent(risk_type="stop_loss", message="Hit stop"))
    bus.start()  # async mode

Architecture:
    ┌─────────┐   publish    ┌─────────┐   dispatch   ┌───────────┐
    │ Scanner  │──────────→  │         │─────────────→│ Handlers  │
    │ LLM      │──────────→  │ EventBus│─────────────→│ Risk      │
    │ DataFeed │──────────→  │         │─────────────→│ Journal   │
    │ Broker   │──────────→  │         │─────────────→│ Notify    │
    └─────────┘              └─────────┘              └───────────┘
                                ↑  ↓
                          PriorityEventQueue
                          (CRITICAL > HIGH > NORMAL > LOW)

Event types:
    MarketEvent   (Priority.LOW)      — price/volume updates
    SignalEvent   (Priority.NORMAL)   — LLM/strategy signals
    OrderEvent    (Priority.HIGH)     — order execution
    RiskEvent     (Priority.CRITICAL) — risk triggers, circuit breakers
    NewsEvent     (Priority.LOW)      — news sentiment updates
"""

from .bus import EventBus, get_bus, reset_bus
from .handlers import (
    HandlerRegistry,
    JournalHandler,
    LoggingHandler,
    NotificationHandler,
    OrderHandler,
    RiskHandler,
    SelfLearningHandler,
)
from .queue import PriorityEventQueue
from .types import (
    EVENT_REGISTRY,
    Event,
    MarketEvent,
    NewsEvent,
    OrderEvent,
    Priority,
    RiskEvent,
    SignalEvent,
    deserialize_event,
)

__all__ = [
    "EVENT_REGISTRY",
    # Core types
    "Event",
    # Bus
    "EventBus",
    "HandlerRegistry",
    "JournalHandler",
    # Handlers
    "LoggingHandler",
    "MarketEvent",
    "NewsEvent",
    "NotificationHandler",
    "OrderEvent",
    "OrderHandler",
    "Priority",
    # Queue
    "PriorityEventQueue",
    "RiskEvent",
    "RiskHandler",
    "SelfLearningHandler",
    "SignalEvent",
    "deserialize_event",
    "get_bus",
    "reset_bus",
]
