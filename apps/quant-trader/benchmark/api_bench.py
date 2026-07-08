"""API endpoint performance benchmark.

Measures latency (p50/p95/p99) and throughput for key API endpoints.
Requires the FastAPI server to be running at the target URL.

Usage::

    # start server first:
    #   python -m uvicorn quanttrader.api.server:app --host 127.0.0.1 --port 8000
    # then:
    python -m quanttrader.benchmark.api_bench
"""

from __future__ import annotations

import gc
import os
import statistics
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import requests

_project = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project not in sys.path:
    sys.path.insert(0, _project)

DEFAULT_BASE = "http://127.0.0.1:8000"


@dataclass
class LatencyStats:
    label: str
    count: int
    errors: int = 0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    avg_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    rps: float = 0.0
    total_s: float = 0.0

    @classmethod
    def from_latencies(cls, label: str, latencies_ms: list[float], errors: int, total_s: float) -> LatencyStats:
        if not latencies_ms:
            return cls(label=label, count=0, errors=errors, total_s=total_s)
        s = sorted(latencies_ms)
        n = len(s)
        return cls(
            label=label,
            count=n,
            errors=errors,
            p50_ms=s[int(n * 0.50)],
            p95_ms=s[min(int(n * 0.95), n - 1)],
            p99_ms=s[min(int(n * 0.99), n - 1)],
            avg_ms=statistics.mean(s),
            min_ms=s[0],
            max_ms=s[-1],
            rps=n / max(total_s, 1e-9),
            total_s=total_s,
        )


def _mem_mb() -> float:
    try:
        import psutil

        return float(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024))
    except Exception:
        current, _ = tracemalloc.get_traced_memory()
        return current / (1024 * 1024)


def _get(base: str, path: str, params: dict | None = None) -> tuple[float, bool]:
    """Single GET request, returns (latency_ms, is_error)."""
    t0 = time.perf_counter()
    try:
        r = requests.get(f"{base}{path}", params=params, timeout=30)
        ok = r.status_code < 400
    except Exception:
        ok = False
    ms = (time.perf_counter() - t0) * 1000
    return ms, not ok


def _post(base: str, path: str, json: Any = None) -> tuple[float, bool]:
    """Single POST request, returns (latency_ms, is_error)."""
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{base}{path}", json=json, timeout=60)
        ok = r.status_code < 400
    except Exception:
        ok = False
    ms = (time.perf_counter() - t0) * 1000
    return ms, not ok


def bench_endpoint(
    name: str,
    method: str,
    base: str,
    path: str,
    params: dict | None = None,
    json_body: Any = None,
    n_requests: int = 20,
    concurrency: int = 1,
) -> LatencyStats:
    """Benchmark a single endpoint with sequential or concurrent requests."""
    gc.collect()
    mem_before = _mem_mb()

    latencies: list[float] = []
    errors = 0

    t0 = time.perf_counter()

    if concurrency <= 1:
        for _ in range(n_requests):
            if method == "GET":
                ms, is_err = _get(base, path, params)
            else:
                ms, is_err = _post(base, path, json_body)
            latencies.append(ms)
            errors += is_err
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = []
            for _ in range(n_requests):
                if method == "GET":
                    futures.append(pool.submit(_get, base, path, params))
                else:
                    futures.append(pool.submit(_post, base, path, json_body))
            for f in as_completed(futures):
                ms, is_err = f.result()
                latencies.append(ms)
                errors += is_err

    total_s = time.perf_counter() - t0
    mem_after = _mem_mb()

    stats = LatencyStats.from_latencies(name, latencies, errors, total_s)
    # attach memory info
    stats.avg_ms = stats.avg_ms  # already set
    return stats


def _print_stats(s: LatencyStats):
    print(
        f"  {s.label:35s} | {s.count:>4d} reqs ({s.errors} err) | "
        f"p50={s.p50_ms:7.1f}ms  p95={s.p95_ms:7.1f}ms  p99={s.p99_ms:7.1f}ms | "
        f"{s.rps:6.1f} rps"
    )


def check_server(base: str) -> bool:
    """Verify the API server is reachable."""
    try:
        r = requests.get(f"{base}/health", timeout=5)
        return bool(r.status_code == 200)
    except Exception:
        return False


def run_all(base_url: str = DEFAULT_BASE):
    """Run the full API benchmark suite."""
    print("=" * 100)
    print("  API BENCHMARK")
    print(f"  Target: {base_url}")
    print("=" * 100)

    if not check_server(base_url):
        print(f"\n  ** Server not reachable at {base_url} -- skipping API benchmarks **")
        print("     Start with: python -m uvicorn quanttrader.api.server:app --host 127.0.0.1 --port 8000")
        return []

    print("\n>> GET endpoints (sequential, 20 requests)")
    # 统一四元组 (name, method, path, params) 便于类型收敛
    endpoints_get: list[tuple[str, str, str, dict[str, str] | None]] = [
        ("health", "GET", "/health", None),
        ("market/price", "GET", "/market/price", {"symbol": "600519", "source": "synthetic"}),
        (
            "market/bars",
            "GET",
            "/market/bars",
            {"symbol": "600519", "source": "synthetic", "start": "2024-01-01", "end": "2024-12-31"},
        ),
        ("horizons", "GET", "/horizons", None),
        ("principles", "GET", "/principles", None),
        ("portfolio", "GET", "/portfolio", None),
        ("playbooks", "GET", "/playbooks", None),
    ]

    all_stats: list[LatencyStats] = []
    for name, method, path, params in endpoints_get:
        s = bench_endpoint(name, method, base_url, path, params=params, n_requests=20)
        _print_stats(s)
        all_stats.append(s)

    print("\n>> POST endpoints (sequential, 20 requests)")
    endpoints_post: list[tuple[str, str, str, dict[str, Any] | None]] = [
        (
            "backtest",
            "POST",
            "/backtest",
            {
                "symbol": "600519",
                "source": "synthetic",
                "start": "2024-01-01",
                "end": "2024-12-31",
                "strategy": "sma_cross",
            },
        ),
        ("scanner/run", "POST", "/api/scanner/run", None),
    ]

    for entry in endpoints_post:
        name, method, path, body = entry
        s = bench_endpoint(name, method, base_url, path, json_body=body, n_requests=20)
        _print_stats(s)
        all_stats.append(s)

    print("\n>> Concurrent health checks (10/50/100 parallel)")
    for conc in (10, 50, 100):
        s = bench_endpoint(
            f"health x{conc} conc",
            "GET",
            base_url,
            "/health",
            n_requests=conc,
            concurrency=conc,
        )
        _print_stats(s)
        all_stats.append(s)

    # ── summary ──
    print("\n" + "-" * 100)
    total_reqs = sum(s.count for s in all_stats)
    total_errs = sum(s.errors for s in all_stats)
    avg_p50 = statistics.mean([s.p50_ms for s in all_stats if s.count > 0])
    avg_p95 = statistics.mean([s.p95_ms for s in all_stats if s.count > 0])
    print(f"  TOTAL: {total_reqs} requests, {total_errs} errors | avg p50={avg_p50:.1f}ms  p95={avg_p95:.1f}ms")
    print("=" * 100)
    return all_stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="API benchmark")
    parser.add_argument("--base", default=DEFAULT_BASE, help="API base URL")
    args = parser.parse_args()
    run_all(base_url=args.base)
