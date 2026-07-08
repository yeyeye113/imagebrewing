"""Performance regression testing for quant-trader.

Ensures optimizations do not introduce performance regressions by comparing
current measurements against stored baselines. Alerts when any metric exceeds
the threshold (default 20% slower).

Usage::

    # Run all regression tests
    python -m quanttrader.benchmark.perf_regression

    # Update baselines after intentional changes
    python -m quanttrader.benchmark.perf_regression --update-baseline

    # Run specific suite only
    python -m quanttrader.benchmark.perf_regression --suite backtest
    python -m quanttrader.benchmark.perf_regression --suite scanner
    python -m quanttrader.benchmark.perf_regression --suite llm
    python -m quanttrader.benchmark.perf_regression --suite data

    # Generate report without failing on regressions
    python -m quanttrader.benchmark.perf_regression --report-only
"""

from __future__ import annotations

import gc
import json
import os
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

_project = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project not in sys.path:
    sys.path.insert(0, _project)

from quanttrader.data.base import BarRequest, get_feed
from quanttrader.engine.backtest import Backtester
from quanttrader.strategy.base import get_strategy

# ── paths ──────────────────────────────────────────────────────────────────
BASELINES_PATH = Path(__file__).parent / "baselines.json"
REPORTS_DIR = Path(_project) / "logs" / "perf_reports"


# ── config ─────────────────────────────────────────────────────────────────

REGRESSION_THRESHOLD = 0.20  # 20% slower = regression
WARMUP_RUNS = 1  # discard first N runs
MEASURE_RUNS = 3  # average over N runs


# ── data structures ────────────────────────────────────────────────────────


@dataclass
class Measurement:
    """Single benchmark measurement."""

    name: str
    elapsed_s: float
    bars_or_items: int = 0
    throughput: float = 0.0  # bars/s or items/s
    mem_delta_mb: float = 0.0
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.elapsed_s > 0 and self.bars_or_items > 0:
            self.throughput = self.bars_or_items / self.elapsed_s


@dataclass
class RegressionResult:
    """Comparison result for a single metric."""

    name: str
    baseline_s: float
    current_s: float
    change_pct: float  # positive = slower
    is_regression: bool
    baseline_throughput: float = 0.0
    current_throughput: float = 0.0


@dataclass
class BenchmarkSuite:
    """Complete regression test suite result."""

    timestamp: str
    machine: str
    suite: str
    measurements: list[Measurement]
    regressions: list[RegressionResult]
    passed: bool


# ── helpers ────────────────────────────────────────────────────────────────


def _mem_mb() -> float:
    try:
        import psutil

        return float(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024))
    except Exception:
        current, _ = tracemalloc.get_traced_memory()
        return current / (1024 * 1024)


def _gen_prices(symbol: str, years: int) -> pd.DataFrame:
    feed = get_feed("synthetic")
    end = date.today()
    start = end - timedelta(days=years * 365)
    req = BarRequest(symbol=symbol, start=start.isoformat(), end=end.isoformat())
    return feed.history(req)


