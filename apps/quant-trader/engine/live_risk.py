"""Live (paper/real-time) risk monitoring for running portfolios.

Computes rolling portfolio risk metrics from broker state without needing
a full backtest. Designed to be polled via the API ``/risk/*`` endpoints.
"""
from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from ..broker.base import Broker, Position

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PositionRiskDetail:
    """Per-position risk snapshot."""
    symbol: str
    qty: float
    avg_price: float
    current_price: float
    market_value: float
    weight: float  # fraction of total equity
    unrealized_pnl: float
    unrealized_pnl_pct: float


@dataclass
class LiveRiskSnapshot:
    """Serializable risk dashboard snapshot."""
    timestamp: str
    equity: float
    cash: float
    total_position_value: float
    exposure_pct: float  # total_position_value / equity
    cash_pct: float
    positions: list[PositionRiskDetail]
    concentration_hhi: float  # Herfindahl-Hirschman Index of position weights
    portfolio_var_95_1d: float  # 95% 1-day VaR (dollar)
    portfolio_var_95_1d_pct: float
    current_drawdown: float  # fraction, negative (e.g. -0.05 = -5%)
    peak_equity: float
    rolling_volatility: float  # annualized, from equity history
    n_positions: int
    risk_score: int  # 0-100 composite
    risk_grade: str  # A/B/C/D

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "equity": round(self.equity, 2),
            "cash": round(self.cash, 2),
            "total_position_value": round(self.total_position_value, 2),
            "exposure_pct": round(self.exposure_pct, 4),
            "cash_pct": round(self.cash_pct, 4),
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": round(p.qty, 6),
                    "avg_price": round(p.avg_price, 4),
                    "current_price": round(p.current_price, 4),
                    "market_value": round(p.market_value, 2),
                    "weight": round(p.weight, 4),
                    "unrealized_pnl": round(p.unrealized_pnl, 2),
                    "unrealized_pnl_pct": round(p.unrealized_pnl_pct, 4),
                }
                for p in self.positions
            ],
            "concentration_hhi": round(self.concentration_hhi, 4),
            "portfolio_var_95_1d": round(self.portfolio_var_95_1d, 2),
            "portfolio_var_95_1d_pct": round(self.portfolio_var_95_1d_pct, 4),
            "current_drawdown": round(self.current_drawdown, 4),
            "peak_equity": round(self.peak_equity, 2),
            "rolling_volatility": round(self.rolling_volatility, 4),
            "n_positions": self.n_positions,
            "risk_score": self.risk_score,
            "risk_grade": self.risk_grade,
        }


@dataclass
class RiskAlert:
    """A single threshold-violation alert."""
    level: str  # "warning" | "critical"
    code: str  # e.g. "DRAWDOWN", "EXPOSURE", "CONCENTRATION", "VAR"
    message: str
    value: float
    threshold: float
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "value": round(self.value, 4),
            "threshold": round(self.threshold, 4),
            "timestamp": self.timestamp,
        }


@dataclass
class RiskThresholds:
    """Configurable alert thresholds (all fractions)."""
    max_drawdown_warning: float = -0.10  # -10%
    max_drawdown_critical: float = -0.20  # -20%
    max_exposure_warning: float = 0.85  # 85%
    max_exposure_critical: float = 0.95  # 95%
    max_concentration_hhi: float = 0.35  # HHI > 0.35 means concentrated
    max_position_weight: float = 0.40  # single position > 40%
    max_var_pct_warning: float = 0.05  # VaR > 5% of equity
    min_cash_pct: float = 0.05  # cash < 5%


