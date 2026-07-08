"""Event types for the quant-trader event-driven architecture.

Defines the base Event class and all concrete event types used throughout
the system. Every event carries an immutable ID, timestamp, priority, and
a typed data payload.

Event hierarchy:
    Event (base)
    ├── MarketEvent      — price/volume bar updates
    ├── SignalEvent       — LLM or strategy signals (BUY/SELL/HOLD)
    ├── OrderEvent        — order execution requests and fills
    ├── RiskEvent         — risk triggers (stop-loss, circuit breaker, drawdown)
    └── NewsEvent         — news aggregation and sentiment updates

Usage:
    from quanttrader.events.types import MarketEvent, SignalEvent, Priority

    evt = MarketEvent(symbol="AAPL", price=150.0, volume=1_000_000)
    print(evt.priority)   # Priority.LOW
    print(evt.to_dict())  # serializable dict
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# Priority levels
# ═══════════════════════════════════════════════════════════════════════════


class Priority(IntEnum):
    """Event priority levels. Lower numeric value = higher priority.

    Used by PriorityEventQueue to determine processing order.
    Risk events always preempt market data events.
    """

    CRITICAL = 0  # Risk events: stop-loss, circuit breaker, drawdown halt
    HIGH = 10  # Order events: execution requests, fills
    NORMAL = 20  # Signal events: LLM decisions, strategy signals
    LOW = 30  # Market events: price bars, news updates


# ═══════════════════════════════════════════════════════════════════════════
# Base Event
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Event:
    """Base event class. All events are immutable after creation.

    Attributes:
        event_id:    Unique identifier (UUID4).
        event_type:  String tag for routing (e.g. "market.price", "risk.stop_loss").
        timestamp:   UTC creation time.
        priority:    Processing priority level.
        source:      Component that emitted this event (e.g. "daemon", "scanner").
        data:        Payload dict — structure varies by event type.
    """

    event_type: str
    priority: Priority = Priority.NORMAL
    source: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        d = asdict(self)
        d["priority"] = self.priority.value
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Deserialize from dict. Subclasses should override for typed access."""
        data = dict(data)
        if "priority" in data and isinstance(data["priority"], int):
            data["priority"] = Priority(data["priority"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════════════════
# Concrete event types
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MarketEvent(Event):
    """Price/volume bar update from data feed or broker.

    Attributes:
        symbol:  Ticker symbol (e.g. "AAPL", "sh600000").
        price:   Latest close price.
        volume:  Bar volume.
        open:    Bar open price.
        high:    Bar high price.
        low:     Bar low price.
        interval: Bar interval (e.g. "1d", "1h").
    """

    event_type: str = "market.price"
    priority: Priority = Priority.LOW
    symbol: str = ""
    price: float = 0.0
    volume: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    interval: str = "1d"

    def __post_init__(self) -> None:
        # Populate data dict for generic consumers
        object.__setattr__(
            self,
            "data",
            {
                "symbol": self.symbol,
                "price": self.price,
                "volume": self.volume,
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "interval": self.interval,
            },
        )


@dataclass(frozen=True)
class SignalEvent(Event):
    """Trading signal from LLM or strategy.

    Attributes:
        symbol:     Ticker symbol.
        signal:     Direction: 1 (BUY), 0 (HOLD), -1 (SELL).
        confidence: Signal confidence 0.0-1.0.
        reason:     Human-readable reason string.
        label:      Text label ("BUY", "HOLD", "SELL").
        provider:   LLM provider name (e.g. "deepseek").
        model:      LLM model name.
        target_price: Price target from LLM.
        stop_loss:   Suggested stop-loss price.
        take_profit: Suggested take-profit price.
    """

    event_type: str = "signal.llm"
    priority: Priority = Priority.NORMAL
    symbol: str = ""
    signal: int = 0
    confidence: float = 0.0
    reason: str = ""
    label: str = "HOLD"
    provider: str = ""
    model: str = ""
    target_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data",
            {
                "symbol": self.symbol,
                "signal": self.signal,
                "confidence": self.confidence,
                "reason": self.reason,
                "label": self.label,
                "provider": self.provider,
                "model": self.model,
                "target_price": self.target_price,
                "stop_loss": self.stop_loss,
                "take_profit": self.take_profit,
            },
        )


@dataclass(frozen=True)
class OrderEvent(Event):
    """Order execution request or fill notification.

    Attributes:
        symbol:    Ticker symbol.
        side:      "BUY" or "SELL".
        quantity:  Number of shares (0 if using notional).
        notional:  Dollar amount for the order.
        price:     Execution price (0 if pending).
        status:    "pending", "filled", "rejected", "cancelled".
        order_id:  Broker-assigned order ID.
        reason:    Why this order was placed (e.g. "signal", "stop_loss").
    """

    event_type: str = "order.execute"
    priority: Priority = Priority.HIGH
    symbol: str = ""
    side: str = ""  # BUY / SELL
    quantity: float = 0.0
    notional: float = 0.0
    price: float = 0.0
    status: str = "pending"  # pending / filled / rejected / cancelled
    order_id: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data",
            {
                "symbol": self.symbol,
                "side": self.side,
                "quantity": self.quantity,
                "notional": self.notional,
                "price": self.price,
                "status": self.status,
                "order_id": self.order_id,
                "reason": self.reason,
            },
        )


