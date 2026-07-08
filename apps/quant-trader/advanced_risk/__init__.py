"""Advanced risk management module — VaR, stress testing, dynamic stops, attribution.

Usage:
    from quanttrader.advanced_risk import VaR, StressTest, DynamicStop, RiskAttribution

All classes are standalone; they do NOT touch engine/risk.py or engine/backtest.py.
They read pandas Series/DataFrames and return plain dicts.
"""

from quanttrader.advanced_risk.attribution import RiskAttribution
from quanttrader.advanced_risk.dynamic import DynamicStop
from quanttrader.advanced_risk.stress import StressScenario, StressTest
from quanttrader.advanced_risk.var import VaR, VaRResult

__all__ = [
    "DynamicStop",
    "RiskAttribution",
    "StressScenario",
    "StressTest",
    "VaR",
    "VaRResult",
]
