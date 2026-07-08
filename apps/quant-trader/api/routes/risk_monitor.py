"""Risk monitoring API routes.

Provides live portfolio risk dashboard endpoints backed by
:class:`~quanttrader.engine.live_risk.LiveRiskMonitor`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...engine.live_risk import LiveRiskMonitor


def register_risk_routes(app, monitor: LiveRiskMonitor, auth) -> None:
    """Register /risk/* endpoints on *app* (a FastAPI instance).

    Parameters
    ----------
    app:
        The FastAPI application.
    monitor:
        A :class:`LiveRiskMonitor` instance (shared with the server).
    auth:
        A FastAPI ``Depends``-compatible auth dependency.
    """
    from fastapi import Depends

    @app.get("/risk/snapshot", dependencies=[Depends(auth)])
    def risk_snapshot():
        """Current risk dashboard: exposure, drawdown, VaR, HHI, positions."""
        monitor.update()
        snap = monitor.snapshot()
        return snap.to_dict()

    @app.get("/risk/history", dependencies=[Depends(auth)])
    def risk_history():
        """Rolling equity curve (up to 500 points) for charting."""
        return {
            "points": monitor.equity_history_points(),
            "count": len(monitor._equity_history),
        }

    @app.get("/risk/alerts", dependencies=[Depends(auth)])
    def risk_alerts():
        """Active risk alerts based on configurable thresholds."""
        monitor.update()
        alerts = monitor.check_alerts()
        return {
            "alerts": [a.to_dict() for a in alerts],
            "count": len(alerts),
        }
