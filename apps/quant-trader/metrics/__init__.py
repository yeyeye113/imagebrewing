"""Prometheus metrics collectors for quanttrader.

Exposes trading metrics via /metrics endpoint for Prometheus scraping.
Metrics: trade count, PnL, win rate, LLM latency, scanner duration, risk events.
"""

from .collectors import (
    DRAWDOWN_GAUGE,
    EQUITY_GAUGE,
    LLM_CALLS_TOTAL,
    LLM_LATENCY,
    POSITION_GAUGE,
    RISK_EVENTS,
    SCANNER_DURATION,
    SCANNER_STOCKS_FOUND,
    TRADE_COUNT,
    TRADE_PNL,
    TRADE_WIN_RATE,
    start_metrics_server,
)

__all__ = [
    "DRAWDOWN_GAUGE",
    "EQUITY_GAUGE",
    "LLM_CALLS_TOTAL",
    "LLM_LATENCY",
    "POSITION_GAUGE",
    "RISK_EVENTS",
    "SCANNER_DURATION",
    "SCANNER_STOCKS_FOUND",
    "TRADE_COUNT",
    "TRADE_PNL",
    "TRADE_WIN_RATE",
    "start_metrics_server",
]
