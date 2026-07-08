"""Priority event queue for the quant-trader event-driven architecture.

Provides a thread-safe priority queue that processes events in order of
their Priority level (CRITICAL first, LOW last). Events with equal priority
are processed in FIFO order.

Usage:
    from quanttrader.events.queue import PriorityEventQueue
    from quanttrader.events.types import RiskEvent, MarketEvent

    q = PriorityEventQueue()
    q.put(MarketEvent(symbol="AAPL", price=150.0))
    q.put(RiskEvent(risk_type="stop_loss", message="Hit stop"))

    # RiskEvent comes out first despite being added second
    evt = q.get()  # RiskEvent
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .types import Event, Priority


@dataclass
class PriorityEventQueue:
    """Thread-safe priority queue for events.

    Events are ordered by priority (lower value = higher priority).
    Within the same priority level, FIFO order is preserved via a
    monotonic sequence counter.

    Attributes:
        _queues:  Per-priority-level FIFO deques.
        _lock:    Threading lock for put/get safety.
        _counter: Monotonic counter for FIFO ordering within a priority.
        _notified: Semaphore for blocking get() support.
        _maxsize: Maximum queue depth (0 = unlimited). When full, put()
                  raises QueueFull.
    """

    _queues: dict[int, deque[tuple[int, Event]]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _counter: int = field(default=0)
    _notified: threading.Semaphore = field(default_factory=threading.Semaphore)
    _maxsize: int = 0
    _total_put: int = field(default=0)
    _total_get: int = field(default=0)

    def __post_init__(self) -> None:
        # Initialize a deque for each priority level
        for p in Priority:
            self._queues[p.value] = deque()

    # ── Core operations ──────────────────────────────────────────────

    def put(self, event: Event) -> None:
        """Add an event to the queue.

        Args:
            event: The Event to enqueue.

        Raises:
            RuntimeError: If the queue is at maxsize capacity.
        """
        with self._lock:
            if self._maxsize > 0 and self.size() >= self._maxsize:
                raise RuntimeError(
                    f"EventQueue full (maxsize={self._maxsize}). Drop low-priority events or increase capacity."
                )
            seq = self._counter
            self._counter += 1
            self._queues[event.priority.value].append((seq, event))
            self._total_put += 1
        self._notified.release()

    def get(self, block: bool = True, timeout: float | None = None) -> Event:
        """Remove and return the highest-priority event.

        Args:
            block:  If True, wait for an event to be available.
            timeout: Max seconds to wait when blocking. None = wait forever.

        Returns:
            The highest-priority Event.

        Raises:
            RuntimeError: If block=False and queue is empty.
            TimeoutError: If timeout expires while blocking.
        """
        if block:
            import time as _time

            deadline = _time.monotonic() + timeout if timeout else None
            while True:
                remaining = (deadline - _time.monotonic()) if deadline else None
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("Timed out waiting for event")
                acquired = self._notified.acquire(timeout=remaining)
                if not acquired:
                    raise TimeoutError("Timed out waiting for event")
                # Try to get from queue (may be empty due to race)
                with self._lock:
                    for p in sorted(self._queues.keys()):
                        q = self._queues[p]
                        if q:
                            _, event = q.popleft()
                            self._total_get += 1
                            return event
                # Semaphore acquired but queue empty — retry
        else:
            with self._lock:
                for p in sorted(self._queues.keys()):
                    q = self._queues[p]
                    if q:
                        _, event = q.popleft()
                        self._total_get += 1
                        return event

        raise RuntimeError("EventQueue is empty (non-blocking get)")

    def get_nowait(self) -> Event | None:
        """Non-blocking get. Returns None if queue is empty."""
        try:
            return self.get(block=False)
        except RuntimeError:
            return None

    # ── Inspection ───────────────────────────────────────────────────

    def size(self) -> int:
        """Total number of events across all priority levels."""
        return sum(len(q) for q in self._queues.values())

    def size_by_priority(self) -> dict[Priority, int]:
        """Event count per priority level."""
        return {Priority(p): len(q) for p, q in self._queues.items() if len(q) > 0}

    def is_empty(self) -> bool:
        """True if no events are queued."""
        return self.size() == 0

    def peek(self) -> Event | None:
        """Return the highest-priority event without removing it, or None."""
        with self._lock:
            for p in sorted(self._queues.keys()):
                q = self._queues[p]
                if q:
                    return q[0][1]
        return None

    @property
    def stats(self) -> dict[str, Any]:
        """Queue statistics for monitoring."""
        return {
            "size": self.size(),
            "by_priority": {Priority(p).name: len(q) for p, q in self._queues.items()},
            "total_put": self._total_put,
            "total_get": self._total_get,
            "maxsize": self._maxsize,
        }

    # ── Bulk operations ──────────────────────────────────────────────

    def drain(self, max_items: int = 0) -> list[Event]:
        """Drain events from the queue in priority order.

        Args:
            max_items: Maximum events to drain. 0 = drain all.

        Returns:
            List of events in priority order.
        """
        events: list[Event] = []
        with self._lock:
            count = 0
            for p in sorted(self._queues.keys()):
                q = self._queues[p]
                while q and (max_items == 0 or count < max_items):
                    _, event = q.popleft()
                    events.append(event)
                    count += 1
                    self._total_get += 1
        return events

    def clear(self) -> int:
        """Remove all events. Returns count of removed events."""
        with self._lock:
            count = self.size()
            for q in self._queues.values():
                q.clear()
        return count
