"""Performance benchmark suite for quant-trader.

Modules:
    backtest_bench  -- single/multi-symbol backtest throughput
    scanner_bench   -- scanner scoring/divination throughput
    api_bench       -- FastAPI endpoint latency & throughput
    load_test       -- concurrent stress tests with memory monitoring

Usage::

    python -m quanttrader.benchmark.backtest_bench   # quick single-symbol test
    python -m quanttrader.benchmark.scanner_bench     # scanner throughput
    python -m quanttrader.benchmark.api_bench         # API latency (start server first)
    python -m quanttrader.benchmark.load_test         # full concurrent suite
"""