@dataclass(frozen=True)
class RiskEvent(Event):
    """Risk management trigger — stop-loss, circuit breaker, drawdown halt.

    Attributes:
        symbol:      Ticker symbol (empty for portfolio-level events).
        risk_type:   Type of risk trigger
                     ("stop_loss", "take_profit", "trailing_stop",
                      "max_drawdown", "daily_loss", "daily_gain",
                      "consecutive_losses", "max_trades").
        message:     Human-readable description.
        equity:      Current equity at time of trigger.
        peak_equity: Peak equity for drawdown calculation.
        day_pnl_pct: Day P&L percentage.
        halt_until:  Unix timestamp until trading is halted (0 = not halted).
    """

    event_type: str = "risk.trigger"
    priority: Priority = Priority.CRITICAL
    symbol: str = ""
    risk_type: str = ""
    message: str = ""
    equity: float = 0.0
    peak_equity: float = 0.0
    day_pnl_pct: float = 0.0
    halt_until: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data",
            {
                "symbol": self.symbol,
                "risk_type": self.risk_type,
                "message": self.message,
                "equity": self.equity,
                "peak_equity": self.peak_equity,
                "day_pnl_pct": self.day_pnl_pct,
                "halt_until": self.halt_until,
            },
        )


@dataclass(frozen=True)
class NewsEvent(Event):
    """News aggregation result with sentiment analysis.

    Attributes:
        symbol:       Ticker symbol.
        headline:     News headline or summary.
        sentiment:    Sentiment label ("positive", "negative", "neutral").
        score:        Sentiment score (-1.0 to 1.0).
        source:       News source name.
        article_count: Number of articles aggregated.
        news_text:    Full text for LLM context.
    """

    event_type: str = "news.update"
    priority: Priority = Priority.LOW
    symbol: str = ""
    headline: str = ""
    sentiment: str = "neutral"
    score: float = 0.0
    article_count: int = 0
    news_text: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data",
            {
                "symbol": self.symbol,
                "headline": self.headline,
                "sentiment": self.sentiment,
                "score": self.score,
                "article_count": self.article_count,
                "news_text": self.news_text,
            },
        )


# ═══════════════════════════════════════════════════════════════════════════
# Event registry — type string → class mapping
# ═══════════════════════════════════════════════════════════════════════════

EVENT_REGISTRY: dict[str, type[Event]] = {
    "market.price": MarketEvent,
    "signal.llm": SignalEvent,
    "order.execute": OrderEvent,
    "risk.trigger": RiskEvent,
    "news.update": NewsEvent,
}


def deserialize_event(data: dict[str, Any]) -> Event:
    """Deserialize a dict into the correct Event subclass.

    Looks up the event_type in EVENT_REGISTRY. Falls back to base Event
    if the type is unknown.

    Args:
        data: Dict from Event.to_dict() or JSON file.

    Returns:
        Typed Event instance.
    """
    event_type = data.get("event_type", "")
    cls = EVENT_REGISTRY.get(event_type, Event)
    # Filter to known fields
    known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
    if "priority" in known and isinstance(known["priority"], int):
        known["priority"] = Priority(known["priority"])
    return cls(**known)
