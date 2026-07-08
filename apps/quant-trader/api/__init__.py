"""HTTP API layer.

`server.py` exposes the trading engine over REST so external clients (including
other AI agents) can pull market data, run backtests, query the portfolio, and
submit orders/signals.
"""

from .server import create_app

__all__ = ["create_app"]