def _load_baselines() -> dict:
    if BASELINES_PATH.exists():
        with open(BASELINES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    return {}


def _save_baselines(data: dict):
    BASELINES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_machine_id() -> str:
    import platform

    return f"{platform.node()}_{platform.system()}_{platform.machine()}"


# ── backtest benchmarks ────────────────────────────────────────────────────


def _bench_backtest_single(years: int, strategy_name: str = "sma_cross") -> Measurement:
    """Benchmark single-symbol backtest for given years."""
    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    prices = _gen_prices("BENCH_REG", years)
    strategy = get_strategy(strategy_name)
    bt = Backtester(cash=100_000, symbol="BENCH_REG")
    bt.run(prices, strategy)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()
    n_bars = len(prices)

    return Measurement(
        name=f"backtest_single_{years}y_{strategy_name}",
        elapsed_s=elapsed,
        bars_or_items=n_bars,
        mem_delta_mb=max(mem_after - mem_before, 0),
        meta={"years": years, "strategy": strategy_name, "bars": n_bars},
    )


def _bench_backtest_multi(n_symbols: int, years: int = 3, strategy_name: str = "sma_cross") -> Measurement:
    """Benchmark multi-symbol backtest."""
    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    strategy = get_strategy(strategy_name)
    total_bars = 0
    for i in range(n_symbols):
        sym = f"BENCH_R{i:04d}"
        prices = _gen_prices(sym, years)
        bt = Backtester(cash=100_000, symbol=sym)
        bt.run(prices, strategy)
        total_bars += len(prices)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()

    return Measurement(
        name=f"backtest_multi_{n_symbols}x{years}y_{strategy_name}",
        elapsed_s=elapsed,
        bars_or_items=total_bars,
        mem_delta_mb=max(mem_after - mem_before, 0),
        meta={"n_symbols": n_symbols, "years": years, "strategy": strategy_name, "total_bars": total_bars},
    )


# ── scanner benchmarks ────────────────────────────────────────────────────


def _bench_scanner_scoring(n: int) -> Measurement:
    """Benchmark scoring logic for n stocks."""
    import random

    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    for i in range(n):
        code = f"{600000 + i}"
        rng = random.Random(hash(code))
        price = rng.uniform(5, 200)
        chg = rng.uniform(-5, 5)
        amount = rng.uniform(1e8, 5e9)
        turnover = rng.uniform(1, 20)

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

    return Measurement(
        name=f"scanner_scoring_{n}",
        elapsed_s=elapsed,
        bars_or_items=n,
        mem_delta_mb=max(mem_after - mem_before, 0),
        meta={"count": n},
    )


# ── LLM benchmarks ────────────────────────────────────────────────────────


def _bench_llm_prompt_build(lookback: int = 60) -> Measurement:
    """Benchmark LLM prompt construction (CPU-only, no API call)."""
    from quanttrader.ai.llm import _build_user_prompt

    prices = _gen_prices("LLM_BENCH", 2)

    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    for _ in range(50):
        _build_user_prompt(prices, lookback=lookback)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()

    return Measurement(
        name=f"llm_prompt_build_{lookback}",
        elapsed_s=elapsed,
        bars_or_items=50,
        mem_delta_mb=max(mem_after - mem_before, 0),
        meta={"lookback": lookback, "iterations": 50},
    )


def _bench_llm_parse_decision() -> Measurement:
    """Benchmark LLM response parsing."""
    from quanttrader.ai.llm import _parse_decision

    sample_responses = [
        '{"signal": 1, "confidence": 0.75, "reason": "Bullish trend confirmed"}',
        '{"signal": -1, "confidence": 0.60, "reason": "Overbought RSI"}',
        "Based on the analysis, I recommend buying. The trend is strong.",
        '{"signal": 0, "confidence": 0.45, "reason": "Mixed signals"}',
    ]

    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    for _ in range(200):
        for resp in sample_responses:
            _parse_decision(resp)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()

    return Measurement(
        name="llm_parse_decision",
        elapsed_s=elapsed,
        bars_or_items=800,  # 200 * 4
        mem_delta_mb=max(mem_after - mem_before, 0),
        meta={"iterations": 200, "variants": len(sample_responses)},
    )


# ── data fetch benchmarks ─────────────────────────────────────────────────


def _bench_data_synthetic(n_bars: int) -> Measurement:
    """Benchmark synthetic data generation."""
    feed = get_feed("synthetic")
    end = date.today()
    start = end - timedelta(days=int(n_bars * 1.5))
    req = BarRequest(symbol="DATA_BENCH", start=start.isoformat(), end=end.isoformat())

    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    for _ in range(20):
        feed.history(req)

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()

    return Measurement(
        name=f"data_synthetic_{n_bars}",
        elapsed_s=elapsed,
        bars_or_items=n_bars * 20,
        mem_delta_mb=max(mem_after - mem_before, 0),
        meta={"n_bars": n_bars, "iterations": 20},
    )


def _bench_data_csv_parse() -> Measurement:
    """Benchmark CSV data parsing (generate temp CSV, then parse)."""
    import io

    n_rows = 2520  # ~10 years of daily data
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(end=date.today(), periods=n_rows)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n_rows)))
    csv_buf = io.StringIO()
    csv_buf.write("Date,Open,High,Low,Close,Volume\n")
    for i in range(n_rows):
        c = close[i]
        csv_buf.write(
            f"{dates[i].strftime('%Y-%m-%d')},{c * 0.99:.2f},{c * 1.01:.2f},{c * 0.98:.2f},{c:.2f},{rng.integers(1000000, 5000000)}\n"
        )
    csv_data = csv_buf.getvalue()

    gc.collect()
    mem_before = _mem_mb()
    t0 = time.perf_counter()

    for _ in range(20):
        df = pd.read_csv(io.StringIO(csv_data), index_col=0, parse_dates=True)
        df.columns = [c.lower() for c in df.columns]

    elapsed = time.perf_counter() - t0
    mem_after = _mem_mb()

    return Measurement(
        name=f"data_csv_parse_{n_rows}",
        elapsed_s=elapsed,
        bars_or_items=n_rows * 20,
        mem_delta_mb=max(mem_after - mem_before, 0),
        meta={"n_rows": n_rows, "iterations": 20},
    )


# ── regression detection ──────────────────────────────────────────────────


