"""quant-trader: a minimal, runnable quantitative trading framework.

Layers:
    data     - market data feeds (Yahoo Finance / synthetic offline)
    strategy - signal generation
    engine   - portfolio accounting + backtest loop + metrics
    broker   - execution adapters (paper + Alpaca live/paper API)
"""

__version__ = "0.6.0"
