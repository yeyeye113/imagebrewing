"""Prometheus metric collectors for quanttrader.

All metrics are registered here. Import and use in daemon/trader code.
Requires: pip install prometheus-client

Usage in daemon.py / trader.py:
    from quanttrader.metrics import collectors
    collectors.TRADE_COUNT.labels(symbol="600519", side="buy").inc()
    collectors.LLM_LATENCY.observe(elapsed_seconds)
"""

from __future__ import annotations

import logging

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

logger = logging.getLogger("quanttrader.metrics")

# ═══════════════════════════════════════════════════════════════════════════
# Trading metrics
# ═══════════════════════════════════════════════════════════════════════════

TRADE_COUNT = Counter(
    "quanttrader_trades_total",
    "Total number of trades executed",
    ["symbol", "side", "exit_reason"],
)

TRADE_PNL = Histogram(
    "quanttrader_trade_pnl",
    "Profit/loss per trade in currency units",
    ["symbol"],
    buckets=[-10000, -5000, -2000, -1000, -500, -100, 0, 100, 500, 1000, 2000, 5000, 10000],
)

TRADE_WIN_RATE = Gauge(
    "quanttrader_win_rate",
    "Running win rate (wins / total_trades)",
    ["symbol"],
)

# ═══════════════════════════════════════════════════════════════════════════
# LLM metrics
# ═══════════════════════════════════════════════════════════════════════════

LLM_LATENCY = Histogram(
    "quanttrader_llm_latency_seconds",
    "LLM API call latency in seconds",
    ["provider", "model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 15.0, 30.0],
)

LLM_CALLS_TOTAL = Counter(
    "quanttrader_llm_calls_total",
    "Total LLM API calls",
    ["provider", "model", "status"],
)

LLM_CONFIDENCE = Histogram(
    "quanttrader_llm_confidence",
    "LLM signal confidence distribution",
    ["signal"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ═══════════════════════════════════════════════════════════════════════════
# Scanner metrics
# ═══════════════════════════════════════════════════════════════════════════

SCANNER_DURATION = Histogram(
    "quanttrader_scanner_duration_seconds",
    "Scanner execution time in seconds",
    buckets=[1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 60.0],
)

SCANNER_STOCKS_FOUND = Gauge(
    "quanttrader_scanner_stocks_found",
    "Number of stocks returned by scanner",
)

# ═══════════════════════════════════════════════════════════════════════════
# Risk metrics
# ═══════════════════════════════════════════════════════════════════════════

RISK_EVENTS = Counter(
    "quanttrader_risk_events_total",
    "Risk management events (stop_loss, circuit_breaker, etc.)",
    ["event_type", "symbol"],
)

EQUITY_GAUGE = Gauge(
    "quanttrader_equity",
    "Current portfolio equity",
    ["symbol"],
)

POSITION_GAUGE = Gauge(
    "quanttrader_position_qty",
    "Current position size (shares)",
    ["symbol"],
)

DRAWDOWN_GAUGE = Gauge(
    "quanttrader_drawdown_pct",
    "Current drawdown from peak equity (%)",
    ["symbol"],
)

CONSECUTIVE_LOSSES = Gauge(
    "quanttrader_consecutive_losses",
    "Number of consecutive losing trades",
)

# ═══════════════════════════════════════════════════════════════════════════
# Daemon metrics
# ═══════════════════════════════════════════════════════════════════════════

DAEMON_UPTIME = Gauge(
    "quanttrader_daemon_uptime_seconds",
    "Daemon process uptime in seconds",
)

DAEMON_RESTARTS = Counter(
    "quanttrader_daemon_restarts_total",
    "Number of daemon self-restarts",
)

DAEMON_ERRORS = Counter(
    "quanttrader_daemon_errors_total",
    "Daemon loop errors",
    ["error_type"],
)


# ═══════════════════════════════════════════════════════════════════════════
# Helper: record a completed trade
# ═══════════════════════════════════════════════════════════════════════════


def record_trade(
    symbol: str,
    side: str,
    pnl: float,
    exit_reason: str,
    win_rate: float,
) -> None:
    """Record a completed trade into Prometheus metrics."""
    TRADE_COUNT.labels(symbol=symbol, side=side, exit_reason=exit_reason).inc()
    TRADE_PNL.labels(symbol=symbol).observe(pnl)
    TRADE_WIN_RATE.labels(symbol=symbol).set(win_rate)


def record_llm_call(
    provider: str,
    model: str,
    latency: float,
    confidence: float,
    signal: int,
    success: bool = True,
) -> None:
    """Record an LLM API call."""
    status = "success" if success else "error"
    LLM_LATENCY.labels(provider=provider, model=model).observe(latency)
    LLM_CALLS_TOTAL.labels(provider=provider, model=model, status=status).inc()
    sig_label = {1: "buy", 0: "hold", -1: "sell"}.get(signal, "unknown")
    LLM_CONFIDENCE.labels(signal=sig_label).observe(confidence)


def record_risk_event(event_type: str, symbol: str) -> None:
    """Record a risk management event (stop loss, circuit breaker, etc.)."""
    RISK_EVENTS.labels(event_type=event_type, symbol=symbol).inc()


def update_portfolio(
    symbol: str,
    equity: float,
    position_qty: int,
    peak_equity: float,
) -> None:
    """Update portfolio gauges."""
    EQUITY_GAUGE.labels(symbol=symbol).set(equity)
    POSITION_GAUGE.labels(symbol=symbol).set(position_qty)
    if peak_equity > 0:
        dd = (equity / peak_equity - 1.0) * 100
        DRAWDOWN_GAUGE.labels(symbol=symbol).set(dd)


# ═══════════════════════════════════════════════════════════════════════════
# HTTP server for Prometheus scraping
# ═══════════════════════════════════════════════════════════════════════════

_metrics_server_started = False


def start_metrics_server(port: int = 9090) -> None:
    """Start the Prometheus HTTP metrics server on the given port.

    Safe to call multiple times — only starts once.
    """
    global _metrics_server_started
    if _metrics_server_started:
        return
    try:
        start_http_server(port)
        _metrics_server_started = True
        logger.info("Prometheus metrics server started on port %d", port)
    except OSError as e:
        logger.warning("Failed to start metrics server on port %d: %s", port, e)