def detect_regressions(
    baselines: dict,
    current: list[Measurement],
    threshold: float = REGRESSION_THRESHOLD,
) -> list[RegressionResult]:
    """Compare current measurements against baselines, flag regressions."""
    results = []
    for m in current:
        key = m.name
        if key not in baselines:
            continue
        bl = baselines[key]
        bl_s = bl.get("elapsed_s", 0)
        if bl_s <= 0:
            continue
        change = (m.elapsed_s - bl_s) / bl_s
        is_reg = change > threshold
        results.append(
            RegressionResult(
                name=key,
                baseline_s=bl_s,
                current_s=m.elapsed_s,
                change_pct=change,
                is_regression=is_reg,
                baseline_throughput=bl.get("throughput", 0),
                current_throughput=m.throughput,
            )
        )
    return results


# ── suite runners ──────────────────────────────────────────────────────────


def _run_with_warmup(fn, *args, warmup: int = WARMUP_RUNS, measure: int = MEASURE_RUNS, **kwargs) -> Measurement:
    """Run fn multiple times, return average of measured runs."""
    for _ in range(warmup):
        fn(*args, **kwargs)

    measurements = []
    for _ in range(measure):
        m = fn(*args, **kwargs)
        measurements.append(m)

    # Average the measurements
    avg_elapsed = sum(m.elapsed_s for m in measurements) / len(measurements)
    avg_mem = sum(m.mem_delta_mb for m in measurements) / len(measurements)
    base = measurements[0]
    return Measurement(
        name=base.name,
        elapsed_s=avg_elapsed,
        bars_or_items=base.bars_or_items,
        mem_delta_mb=avg_mem,
        meta={**base.meta, "warmup": warmup, "measure_runs": measure},
    )


def suite_backtest() -> list[Measurement]:
    """Run backtest performance suite."""
    results = []
    for y in (1, 3, 5):
        results.append(_run_with_warmup(_bench_backtest_single, y))
    for n in (50, 100):
        results.append(_run_with_warmup(_bench_backtest_multi, n, 3))
    return results


def suite_scanner() -> list[Measurement]:
    """Run scanner performance suite."""
    results = []
    for n in (50, 100):
        results.append(_run_with_warmup(_bench_scanner_scoring, n))
    return results


def suite_llm() -> list[Measurement]:
    """Run LLM-related performance suite (CPU-only)."""
    results = []
    results.append(_run_with_warmup(_bench_llm_prompt_build, 60))
    results.append(_run_with_warmup(_bench_llm_parse_decision))
    return results


def suite_data() -> list[Measurement]:
    """Run data fetch performance suite."""
    results = []
    for n in (252, 756, 1260):  # 1y, 3y, 5y
        results.append(_run_with_warmup(_bench_data_synthetic, n))
    results.append(_run_with_warmup(_bench_data_csv_parse))
    return results


# ── reporting ──────────────────────────────────────────────────────────────


def _generate_report(
    suite_name: str,
    measurements: list[Measurement],
    regressions: list[RegressionResult],
) -> str:
    """Generate a human-readable performance report."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"  PERFORMANCE REGRESSION REPORT — {suite_name.upper()}")
    lines.append(f"  Generated: {datetime.now().isoformat()}")
    lines.append(f"  Machine: {_get_machine_id()}")
    lines.append("=" * 80)

    # Measurements table
    lines.append("")
    lines.append(f"  {'Benchmark':<40s} | {'Time':>8s} | {'Throughput':>14s} | {'Mem':>8s}")
    lines.append("  " + "-" * 76)
    for m in measurements:
        t_str = f"{m.elapsed_s:.4f}s"
        if m.throughput > 0:
            if "scanner" in m.name or "llm" in m.name:
                tp_str = f"{m.throughput:,.0f} items/s"
            else:
                tp_str = f"{m.throughput:,.0f} bars/s"
        else:
            tp_str = "—"
        mem_str = f"+{m.mem_delta_mb:.1f}MB"
        lines.append(f"  {m.name:<40s} | {t_str:>8s} | {tp_str:>14s} | {mem_str:>8s}")

    # Regression results
    lines.append("")
    if regressions:
        reg_count = sum(1 for r in regressions if r.is_regression)
        lines.append(f"  REGRESSIONS DETECTED: {reg_count}")
        lines.append("  " + "-" * 76)
        for r in regressions:
            icon = "FAIL" if r.is_regression else " OK "
            direction = "slower" if r.change_pct > 0 else "faster"
            lines.append(
                f"  [{icon}] {r.name:<38s} | "
                f"baseline {r.baseline_s:.4f}s -> {r.current_s:.4f}s "
                f"({r.change_pct:+.1%} {direction})"
            )
    else:
        lines.append("  ALL CHECKS PASSED — no regressions detected")

    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def _save_report(report: str, suite_name: str):
    """Save report to logs/perf_reports/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"perf_regression_{suite_name}_{ts}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    return path


