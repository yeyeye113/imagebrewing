"""Risk attribution — decompose portfolio risk into component contributions.

Answers questions like:
  - How much risk does each position contribute?
  - How much of the total risk is idiosyncratic vs systematic?
  - Which positions are the biggest risk drivers?

Methods:
  1. Marginal VaR: contribution of each position to portfolio VaR.
  2. Component VaR: position weight * marginal VaR.
  3. Variance decomposition: systematic vs idiosyncratic risk split.

Usage:
    from quanttrader.advanced_risk.attribution import RiskAttribution

    ra = RiskAttribution(
        positions={"600519": 100, "601318": 200},
        prices=pd.DataFrame(...),
    )
    result = ra.full_attribution()
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class PositionAttribution:
    """Risk attribution for a single position."""

    symbol: str
    weight: float  # portfolio weight
    contribution: float  # % of total risk contributed
    marginal_var: float  # marginal VaR contribution
    component_var: float  # component VaR (= weight * marginal)
    volatility: float  # individual annualized volatility
    beta: float  # beta to portfolio


@dataclass
class AttributionResult:
    """Full portfolio risk attribution result."""

    total_var: float  # portfolio VaR
    total_volatility: float  # annualized portfolio vol
    positions: list[PositionAttribution] = field(default_factory=list)
    systematic_risk_pct: float = 0.0  # % of risk from systematic factor
    idiosyncratic_risk_pct: float = 0.0
    concentration_score: float = 0.0  # 0-1, 1 = fully concentrated
    metadata: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Portfolio VaR(95%): {self.total_var:.4%}",
            f"Annual volatility:  {self.total_volatility:.4%}",
            f"Systematic risk:    {self.systematic_risk_pct:.1f}%",
            f"Idiosyncratic risk: {self.idiosyncratic_risk_pct:.1f}%",
            f"Concentration:      {self.concentration_score:.2f}",
            "",
            "Position breakdown:",
            f"  {'Symbol':<10} {'Weight':>8} {'Contrib':>10} {'Beta':>8} {'Vol':>10}",
            f"  {'─' * 10} {'─' * 8} {'─' * 10} {'─' * 8} {'─' * 10}",
        ]
        for p in sorted(self.positions, key=lambda x: -x.contribution):
            lines.append(
                f"  {p.symbol:<10} {p.weight:>7.1%} {p.contribution:>9.1%} {p.beta:>7.2f} {p.volatility:>9.1%}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "total_var": self.total_var,
            "total_volatility": self.total_volatility,
            "systematic_risk_pct": self.systematic_risk_pct,
            "idiosyncratic_risk_pct": self.idiosyncratic_risk_pct,
            "concentration_score": self.concentration_score,
            "positions": [
                {
                    "symbol": p.symbol,
                    "weight": p.weight,
                    "contribution": p.contribution,
                    "marginal_var": p.marginal_var,
                    "component_var": p.component_var,
                    "volatility": p.volatility,
                    "beta": p.beta,
                }
                for p in self.positions
            ],
            **self.metadata,
        }


class RiskAttribution:
    """Portfolio risk attribution engine.

    Args:
        positions: dict of {symbol: quantity_held}.
        prices: DataFrame with columns = symbols, index = date (close prices).
        confidence: VaR confidence level (default 0.95).
        horizon: VaR horizon in trading days (default 1).
        risk_free_rate: annual risk-free rate.
    """

    def __init__(
        self,
        positions: dict[str, int | float],
        prices: pd.DataFrame,
        confidence: float = 0.95,
        horizon: int = 1,
        risk_free_rate: float = 0.02,
    ):
        self.positions = positions
        self.prices = prices.copy()
        self.confidence = confidence
        self.horizon = horizon
        self.risk_free_rate = risk_free_rate

        missing = set(positions) - set(prices.columns)
        if missing:
            raise ValueError(f"Missing price data for: {missing}")

        # Compute returns and portfolio weights
        self.returns = self.prices.pct_change().dropna()
        self._compute_weights()

    def _compute_weights(self) -> None:
        """Compute portfolio weights from positions and latest prices."""
        last_prices = self.prices.iloc[-1]
        values = {sym: self.positions[sym] * last_prices[sym] for sym in self.positions}
        total = sum(values.values())
        self.weights = {sym: values[sym] / total for sym in values}

    # ── Main attribution ─────────────────────────────────────────────

    def full_attribution(self) -> AttributionResult:
        """Run complete risk attribution: VaR, vol decomposition, concentration."""
        symbols = list(self.positions.keys())
        weight_vec = np.array([self.weights[s] for s in symbols])

        # Covariance matrix
        cov_matrix = self.returns[symbols].cov().values * TRADING_DAYS

        # Portfolio volatility
        port_var = weight_vec @ cov_matrix @ weight_vec
        port_vol = np.sqrt(max(port_var, 0))

        # Portfolio VaR (parametric)
        z = self._norm_ppf(self.confidence)
        port_var_val = port_vol * z * np.sqrt(self.horizon)

        # Individual stats
        individual_vols = np.sqrt(np.diag(cov_matrix))
        portfolio_returns = self.returns[symbols].values @ weight_vec
        port_ret_var = np.var(portfolio_returns) * TRADING_DAYS

        # Betas and attribution
        position_attribs = []
        for i, sym in enumerate(symbols):
            beta = float(cov_matrix[i, :] @ weight_vec / port_var) if port_var > 0 else 0.0
            marginal = float(cov_matrix[i, :] @ weight_vec / np.sqrt(port_var)) if port_var > 0 else 0.0
            component = weight_vec[i] * marginal

            position_attribs.append(
                PositionAttribution(
                    symbol=sym,
                    weight=float(weight_vec[i]),
                    contribution=0.0,  # filled below
                    marginal_var=float(marginal * z),
                    component_var=float(component * z),
                    volatility=float(individual_vols[i]),
                    beta=beta,
                )
            )

        # Normalize contributions to sum to 100%
        total_component = sum(p.component_var for p in position_attribs)
        if total_component > 0:
            for p in position_attribs:
                p.contribution = p.component_var / total_component

        # Systematic vs idiosyncratic decomposition
        sys_pct, idio_pct = self._systematic_idio_split(symbols, weight_vec, cov_matrix)

        # Concentration score (Herfindahl index, normalized)
        hhi = sum(w**2 for w in weight_vec)
        concentration = (hhi - 1 / len(symbols)) / (1 - 1 / len(symbols)) if len(symbols) > 1 else 1.0

        return AttributionResult(
            total_var=float(port_var_val),
            total_volatility=float(port_vol),
            positions=position_attribs,
            systematic_risk_pct=float(sys_pct * 100),
            idiosyncratic_risk_pct=float(idio_pct * 100),
            concentration_score=float(np.clip(concentration, 0, 1)),
            metadata={"n_symbols": len(symbols), "confidence": self.confidence},
        )

    # ── Marginal VaR ranking ─────────────────────────────────────────

    def marginal_var_ranking(self) -> list[dict]:
        """Rank positions by marginal VaR contribution (most to least risky)."""
        result = self.full_attribution()
        ranked = sorted(result.positions, key=lambda p: -abs(p.marginal_var))
        return [
            {
                "rank": i + 1,
                "symbol": p.symbol,
                "marginal_var": p.marginal_var,
                "weight": p.weight,
                "beta": p.beta,
                "volatility": p.volatility,
            }
            for i, p in enumerate(ranked)
        ]

    # ── Scenario-based attribution ───────────────────────────────────

    def scenario_attribution(self, shock_pct: float = -0.10) -> list[dict]:
        """Attribute losses under a uniform market shock.

        Args:
            shock_pct: market-wide shock (e.g. -0.10 for a 10% drop).
        """
        symbols = list(self.positions.keys())
        last_prices = self.prices.iloc[-1]

        losses = []
        for sym in symbols:
            position_value = self.positions[sym] * last_prices[sym]
            loss = position_value * shock_pct
            losses.append(
                {
                    "symbol": sym,
                    "position_value": position_value,
                    "loss": loss,
                    "loss_pct": shock_pct,
                }
            )

        total_loss = sum(l["loss"] for l in losses)
        for l in losses:
            l["contribution_pct"] = l["loss"] / total_loss if total_loss != 0 else 0

        return sorted(losses, key=lambda l: l["loss"])

    # ── Systematic / idiosyncratic split ─────────────────────────────

    def _systematic_idio_split(
        self,
        symbols: list[str],
        weights: np.ndarray,
        cov_matrix: np.ndarray,
    ) -> tuple[float, float]:
        """Decompose risk into systematic vs idiosyncratic.

        Uses the single-factor model approximation:
          - Systematic = beta^2 * sigma_m^2 (market risk)
          - Idiosyncratic = sigma_e^2 (stock-specific risk)
        """
        # Portfolio return variance
        port_var = weights @ cov_matrix @ weights

        # Average pairwise correlation as proxy for systematic exposure
        n = len(symbols)
        if n < 2:
            return 1.0, 0.0

        # Extract individual variances and correlations
        vols = np.sqrt(np.diag(cov_matrix))
        corr_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if vols[i] > 0 and vols[j] > 0:
                    corr_matrix[i, j] = cov_matrix[i, j] / (vols[i] * vols[j])

        # Weighted average correlation (proxy for R-squared)
        weight_sq = weights**2
        avg_corr = 0.0
        count = 0
        for i in range(n):
            for j in range(n):
                if i != j:
                    avg_corr += weight_sq[i] * weight_sq[j] * corr_matrix[i, j]
                    count += 1
        avg_corr = avg_corr / count if count > 0 else 0

        # Systematic fraction ≈ weighted avg correlation
        sys_pct = max(0, min(1, avg_corr))
        idio_pct = 1 - sys_pct

        return sys_pct, idio_pct

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _norm_ppf(p: float) -> float:
        """Rational approximation for normal inverse CDF."""
        if p <= 0 or p >= 1:
            raise ValueError(f"p must be in (0,1), got {p}")
        if p < 0.5:
            return -RiskAttribution._norm_ppf(1 - p)
        t = np.sqrt(-2 * np.log(1 - p))
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308
        return float(t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t))