TRADING_DAYS = 252
VAR_Z_95 = 1.645


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class LiveRiskMonitor:
    """Real-time risk monitor that wraps a broker and maintains a rolling
    equity curve for drawdown / volatility / VaR computation.

    Usage::

        monitor = LiveRiskMonitor(broker)
        # call update() periodically (e.g. each API poll or timer tick)
        monitor.update()
        snapshot = monitor.snapshot()
        alerts = monitor.check_alerts()
    """

    def __init__(
        self,
        broker: Broker,
        thresholds: RiskThresholds | None = None,
        equity_history_maxlen: int = 500,
        price_fn: Callable[[str], float] | None = None,
    ):
        self._broker = broker
        self._thresholds = thresholds or RiskThresholds()
        self._equity_history: deque[float] = deque(maxlen=equity_history_maxlen)
        self._timestamps: deque[str] = deque(maxlen=equity_history_maxlen)
        self._peak_equity: float = 0.0
        self._price_fn = price_fn  # optional override for fetching prices

    # -- data refresh ------------------------------------------------------

    def update(self) -> None:
        """Record the current equity into the rolling history."""
        acct = self._broker.get_account()
        eq = acct.equity
        self._equity_history.append(eq)
        self._timestamps.append(
            datetime.now(UTC).isoformat(timespec="seconds"),
        )
        if eq > self._peak_equity:
            self._peak_equity = eq

    def push_equity(self, equity: float, ts: str = "") -> None:
        """Manually inject an equity point (for testing or external feeds)."""
        self._equity_history.append(equity)
        self._timestamps.append(ts or datetime.now(UTC).isoformat(timespec="seconds"))
        if equity > self._peak_equity:
            self._peak_equity = equity

    # -- helpers -----------------------------------------------------------

    def _get_price(self, symbol: str) -> float:
        if self._price_fn:
            return self._price_fn(symbol)
        return self._broker.last_price(symbol)

    def _positions(self) -> list[Position]:
        return list(getattr(self._broker, "_positions", {}).values())

    def _rolling_vol(self) -> float:
        """Annualized volatility from equity history returns."""
        eq = list(self._equity_history)
        if len(eq) < 3:
            return 0.0
        arr = np.array(eq, dtype=float)
        rets = np.diff(arr) / arr[:-1]
        rets = rets[np.isfinite(rets)]
        if len(rets) < 2:
            return 0.0
        return float(np.std(rets, ddof=1) * np.sqrt(TRADING_DAYS))

    def _portfolio_var(self, equity: float, vol: float) -> tuple[float, float]:
        """Return (var_dollar, var_pct)."""
        var_dollar = equity * vol / math.sqrt(TRADING_DAYS) * VAR_Z_95
        var_pct = var_dollar / equity if equity else 0.0
        return var_dollar, var_pct

    # -- public API --------------------------------------------------------

    def snapshot(self) -> LiveRiskSnapshot:
        """Build a full risk snapshot from current broker state."""
        acct = self._broker.get_account()
        equity = acct.equity
        cash = acct.cash
        positions_raw = self._positions()

        # Per-position detail
        details: list[PositionRiskDetail] = []
        total_pos_value = 0.0
        for pos in positions_raw:
            try:
                price = self._get_price(pos.symbol)
            except Exception:
                price = pos.avg_price
            mv = pos.qty * price
            total_pos_value += mv
            pnl = (price - pos.avg_price) * pos.qty
            pnl_pct = (price / pos.avg_price - 1) if pos.avg_price else 0.0
            details.append(PositionRiskDetail(
                symbol=pos.symbol,
                qty=pos.qty,
                avg_price=pos.avg_price,
                current_price=price,
                market_value=mv,
                weight=0.0,  # filled below
                unrealized_pnl=pnl,
                unrealized_pnl_pct=pnl_pct,
            ))

        # Weights
        for d in details:
            d.weight = d.market_value / equity if equity else 0.0

        exposure_pct = total_pos_value / equity if equity else 0.0
        cash_pct = cash / equity if equity else 0.0

        # HHI
        weights = [d.weight for d in details]
        hhi = sum(w ** 2 for w in weights)

        # Drawdown
        peak = max(self._peak_equity, equity) if self._peak_equity else equity
        drawdown = (equity / peak - 1.0) if peak else 0.0

        # Volatility & VaR
        vol = self._rolling_vol()
        var_dollar, var_pct = self._portfolio_var(equity, vol)

        # Risk score
        score, grade = _score_live_risk(
            exposure_pct, cash_pct, drawdown, hhi, weights, var_pct,
        )

        now = datetime.now(UTC).isoformat(timespec="seconds")
        return LiveRiskSnapshot(
            timestamp=now,
            equity=equity,
            cash=cash,
            total_position_value=total_pos_value,
            exposure_pct=exposure_pct,
            cash_pct=cash_pct,
            positions=details,
            concentration_hhi=hhi,
            portfolio_var_95_1d=var_dollar,
            portfolio_var_95_1d_pct=var_pct,
            current_drawdown=drawdown,
            peak_equity=peak,
            rolling_volatility=vol,
            n_positions=len(details),
            risk_score=score,
            risk_grade=grade,
        )

    def check_alerts(self) -> list[RiskAlert]:
        """Evaluate thresholds and return active alerts."""
        snap = self.snapshot()
        th = self._thresholds
        now = snap.timestamp
        alerts: list[RiskAlert] = []

        # Drawdown
        if snap.current_drawdown <= th.max_drawdown_critical:
            alerts.append(RiskAlert(
                level="critical", code="DRAWDOWN",
                message=f"回撤 {snap.current_drawdown:.1%} 触及熔断线 {th.max_drawdown_critical:.0%}",
                value=snap.current_drawdown, threshold=th.max_drawdown_critical, timestamp=now,
            ))
        elif snap.current_drawdown <= th.max_drawdown_warning:
            alerts.append(RiskAlert(
                level="warning", code="DRAWDOWN",
                message=f"回撤 {snap.current_drawdown:.1%} 超过预警线 {th.max_drawdown_warning:.0%}",
                value=snap.current_drawdown, threshold=th.max_drawdown_warning, timestamp=now,
            ))

        # Exposure
        if snap.exposure_pct >= th.max_exposure_critical:
            alerts.append(RiskAlert(
                level="critical", code="EXPOSURE",
                message=f"总暴露 {snap.exposure_pct:.1%} 超过临界 {th.max_exposure_critical:.0%}",
                value=snap.exposure_pct, threshold=th.max_exposure_critical, timestamp=now,
            ))
        elif snap.exposure_pct >= th.max_exposure_warning:
            alerts.append(RiskAlert(
                level="warning", code="EXPOSURE",
                message=f"总暴露 {snap.exposure_pct:.1%} 超过预警 {th.max_exposure_warning:.0%}",
                value=snap.exposure_pct, threshold=th.max_exposure_warning, timestamp=now,
            ))

        # Concentration
        if snap.concentration_hhi >= th.max_concentration_hhi:
            alerts.append(RiskAlert(
                level="warning", code="CONCENTRATION",
                message=f"集中度 HHI={snap.concentration_hhi:.2f} 超过阈值 {th.max_concentration_hhi:.2f}",
                value=snap.concentration_hhi, threshold=th.max_concentration_hhi, timestamp=now,
            ))

        # Single position weight
        for pos in snap.positions:
            if pos.weight >= th.max_position_weight:
                alerts.append(RiskAlert(
                    level="warning", code="POSITION_WEIGHT",
                    message=f"{pos.symbol} 仓位权重 {pos.weight:.1%} 超过 {th.max_position_weight:.0%}",
                    value=pos.weight, threshold=th.max_position_weight, timestamp=now,
                ))

        # VaR
        if snap.portfolio_var_95_1d_pct >= th.max_var_pct_warning:
            alerts.append(RiskAlert(
                level="warning", code="VAR",
                message=f"日 VaR {snap.portfolio_var_95_1d_pct:.1%} 超过预警 {th.max_var_pct_warning:.0%}",
                value=snap.portfolio_var_95_1d_pct, threshold=th.max_var_pct_warning, timestamp=now,
            ))

        # Cash
        if snap.n_positions > 0 and snap.cash_pct < th.min_cash_pct:
            alerts.append(RiskAlert(
                level="warning", code="LOW_CASH",
                message=f"现金比例 {snap.cash_pct:.1%} 低于最低线 {th.min_cash_pct:.0%}",
                value=snap.cash_pct, threshold=th.min_cash_pct, timestamp=now,
            ))

        return alerts

    def equity_history_points(self) -> list[dict]:
        """Return the rolling equity curve as a list of {time, equity} dicts."""
        return [
            {"time": ts, "equity": round(eq, 2)}
            for ts, eq in zip(self._timestamps, self._equity_history)
        ]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_live_risk(
    exposure_pct: float,
    cash_pct: float,
    drawdown: float,
    hhi: float,
    weights: list[float],
    var_pct: float,
) -> tuple[int, str]:
    """Composite risk score 0-100, mapped to A/B/C/D grade."""
    score = 100

    # Drawdown penalty (heaviest)
    if drawdown < -0.25:
        score -= 30
    elif drawdown < -0.15:
        score -= 20
    elif drawdown < -0.10:
        score -= 10
    elif drawdown < -0.05:
        score -= 5

    # Exposure
    if exposure_pct > 0.95:
        score -= 20
    elif exposure_pct > 0.85:
        score -= 10
    elif exposure_pct > 0.75:
        score -= 5

    # Cash
    if cash_pct < 0.05:
        score -= 15
    elif cash_pct < 0.10:
        score -= 8
    elif cash_pct < 0.15:
        score -= 3

    # Concentration
    if hhi > 0.50:
        score -= 15
    elif hhi > 0.35:
        score -= 8

    # Single position overweight
    max_w = max(weights) if weights else 0.0
    if max_w > 0.50:
        score -= 15
    elif max_w > 0.40:
        score -= 8

    # VaR
    if var_pct > 0.08:
        score -= 10
    elif var_pct > 0.05:
        score -= 5

    score = max(0, min(100, score))
    if score >= 80:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 40:
        grade = "C"
    else:
        grade = "D"
    return score, grade
