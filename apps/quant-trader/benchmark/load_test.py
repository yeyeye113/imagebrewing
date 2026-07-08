"""Concurrent load test with memory monitoring.

Runs mixed workloads (backtest + scanner + API) concurrently,
tracking throughput, latency, and memory growth under pressure.

Usage::

    python -m quanttrader.benchmark.load_test
    python -m quanttrader.benchmark.load_test --duration 60 --threads 20
"""

from __future__ import annotations

import argparse
import gc
import os
import random
import sys
import threading
import time
import tracemalloc
from dataclasses import dataclass, field

import pandas as pd

_project = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project not in sys.path:
    sys.path.insert(0, _project)

from quanttrader.data.base import BarRequest, get_feed
from quanttrader.engine.backtest import Backtester
from quanttrader.strategy.base import get_strategy

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ── data structures ──────────────────────────────────────────────────────


@dataclass
class WorkerStats:
    name: str
    calls: int = 0
    errors: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    latencies: list = field(default_factory=list)

    def record(self, ms: float, error: bool = False):
        self.calls += 1
        self.errors += int(error)
        self.total_ms += ms
        self.min_ms = min(self.min_ms, ms)
        self.max_ms = max(self.max_ms, ms)
        self.latencies.append(ms)

    @property
    def avg_ms(self) -> float:
        return self.total_ms / max(self.calls, 1)

    @property
    def p95_ms(self) -> float:
        if not self.latencies:
            return 0.0
        s = sorted(self.latencies)
        return float(s[min(int(len(s) * 0.95), len(s) - 1)])


@dataclass
class MemorySnapshot:
    timestamp_s: float
    rss_mb: float
    alloc_mb: float


# ── helpers ──────────────────────────────────────────────────────────────

_stop_event = threading.Event()
_lock = threading.Lock()


def _mem_snapshot() -> MemorySnapshot:
    rss = 0.0
    try:
        import psutil

        rss = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        pass
    alloc, _ = tracemalloc.get_traced_memory()
    alloc_mb = alloc / (1024 * 1024)
    return MemorySnapshot(time.perf_counter(), rss, alloc_mb)


def _gen_prices(symbol: str, n_bars: int) -> pd.DataFrame:
    feed = get_feed("synthetic")
    from datetime import date, timedelta

    end = date.today()
    start = end - timedelta(days=int(n_bars * 1.5))
    req = BarRequest(symbol=symbol, start=start.isoformat(), end=end.isoformat())
    df = feed.history(req)
    return df.iloc[:n_bars]


# ── worker functions ─────────────────────────────────────────────────────


def _worker_backtest(stats: WorkerStats, n_bars: int = 252):
    """Continuously run backtests until stop signal."""
    strategy = get_strategy("sma_cross")
    while not _stop_event.is_set():
        sym = f"LOAD_{random.randint(0, 9999):04d}"
        t0 = time.perf_counter()
        try:
            prices = _gen_prices(sym, n_bars)
            bt = Backtester(cash=100_000, symbol=sym)
            bt.run(prices, strategy)
            ms = (time.perf_counter() - t0) * 1000
            stats.record(ms)
        except Exception:
            ms = (time.perf_counter() - t0) * 1000
            stats.record(ms, error=True)


def _worker_scanner(stats: WorkerStats, n_items: int = 50):
    """Continuously run scanner-style scoring until stop signal."""
    while not _stop_event.is_set():
        t0 = time.perf_counter()
        try:
            for i in range(n_items):
                turnover = 5.0 + (i % 10)
                chg = (i % 7) - 3
                score = min(int(turnover * 2) + min(int(abs(chg) * 5), 25), 100)
                _ = score
            ms = (time.perf_counter() - t0) * 1000
            stats.record(ms)
        except Exception:
            ms = (time.perf_counter() - t0) * 1000
            stats.record(ms, error=True)


