"""Event bus for the quant-trader event-driven architecture.

Implements a publish/subscribe event bus with:
- Topic-based routing (subscribe to event types or wildcards)
- Synchronous and asynchronous handler dispatch
- Priority queue integration
- Event history for replay
- Optional JSON-file persistence
- Thread-safe operation

Usage:
    from quanttrader.events.bus import EventBus
    from quanttrader.events.types import RiskEvent, SignalEvent

    bus = EventBus()

    # Subscribe with decorator
    @bus.on("risk.*")
    def handle_risk(event: RiskEvent):
        print(f"Risk: {event.risk_type}")

    # Or subscribe directly
    bus.subscribe("signal.*", my_handler)

    # Publish
    bus.publish(RiskEvent(risk_type="stop_loss", message="Hit stop"))
    bus.publish(SignalEvent(symbol="AAPL", signal=1, confidence=0.8))

    # Async processing
    bus.start()   # spawns worker thread
    bus.stop()    # graceful shutdown
"""

from __future__ import annotations

import fnmatch
import json
import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .queue import PriorityEventQueue
from .types import Event, Priority, deserialize_event

logger = logging.getLogger("quanttrader.events.bus")

# Handler type: takes an Event, returns nothing
EventHandler = Callable[[Event], None]


@dataclass
class EventBus:
    """Central event bus with pub/sub, priority queue, and persistence.

    Components publish events via publish(). Subscribers register handlers
    for specific event types or wildcard patterns (e.g. "risk.*").

    When started (start()), a worker thread drains the priority queue and
    dispatches events to matching handlers.

    Attributes:
        _subscriptions:  event_type pattern → list of handlers.
        _queue:          Priority event queue for async processing.
        _history:        Ring buffer of recent events for replay.
        _history_max:    Maximum events to keep in history.
        _persist_dir:    Directory for event persistence (empty = disabled).
        _worker:         Background worker thread.
        _running:        Worker thread control flag.
        _lock:           Subscription mutation lock.
        _published:      Total events published counter.
        _dispatched:     Total events dispatched counter.
        _errors:         Total handler errors counter.
    """

    _subscriptions: dict[str, list[EventHandler]] = field(default_factory=lambda: defaultdict(list))
    _queue: PriorityEventQueue = field(default_factory=PriorityEventQueue)
    _history: list[Event] = field(default_factory=list)
    _history_max: int = 1000
    _persist_dir: str = ""
    _worker: threading.Thread | None = None
    _running: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _published: int = 0
    _dispatched: int = 0
    _errors: int = 0
    _sync_mode: bool = False  # if True, publish() dispatches immediately

    # ── Subscription ─────────────────────────────────────────────────

    def subscribe(self, pattern: str, handler: EventHandler) -> None:
        """Subscribe a handler to events matching a pattern.

        Args:
            pattern: Event type pattern. Supports glob-style wildcards:
                     "risk.*" matches "risk.stop_loss", "risk.max_drawdown", etc.
                     "*" matches everything.
                     Exact match: "signal.llm".
            handler: Callable that takes an Event.
        """
        with self._lock:
            self._subscriptions[pattern].append(handler)
        logger.debug("Subscribed %s to pattern '%s'", handler.__name__, pattern)

    def unsubscribe(self, pattern: str, handler: EventHandler) -> bool:
        """Remove a handler subscription. Returns True if found."""
        with self._lock:
            handlers = self._subscriptions.get(pattern, [])
            if handler in handlers:
                handlers.remove(handler)
                return True
        return False

    def on(self, pattern: str) -> Callable:
        """Decorator to subscribe a function to an event pattern.

        Usage:
            @bus.on("risk.*")
            def handle_risk(event):
                print(event.risk_type)
        """

        def decorator(fn: EventHandler) -> EventHandler:
            self.subscribe(pattern, fn)
            return fn

        return decorator

    def clear_subscriptions(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._subscriptions.clear()

    # ── Publishing ───────────────────────────────────────────────────

    def publish(self, event: Event) -> None:
        """Publish an event to the bus.

        In sync mode, dispatches immediately. In async mode, enqueues
        for the worker thread to process.

        Args:
            event: The Event to publish.
        """
        self._published += 1

        # Record to history
        self._record(event)

        # Persist if configured
        if self._persist_dir:
            self._persist(event)

        if self._sync_mode:
            self._dispatch(event)
        else:
            self._queue.put(event)

    def publish_many(self, events: list[Event]) -> None:
        """Publish multiple events."""
        for event in events:
            self.publish(event)

    # ── Dispatch ─────────────────────────────────────────────────────

    def _dispatch(self, event: Event) -> None:
        """Route an event to all matching handlers."""
        with self._lock:
            # Collect matching handlers
            matched: list[EventHandler] = []
            for pattern, handlers in self._subscriptions.items():
                if self._matches(pattern, event.event_type):
                    matched.extend(handlers)

        for handler in matched:
            try:
                handler(event)
                self._dispatched += 1
            except Exception as e:
                self._errors += 1
                logger.error(
                    "Handler %s error on %s: %s",
                    handler.__name__,
                    event.event_type,
                    e,
                    exc_info=True,
                )

    @staticmethod
    def _matches(pattern: str, event_type: str) -> bool:
        """Check if an event type matches a subscription pattern.

        Supports:
            "*"           — matches everything
            "risk.*"      — matches "risk.stop_loss", "risk.max_drawdown", etc.
            "signal.llm"  — exact match only
        """
        if pattern == "*":
            return True
        return fnmatch.fnmatch(event_type, pattern)

    # ── Async worker ─────────────────────────────────────────────────

    def start(self, worker_count: int = 1) -> None:
        """Start the async event processing worker thread(s).

        Args:
            worker_count: Number of worker threads (default 1).
        """
        if self._running:
            logger.warning("EventBus already running")
            return

        self._running = True
        self._sync_mode = False

        for i in range(worker_count):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"eventbus-worker-{i}",
                daemon=True,
            )
            t.start()
            if self._worker is None:
                self._worker = t

        logger.info("EventBus started with %d worker(s)", worker_count)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the worker thread(s) gracefully.

        Args:
            timeout: Max seconds to wait for workers to finish.
        """
        self._running = False
        # Put a sentinel to wake blocked workers
        try:
            self._queue.put(Event(event_type="__shutdown__", priority=Priority.LOW))
        except Exception:
            pass

        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=timeout)
        self._worker = None
        logger.info(
            "EventBus stopped. Published=%d Dispatched=%d Errors=%d", self._published, self._dispatched, self._errors
        )

    def _worker_loop(self) -> None:
        """Worker thread: drain queue and dispatch events."""
        while self._running:
            try:
                event = self._queue.get(block=True, timeout=1.0)
                if event.event_type == "__shutdown__":
                    continue
                self._dispatch(event)
            except (TimeoutError, RuntimeError):
                # TimeoutError: no event within timeout (normal)
                # RuntimeError: empty queue race condition (normal during shutdown)
                continue
            except Exception as e:
                logger.error("Worker error: %s", e, exc_info=True)

    @property
    def is_running(self) -> bool:
        """True if the worker thread is active."""
        return self._running

    # ── History & Replay ─────────────────────────────────────────────

    def _record(self, event: Event) -> None:
        """Add event to the history ring buffer."""
        self._history.append(event)
        if len(self._history) > self._history_max:
            self._history = self._history[-self._history_max :]

    def get_history(
        self,
        event_type: str = "",
        limit: int = 100,
        since: str = "",
    ) -> list[Event]:
        """Retrieve events from history.

        Args:
            event_type: Filter by type pattern (e.g. "risk.*"). Empty = all.
            limit:      Maximum events to return.
            since:      ISO timestamp — only return events after this time.

        Returns:
            List of matching events, newest first.
        """
        events = self._history
        if event_type:
            events = [e for e in events if self._matches(event_type, e.event_type)]
        if since:
            events = [e for e in events if e.timestamp > since]
        return events[-limit:]

    def replay(
        self,
        handler: EventHandler,
        event_type: str = "",
        limit: int = 0,
        since: str = "",
    ) -> int:
        """Replay historical events through a handler.

        Useful for backtesting or catching up a new subscriber.

        Args:
            handler:    Handler to receive replayed events.
            event_type: Filter pattern. Empty = all.
            limit:      Max events to replay. 0 = all.
            since:      Only replay events after this ISO timestamp.

        Returns:
            Number of events replayed.
        """
        events = self.get_history(event_type=event_type, limit=limit or 9999, since=since)
        count = 0
        for event in reversed(events):  # oldest first for replay
            try:
                handler(event)
                count += 1
            except Exception as e:
                logger.error("Replay handler error: %s", e)
        return count

    def clear_history(self) -> int:
        """Clear event history. Returns count of cleared events."""
        count = len(self._history)
        self._history.clear()
        return count

    # ── Persistence ──────────────────────────────────────────────────

    def enable_persistence(self, directory: str) -> None:
        """Enable event persistence to JSON files.

        Events are appended to daily NDJSON files (one JSON object per line).

        Args:
            directory: Path to persistence directory.
        """
        self._persist_dir = directory
        Path(directory).mkdir(parents=True, exist_ok=True)
        logger.info("Event persistence enabled: %s", directory)

    def _persist(self, event: Event) -> None:
        """Append event to today's persistence file."""
        try:
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            path = Path(self._persist_dir) / f"events_{today}.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
        except Exception as e:
            logger.warning("Persist failed: %s", e)

    def load_persisted(
        self,
        date: str = "",
        event_type: str = "",
        limit: int = 0,
    ) -> list[Event]:
        """Load events from persistence files.

        Args:
            date:       Date string "YYYY-MM-DD". Empty = today.
            event_type: Filter pattern. Empty = all.
            limit:      Max events. 0 = all.

        Returns:
            List of deserialized events.
        """
        if not self._persist_dir:
            return []

        target_date = date or datetime.now(UTC).strftime("%Y-%m-%d")
        path = Path(self._persist_dir) / f"events_{target_date}.jsonl"
        if not path.exists():
            return []

        events: list[Event] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = deserialize_event(data)
                    if event_type and not self._matches(event_type, event.event_type):
                        continue
                    events.append(event)
                    if limit and len(events) >= limit:
                        break
                except Exception as e:
                    logger.debug("Skip malformed event line: %s", e)
        return events

    def replay_from_disk(
        self,
        handler: EventHandler,
        date: str = "",
        event_type: str = "",
        limit: int = 0,
    ) -> int:
        """Replay persisted events through a handler.

        Args:
            handler:    Handler to receive events.
            date:       Date "YYYY-MM-DD". Empty = today.
            event_type: Filter pattern.
            limit:      Max events. 0 = all.

        Returns:
            Number of events replayed.
        """
        events = self.load_persisted(date=date, event_type=event_type, limit=limit)
        count = 0
        for event in events:
            try:
                handler(event)
                count += 1
            except Exception as e:
                logger.error("Disk replay error: %s", e)
        return count

    # ── Stats ────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Bus statistics for monitoring."""
        return {
            "published": self._published,
            "dispatched": self._dispatched,
            "errors": self._errors,
            "history_size": len(self._history),
            "queue": self._queue.stats,
            "subscriptions": {p: len(h) for p, h in self._subscriptions.items()},
            "running": self._running,
            "persist_dir": self._persist_dir,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Global singleton
# ═══════════════════════════════════════════════════════════════════════════

_global_bus: EventBus | None = None
_global_lock = threading.Lock()


def get_bus() -> EventBus:
    """Get or create the global EventBus singleton."""
    global _global_bus
    if _global_bus is None:
        with _global_lock:
            if _global_bus is None:
                _global_bus = EventBus()
    return _global_bus


def reset_bus() -> None:
    """Reset the global bus (for testing)."""
    global _global_bus
    with _global_lock:
        if _global_bus and _global_bus.is_running:
            _global_bus.stop()
        _global_bus = None
