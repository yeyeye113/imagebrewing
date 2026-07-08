"""Position sizing and portfolio capital allocation.

Encodes professional discipline:
- Never deploy 100% of capital on one signal (cash reserve + exposure caps).
- Cap single-name weight in both single-asset and multi-asset contexts.
- Offer several allocation schemes (equal, inverse-vol / risk parity, min-variance).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .risk import RiskConfig


@dataclass
class SizingConfig:
    """Limits on how much capital may be deployed.

    All values are fractions (0.30 == 30%). Set to 1.0 to effectively disable a cap.
    """

    max_position_pct: float = 0.30  # single position <= 30% of equity
    max_total_exposure: float = 0.80  # total invested <= 80% of equity
    cash_reserve_pct: float = 0.20  # always keep >= 20% cash
    max_weight_per_symbol: float = 0.25  # portfolio sleeve weight cap per symbol
    allow_leverage: bool = False  # False = NEVER spend more than cash on hand
    target_volatility: float = 0.0  # 0 = off; e.g. 0.20 = target 20% annualized vol
    vol_lookback: int = 20  # bars used to estimate realized volatility

    def enabled(self) -> bool:
        return (
            any(
                v < 1.0
                for v in (
                    self.max_position_pct,
                    self.max_total_exposure,
                    self.cash_reserve_pct,
                    self.max_weight_per_symbol,
                )
            )
            or not self.allow_leverage
            or self.target_volatility > 0
        )


def annualized_vol(prices: pd.Series, lookback: int = 20, periods_per_year: int = 252) -> float:
    """Realized annualized volatility from the last ``lookback`` returns."""
    ret = prices.pct_change().dropna().tail(max(2, lookback))
    if len(ret) < 2:
        return 0.0
    return float(ret.std() * (periods_per_year**0.5))


def compute_entry_notional(
    equity: float,
    cash: float,
    position_value: float,
    order_size: float,
    sizing: SizingConfig,
    risk: RiskConfig,
    total_invested: float | None = None,
    volatility: float | None = None,
) -> float:
    """Return dollar amount to deploy on a new long (minimum of all caps).

    Layers (the binding one wins — we take the minimum):
    1. Usable cash after the mandatory reserve, times the per-signal fraction.
    2. Risk-based sizing when stop_loss + risk_per_trade are set.
    3. Volatility-target sizing (``target_volatility``) when a vol estimate is given.
    4. Single-position ceiling (``max_position_pct``).
    5. Portfolio exposure ceiling (``max_total_exposure``) — uses *total* invested
       across all holdings, so adding new names can't quietly breach the cap.
    6. NO LEVERAGE: never spend more than cash on hand (unless allow_leverage).

    ``total_invested`` is the gross value of *all* open positions (defaults to
    ``position_value`` for the single-asset case). ``volatility`` is the asset's
    annualized realized vol, used only when ``target_volatility`` is set.
    """
    if equity <= 0 or cash <= 0:
        return 0.0
    if total_invested is None:
        total_invested = position_value

    min_cash = equity * sizing.cash_reserve_pct
    usable_cash = max(0.0, cash - min_cash)
    candidates = [usable_cash * order_size]

    # No leverage: hard-cap every order at the cash actually available.
    if not sizing.allow_leverage:
        candidates.append(cash)

    if risk.stop_loss and risk.risk_per_trade:
        candidates.append(equity * risk.risk_per_trade / risk.stop_loss)

    # Volatility targeting: smaller positions in choppy names, larger in calm ones.
    if sizing.target_volatility > 0 and volatility and volatility > 0:
        candidates.append(equity * sizing.target_volatility / volatility)

    room_position = max(0.0, equity * sizing.max_position_pct - position_value)
    candidates.append(room_position)

    # Portfolio-wide exposure room (prevents cross-symbol over-investment).
    room_exposure = max(0.0, equity * sizing.max_total_exposure - total_invested)
    candidates.append(room_exposure)

    return max(0.0, min(candidates))


def confidence_sized_notional(
    base_notional: float,
    confidence: float,
    min_pct: float = 0.3,
    threshold: float = 0.5,
) -> float:
    """Scale position size by LLM confidence.

    Logic: 高确信=大仓，低确信=小仓。
    - confidence <= threshold → use min_pct of base_notional
    - confidence = 1.0        → use 100% of base_notional
    - linear mapping in between

    Example: min_pct=0.3, threshold=0.5
        confidence 0.55 → 36%仓位
        confidence 0.70 → 58%仓位
        confidence 0.90 → 94%仓位
    """
    if confidence <= threshold:
        return base_notional * min_pct
    scale = min_pct + (1.0 - min_pct) * (confidence - threshold) / (1.0 - threshold)
    return base_notional * max(min_pct, min(1.0, scale))


def _equal_weights(symbols: list[str]) -> dict[str, float]:
    w = 1.0 / len(symbols)
    return {s: w for s in symbols}


def _inverse_vol_weights(prices_by_symbol: dict[str, pd.DataFrame]) -> dict[str, float]:
    inv: dict[str, float] = {}
    for sym, df in prices_by_symbol.items():
        ret = df["close"].pct_change().dropna()
        vol = float(ret.std())
        inv[sym] = (1.0 / vol) if vol > 0 else 0.0
    total = sum(inv.values())
    if total <= 0:
        return _equal_weights(list(prices_by_symbol))
    return {s: v / total for s, v in inv.items()}


def _min_variance_weights(prices_by_symbol: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Simplified min-variance: weight inversely to variance (vol^2)."""
    inv: dict[str, float] = {}
    for sym, df in prices_by_symbol.items():
        ret = df["close"].pct_change().dropna()
        var = float(ret.var())
        inv[sym] = (1.0 / var) if var > 0 else 0.0
    total = sum(inv.values())
    if total <= 0:
        return _equal_weights(list(prices_by_symbol))
    return {s: v / total for s, v in inv.items()}


def _apply_weight_caps(weights: dict[str, float], sizing: SizingConfig) -> dict[str, float]:
    """Cap per-symbol weight; total may be < investable when caps bind (rest stays cash)."""
    if not weights:
        return weights

    investable = max(0.0, 1.0 - sizing.cash_reserve_pct)
    total = sum(weights.values())
    if total <= 0:
        n = len(weights)
        return {s: min(investable / n, sizing.max_weight_per_symbol) for s in weights}

    scaled = {s: w / total * investable for s, w in weights.items()}
    capped = {s: min(w, sizing.max_weight_per_symbol) for s, w in scaled.items()}
    cap_sum = sum(capped.values())
    if cap_sum > investable:
        f = investable / cap_sum
        return {s: w * f for s, w in capped.items()}
    return capped


def compute_portfolio_weights(
    prices_by_symbol: dict[str, pd.DataFrame],
    method: str = "equal",
    sizing: SizingConfig | None = None,
) -> dict[str, float]:
    """Scientific capital allocation across symbols.

    Methods:
    - equal          : 1/N
    - inverse_vol, inv_vol, risk_parity : inverse daily-return volatility
    - min_variance   : inverse variance (more conservative on high-vol names)
    """
    sizing = sizing or SizingConfig()
    method = (method or "equal").lower()

    if method in ("inverse_vol", "inv_vol", "risk_parity", "riskparity"):
        raw = _inverse_vol_weights(prices_by_symbol)
    elif method in ("min_variance", "minvar", "min_var"):
        raw = _min_variance_weights(prices_by_symbol)
    else:
        raw = _equal_weights(list(prices_by_symbol))

    return _apply_weight_caps(raw, sizing)
