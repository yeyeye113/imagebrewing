"""Backtest performance benchmark.

Measures:
    1. Single-symbol backtest: 1y / 3y / 5y synthetic data
    2. Multi-symbol backtest: 10 / 50 / 100 symbols
    3. Throughput (bars/sec) and memory delta

Usage::

    python -m quanttrader.benchmark.backtest_bench
"""

from __future__ import annotations

import gc
import os
import sys
import time
import tracemalloc
from dataclasses import dataclass

import pandas as pd

# ── project imports ──────────────────────────────────────────────────────
_project = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project not in sys.path:
    sys.path.insert(0, _project)

from quanttrader.data.base import BarRequest, get_feed
from quanttrader.engine.backtest import Backtester
from quanttrader.strategy.base import get_strategy

# ── helpers ──────────────────────────────────────────────────────────────


@dataclass
class BenchResult:
    label: str
    elapsed_s: float
    bars: int
    symbols: int = 1
    bars_per_sec: float = 0.0
    mem_delta_mb: float = 0.0
    peak_mem_mb: float = 0.0

    def __post_init__(self):
        if self.elapsed_s > 0:
            self.bars_per_sec = self.bars / self.elapsed_s


def _gen_prices(symbol: str, years: int) -> pd.DataFrame:
    """Generate synthetic OHLCV for *symbol* spanning *years* years."""
    feed = get_feed("synthetic")
    from datetime import date, timedelta

    end = date.today()
    start = end - timedelta(days=years * 365)
    req = BarRequest(symbol=symbol, start=start.isoformat(), end=end.isoformat())
    return feed.history(req)


def _mem_mb() -> float:
    """Current process RSS in MB (cross-platform best-effort)."""
    try:
        import psutil

        return float(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024))
    except Exception:
        # fallback: tracemalloc
        current, _ = tracemalloc.get_traced_memory()
        return current / (1024 * 1024)


def _print_result(r: BenchResult):
    print(
        f"  {r.label:30s} | {r.elapsed_s:8.3f}s | "
        f"{r.bars:>10,d} bars ({r.symbols} sym) | "
        f"{r.bars_per_sec:>12,.0f} bars/s | "
        f"mem +{r.mem_delta_mb:6.1f}MB (peak {r.peak_mem_mb:.1f}MB)"
    )


# ── benchmarks ──────────────────────────────────────────────────────────


def bench_single_symbol(years: int = 1, strategy_name: str = "sma_cross") -> BenchResult:
    """Backtest one symbol for *years* years of daily data."""
    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    prices = _gen_prices("BENCH_001", years)
    strategy = get_strategy(strategy_name)
    bt = Backtester(cash=100_000, symbol="BENCH_001")
    result = bt.run(prices, strategy)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()
    n_bars = len(prices)
    return BenchResult(
        label=f"single {strategy_name} {years}y",
        elapsed_s=elapsed,
        bars=n_bars,
        bars_per_sec=n_bars / max(elapsed, 1e-9),
        mem_delta_mb=max(mem_after - mem_before, 0),
        peak_mem_mb=mem_after,
    )


def bench_multi_symbol(n_symbols: int = 10, years: int = 3, strategy_name: str = "sma_cross") -> BenchResult:
    """Backtest *n_symbols* independently (sequential)."""
    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    strategy = get_strategy(strategy_name)
    total_bars = 0
    for i in range(n_symbols):
        sym = f"BENCH_{i:04d}"
        prices = _gen_prices(sym, years)
        bt = Backtester(cash=100_000, symbol=sym)
        bt.run(prices, strategy)
        total_bars += len(prices)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()
    return BenchResult(
        label=f"multi {n_symbols}x{years}y {strategy_name}",
        elapsed_s=elapsed,
        bars=total_bars,
        symbols=n_symbols,
        bars_per_sec=total_bars / max(elapsed, 1e-9),
        mem_delta_mb=max(mem_after - mem_before, 0),
        peak_mem_mb=mem_after,
    )


def run_all():
    """Run the full backtest benchmark suite."""
    print("=" * 90)
    print("  BACKTEST BENCHMARK")
    print("=" * 90)
    results: list[BenchResult] = []

    # ── single-symbol ──
    print("\n>> Single-symbol backtests (SMA cross)")
    for y in (1, 3, 5):
        r = bench_single_symbol(years=y)
        _print_result(r)
        results.append(r)

    # ── multi-symbol ──
    print("\n>> Multi-symbol backtests (3y each, SMA cross)")
    for n in (10, 50, 100):
        r = bench_multi_symbol(n_symbols=n, years=3)
        _print_result(r)
        results.append(r)

    # ── strategy comparison ──
    print("\n>> Strategy comparison (1y, single symbol)")
    for strat in ("sma_cross", "rsi", "bollinger", "momentum"):
        try:
            r = bench_single_symbol(years=1, strategy_name=strat)
            _print_result(r)
            results.append(r)
        except Exception as e:
            print(f"  {strat:30s} | SKIP ({e})")

    # ── summary ──
    print("\n" + "-" * 90)
    total_bars = sum(r.bars for r in results)
    total_time = sum(r.elapsed_s for r in results)
    avg_bps = total_bars / max(total_time, 1e-9)
    print(f"  TOTAL: {total_bars:>12,d} bars in {total_time:.2f}s  ({avg_bps:,.0f} bars/s avg)")
    print("=" * 90)
    return results


if __name__ == "__main__":
    run_all()