# ── main entry points ──────────────────────────────────────────────────────

ALL_SUITES = {
    "backtest": suite_backtest,
    "scanner": suite_scanner,
    "llm": suite_llm,
    "data": suite_data,
}


def run_suite(
    suite_name: str,
    threshold: float = REGRESSION_THRESHOLD,
) -> tuple[list[Measurement], list[RegressionResult], bool]:
    """Run a single benchmark suite, compare to baselines.

    Returns (measurements, regressions, passed).
    """
    if suite_name not in ALL_SUITES:
        raise ValueError(f"Unknown suite: {suite_name!r}. Options: {list(ALL_SUITES)}")

    fn = ALL_SUITES[suite_name]
    measurements = fn()

    baselines = _load_baselines()
    regressions = detect_regressions(baselines, measurements, threshold)
    passed = not any(r.is_regression for r in regressions)

    return measurements, regressions, passed


def run_all_suites(
    threshold: float = REGRESSION_THRESHOLD,
) -> list[BenchmarkSuite]:
    """Run all suites, generate reports, optionally update baselines."""
    all_results = []

    for name in ALL_SUITES:
        measurements, regressions, passed = run_suite(name, threshold)
        report = _generate_report(name, measurements, regressions)
        report_path = _save_report(report, name)

        suite = BenchmarkSuite(
            timestamp=datetime.now().isoformat(),
            machine=_get_machine_id(),
            suite=name,
            measurements=measurements,
            regressions=regressions,
            passed=passed,
        )
        all_results.append(suite)

        print(report)
        print(f"\n  Report saved to: {report_path}\n")

    return all_results


def update_baseline(suite_name: str | None = None):
    """Run benchmarks and save current results as new baselines."""
    baselines = _load_baselines()
    suites_to_update = [suite_name] if suite_name else list(ALL_SUITES)

    for name in suites_to_update:
        measurements, _, _ = run_suite(name)
        for m in measurements:
            baselines[m.name] = {
                "elapsed_s": m.elapsed_s,
                "throughput": m.throughput,
                "bars_or_items": m.bars_or_items,
                "mem_delta_mb": m.mem_delta_mb,
                "updated": datetime.now().isoformat(),
                "machine": _get_machine_id(),
                "meta": m.meta,
            }
        print(f"  Updated baselines for suite: {name}")

    _save_baselines(baselines)
    print(f"\n  Baselines saved to: {BASELINES_PATH}")


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    global WARMUP_RUNS, MEASURE_RUNS

    import argparse

    parser = argparse.ArgumentParser(
        description="Performance regression testing for quant-trader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m quanttrader.benchmark.perf_regression                    # run all
  python -m quanttrader.benchmark.perf_regression --suite backtest   # backtest only
  python -m quanttrader.benchmark.perf_regression --update-baseline  # save baselines
  python -m quanttrader.benchmark.perf_regression --report-only      # no-fail report
        """,
    )
    parser.add_argument(
        "--suite",
        choices=list(ALL_SUITES.keys()),
        help="Run only the specified suite (default: all)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=REGRESSION_THRESHOLD,
        help=f"Regression threshold as fraction (default: {REGRESSION_THRESHOLD})",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Run benchmarks and save results as new baselines",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Generate report without failing on regressions",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=WARMUP_RUNS,
        help=f"Warmup runs before measuring (default: {WARMUP_RUNS})",
    )
    parser.add_argument(
        "--measure-runs",
        type=int,
        default=MEASURE_RUNS,
        help=f"Number of measured runs to average (default: {MEASURE_RUNS})",
    )

    args = parser.parse_args()

    WARMUP_RUNS = args.warmup
    MEASURE_RUNS = args.measure_runs

    if args.update_baseline:
        update_baseline(args.suite)
        return

    if args.suite:
        measurements, regressions, passed = run_suite(args.suite, args.threshold)
        report = _generate_report(args.suite, measurements, regressions)
        report_path = _save_report(report, args.suite)
        print(report)
        print(f"\n  Report saved to: {report_path}")
        if not passed and not args.report_only:
            print("\n  *** PERFORMANCE REGRESSION DETECTED — exiting with code 1 ***")
            sys.exit(1)
    else:
        suites = run_all_suites(args.threshold)
        all_passed = all(s.passed for s in suites)
        if not all_passed and not args.report_only:
            print("\n  *** PERFORMANCE REGRESSION DETECTED — exiting with code 1 ***")
            sys.exit(1)


if __name__ == "__main__":
    main()
