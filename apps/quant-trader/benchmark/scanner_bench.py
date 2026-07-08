"""Scanner performance benchmark.

Measures scoring throughput on synthetic stock data.
Avoids network calls -- benchmarks the pure compute path.

Usage::

    python -m quanttrader.benchmark.scanner_bench
"""

from __future__ import annotations

import gc
import os
import random
import sys
import time
import tracemalloc
from dataclasses import dataclass

_project = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project not in sys.path:
    sys.path.insert(0, _project)


@dataclass
class ScannerBenchResult:
    label: str
    elapsed_s: float
    count: int
    per_item_us: float = 0.0
    mem_delta_mb: float = 0.0
    peak_mem_mb: float = 0.0

    def __post_init__(self):
        if self.count > 0:
            self.per_item_us = (self.elapsed_s / self.count) * 1_000_000


def _mem_mb() -> float:
    try:
        import psutil

        return float(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024))
    except Exception:
        current, _ = tracemalloc.get_traced_memory()
        return current / (1024 * 1024)


def _fake_stock(code: str) -> dict:
    """Generate a fake stock dict mimicking Sina API response."""
    rng = random.Random(hash(code))
    return {
        "code": code,
        "name": f"测试{code[-3:]}",
        "trade": f"{rng.uniform(5, 200):.2f}",
        "changepercent": f"{rng.uniform(-5, 5):.2f}",
        "amount": f"{rng.uniform(1e8, 5e9):.0f}",
        "turnoverratio": f"{rng.uniform(1, 20):.2f}",
    }


def _bench_scoring(n: int) -> ScannerBenchResult:
    """Benchmark the scoring logic (momentum + volume + liquidity scoring)."""
    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    for i in range(n):
        code = f"{600000 + i}"
        stock = _fake_stock(code)
        price = float(stock["trade"])
        chg = float(stock["changepercent"])
        amount = float(stock["amount"])
        turnover = float(stock["turnoverratio"])

        # Replicate the scoring logic from scanner/lite.py
        score = 0
        score += min(int(turnover * 2), 30)  # turnover component
        score += min(int(abs(chg) * 5), 25)  # momentum component
        score += min(int(amount / 1e9), 25)  # liquidity component
        if price > 20:
            score += 10
        if 5 < price < 50:
            score += 10
        score = min(score, 100)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()
    return ScannerBenchResult(
        label=f"scoring x{n}",
        elapsed_s=elapsed,
        count=n,
        mem_delta_mb=max(mem_after - mem_before, 0),
        peak_mem_mb=mem_after,
    )


def _bench_full_pipeline(n: int) -> ScannerBenchResult:
    """Benchmark scoring pipeline (技术面)."""
    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    for i in range(n):
        code = f"{600000 + i}"
        stock = _fake_stock(code)
        price = float(stock["trade"])
        chg = float(stock["changepercent"])
        amount = float(stock["amount"])
        turnover = float(stock["turnoverratio"])

        score = 0
        score += min(int(turnover * 2), 30)
        score += min(int(abs(chg) * 5), 25)
        score += min(int(amount / 1e9), 25)
        if price > 20:
            score += 10
        if 5 < price < 50:
            score += 10
        score = min(score, 100)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()
    return ScannerBenchResult(
        label=f"pipeline x{n}",
        elapsed_s=elapsed,
        count=n,
        mem_delta_mb=max(mem_after - mem_before, 0),
        peak_mem_mb=mem_after,
    )


def _print_result(r: ScannerBenchResult):
    print(
        f"  {r.label:30s} | {r.elapsed_s:8.3f}s | "
        f"{r.count:>6d} items | {r.per_item_us:>8.1f} us/item | "
        f"mem +{r.mem_delta_mb:5.1f}MB (peak {r.peak_mem_mb:.1f}MB)"
    )


def run_all():
    """Run the full scanner benchmark suite."""
    print("=" * 90)
    print("  SCANNER BENCHMARK")
    print("=" * 90)
    results: list[ScannerBenchResult] = []

    print("\n>> Scoring throughput")
    for n in (50, 100, 500):
        r = _bench_scoring(n)
        _print_result(r)
        results.append(r)

    print("\n>> Full pipeline (scoring)")
    for n in (50, 100, 500):
        r = _bench_full_pipeline(n)
        _print_result(r)
        results.append(r)

    print("\n" + "-" * 90)
    total_items = sum(r.count for r in results)
    total_time = sum(r.elapsed_s for r in results)
    avg_us = (total_time / max(total_items, 1)) * 1_000_000
    print(f"  TOTAL: {total_items:>8,d} items in {total_time:.2f}s  ({avg_us:.1f} us/item avg)")
    print("=" * 90)
    return results


if __name__ == "__main__":
    run_all()
