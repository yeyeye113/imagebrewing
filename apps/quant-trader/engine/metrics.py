from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# 日内 bar 的年化因子按「一个交易日约 6.5 小时」折算（A股/美股主力交易时段近似）。
_INTRADAY_SECONDS_PER_DAY = 6.5 * 3600


def infer_periods_per_year(index) -> int:
    """从 bar 间隔推断年化因子：日线=252，日内按 bar 秒数折算。

    作为全项目年化因子的单一来源，供单标的回测、组合回测、打法回测等所有绩效入口
    共用；无法判断（非时间索引 / 样本不足 / 异常）一律回退日线 252，保证向后兼容。
    """
    try:
        if len(index) >= 2:
            median_sec = pd.Series(index).diff().dropna().dt.total_seconds().median()
            if median_sec and median_sec < 12 * 3600:  # 日内 bar
                return int(max(1, round(TRADING_DAYS * _INTRADAY_SECONDS_PER_DAY / median_sec)))
    except Exception:
        pass
    return TRADING_DAYS  # 日线默认


def performance_summary(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> dict:
    """Compute standard performance stats from an equity curve."""
    equity = equity.dropna()
    if len(equity) < 2:
        return {}

    returns = equity.pct_change().dropna()
    total_return = equity.iloc[-1] / equity.iloc[0] - 1.0

    n_years = len(equity) / periods_per_year
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / n_years) - 1.0 if n_years > 0 else 0.0

    vol = returns.std() * np.sqrt(periods_per_year)
    sharpe = (returns.mean() * periods_per_year) / vol if vol > 0 else 0.0

    # 下行波动率按 Sortino 标准定义：以 0 为目标收益(MAR)、对*全样本*求均方根后年化。
    # 原实现 returns[returns<0].std() 以负收益子集自身均值为基准、分母仅取负样本数，
    # 会系统性低估下行波动、夸大 Sortino——此处修正为规范口径。
    downside_returns = returns.clip(upper=0.0)
    downside = float(np.sqrt((downside_returns**2).mean())) * np.sqrt(periods_per_year)
    sortino = (returns.mean() * periods_per_year) / downside if downside > 0 else 0.0

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_dd = drawdown.min()

    return {
        "start_equity": float(equity.iloc[0]),
        "end_equity": float(equity.iloc[-1]),
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annual_vol": float(vol),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(max_dd),
    }


def trade_stats(fills: list) -> dict:
    """Pair BUY/SELL fills into round-trip trades and compute win/loss stats."""
    trades = []
    open_buy = None
    for f in fills:
        if f.side == "BUY":
            open_buy = f
        elif f.side == "SELL" and open_buy is not None:
            pnl = (f.price - open_buy.price) * f.qty - open_buy.cost - f.cost
            trades.append(pnl)
            open_buy = None

    if not trades:
        return {"n_round_trips": 0}

    wins = [p for p in trades if p > 0]
    losses = [p for p in trades if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = (gross_win / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    return {
        "n_round_trips": len(trades),
        "win_rate": len(wins) / len(trades),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": (avg_win / avg_loss) if avg_loss > 0 else float("inf"),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
    }


def format_summary(stats: dict) -> str:
    if not stats:
        return "(not enough data for performance metrics)"

    def pct(x):
        return f"{x * 100:,.2f}%"

    def money(x):
        return f"${x:,.2f}"

    lines = [
        f"  Start equity : {money(stats['start_equity'])}",
        f"  End equity   : {money(stats['end_equity'])}",
        f"  Total return : {pct(stats['total_return'])}",
        f"  CAGR         : {pct(stats['cagr'])}",
        f"  Annual vol   : {pct(stats['annual_vol'])}",
        f"  Sharpe       : {stats['sharpe']:.2f}",
        f"  Sortino      : {stats['sortino']:.2f}",
        f"  Max drawdown : {pct(stats['max_drawdown'])}",
    ]
    return "\n".join(lines)