def _worker_api(stats: WorkerStats, base_url: str, path: str = "/health"):
    """Continuously hit API endpoint until stop signal."""
    if not HAS_REQUESTS:
        return
    while not _stop_event.is_set():
        t0 = time.perf_counter()
        try:
            r = requests.get(f"{base_url}{path}", timeout=10)
            ms = (time.perf_counter() - t0) * 1000
            stats.record(ms, error=r.status_code >= 400)
        except Exception:
            ms = (time.perf_counter() - t0) * 1000
            stats.record(ms, error=True)


# ── memory monitor ───────────────────────────────────────────────────────


def _memory_monitor(snapshots: list[MemorySnapshot], interval_s: float = 1.0):
    """Record memory usage at regular intervals."""
    while not _stop_event.is_set():
        snapshots.append(_mem_snapshot())
        _stop_event.wait(interval_s)


# ── main load test ───────────────────────────────────────────────────────


def run_load_test(
    duration_s: int = 30,
    n_backtest_threads: int = 4,
    n_scanner_threads: int = 4,
    n_api_threads: int = 2,
    api_base: str = "http://127.0.0.1:8000",
    memory_interval_s: float = 1.0,
):
    """Execute the mixed concurrent load test."""
    global _stop_event
    _stop_event.clear()

    print("=" * 100)
    print("  CONCURRENT LOAD TEST")
    print(
        f"  Duration: {duration_s}s | "
        f"Backtest: {n_backtest_threads} threads | "
        f"Scanner: {n_scanner_threads} threads | "
        f"API: {n_api_threads} threads"
    )
    print("=" * 100)

    gc.collect()
    tracemalloc.start()
    mem_start = _mem_snapshot()
    print(f"\n  Memory at start: RSS={mem_start.rss_mb:.1f}MB  Alloc={mem_start.alloc_mb:.1f}MB")

    # ── stats per worker type ──
    bt_stats = [WorkerStats(f"backtest_{i}") for i in range(n_backtest_threads)]
    sc_stats = [WorkerStats(f"scanner_{i}") for i in range(n_scanner_threads)]
    api_stats = [WorkerStats(f"api_{i}") for i in range(n_api_threads)]
    mem_snapshots: list[MemorySnapshot] = []

    threads: list[threading.Thread] = []

    # backtest workers
    for s in bt_stats:
        t = threading.Thread(target=_worker_backtest, args=(s, 252), daemon=True)
        threads.append(t)
    # scanner workers
    for s in sc_stats:
        t = threading.Thread(target=_worker_scanner, args=(s, 50), daemon=True)
        threads.append(t)
    # API workers
    for s in api_stats:
        t = threading.Thread(target=_worker_api, args=(s, api_base, "/health"), daemon=True)
        threads.append(t)
    # memory monitor
    mem_thread = threading.Thread(target=_memory_monitor, args=(mem_snapshots, memory_interval_s), daemon=True)
    threads.append(mem_thread)

    # ── start all ──
    t_start = time.perf_counter()
    for t in threads:
        t.start()
    print(f"  Launched {len(threads)} threads, running for {duration_s}s ...\n")

    _stop_event.wait(duration_s)
    _stop_event.set()

    for t in threads:
        t.join(timeout=5)

    total_s = time.perf_counter() - t_start
    mem_end = _mem_snapshot()

    # ── results ──
    print("-" * 100)
    print(f"  {'Worker':<30s} | {'Calls':>6s} | {'Err':>4s} | {'Avg':>8s} | {'P95':>8s} | {'Min':>8s} | {'Max':>8s}")
    print("-" * 100)

    all_stats = bt_stats + sc_stats + api_stats
    for s in all_stats:
        if s.calls == 0:
            continue
        print(
            f"  {s.name:<30s} | {s.calls:>6d} | {s.errors:>4d} | "
            f"{s.avg_ms:>7.1f}ms | {s.p95_ms:>7.1f}ms | "
            f"{s.min_ms:>7.1f}ms | {s.max_ms:>7.1f}ms"
        )

    # ── aggregate ──
    total_calls = sum(s.calls for s in all_stats)
    total_errors = sum(s.errors for s in all_stats)
    all_lat = []
    for s in all_stats:
        all_lat.extend(s.latencies)
    all_lat.sort()

    print("-" * 100)
    if all_lat:
        n = len(all_lat)
        p50 = all_lat[int(n * 0.50)]
        p95 = all_lat[min(int(n * 0.95), n - 1)]
        p99 = all_lat[min(int(n * 0.99), n - 1)]
        print(
            f"  AGGREGATE: {total_calls} calls, {total_errors} errors in {total_s:.1f}s "
            f"({total_calls / max(total_s, 1e-9):.1f} calls/s)"
        )
        print(f"  LATENCY:   p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms")
    else:
        print("  No successful calls recorded.")

    # ── memory report ──
    print("\n" + "-" * 100)
    print("  MEMORY REPORT")
    print("-" * 100)
    rss_delta = mem_end.rss_mb - mem_start.rss_mb
    alloc_delta = mem_end.alloc_mb - mem_start.alloc_mb
    peak_rss = max(s.rss_mb for s in mem_snapshots) if mem_snapshots else mem_end.rss_mb
    peak_alloc = max(s.alloc_mb for s in mem_snapshots) if mem_snapshots else mem_end.alloc_mb
    print(f"  Start:    RSS={mem_start.rss_mb:.1f}MB  Alloc={mem_start.alloc_mb:.1f}MB")
    print(f"  End:      RSS={mem_end.rss_mb:.1f}MB  Alloc={mem_end.alloc_mb:.1f}MB")
    print(f"  Delta:    RSS={rss_delta:+.1f}MB  Alloc={alloc_delta:+.1f}MB")
    print(f"  Peak:     RSS={peak_rss:.1f}MB  Alloc={peak_alloc:.1f}MB")
    print(f"  Samples:  {len(mem_snapshots)} snapshots over {total_s:.1f}s")

    # ── memory timeline ──
    if len(mem_snapshots) > 5:
        print("\n  Memory timeline (RSS MB):")
        step = max(1, len(mem_snapshots) // 10)
        for i in range(0, len(mem_snapshots), step):
            snap = mem_snapshots[i]
            bar_len = int(snap.rss_mb / 10)
            print(f"    t={snap.timestamp_s - t_start:6.1f}s | {snap.rss_mb:6.1f}MB | {'#' * bar_len}")
        # last sample
        snap = mem_snapshots[-1]
        bar_len = int(snap.rss_mb / 10)
        print(f"    t={snap.timestamp_s - t_start:6.1f}s | {snap.rss_mb:6.1f}MB | {'#' * bar_len}")

    print("=" * 100)

    tracemalloc.stop()
    return {
        "total_calls": total_calls,
        "total_errors": total_errors,
        "duration_s": total_s,
        "calls_per_sec": total_calls / max(total_s, 1e-9),
        "mem_start_rss_mb": mem_start.rss_mb,
        "mem_end_rss_mb": mem_end.rss_mb,
        "mem_peak_rss_mb": peak_rss,
    }


# ── entry point ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="quant-trader concurrent load test")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds (default: 30)")
    parser.add_argument("--backtest-threads", type=int, default=4, help="Backtest worker threads (default: 4)")
    parser.add_argument("--scanner-threads", type=int, default=4, help="Scanner worker threads (default: 4)")
    parser.add_argument("--api-threads", type=int, default=2, help="API worker threads (default: 2)")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="API base URL")
    args = parser.parse_args()

    run_load_test(
        duration_s=args.duration,
        n_backtest_threads=args.backtest_threads,
        n_scanner_threads=args.scanner_threads,
        n_api_threads=args.api_threads,
        api_base=args.api_base,
    )


if __name__ == "__main__":
    main()
