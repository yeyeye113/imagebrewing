"""Factor computation engine for quantitative analysis.

Usage:
    from quanttrader.factors import FactorEngine
    engine = FactorEngine()
    factor_df = engine.compute_all(ohlcv_df)
"""

from .alternative import (
    AbnormalVolumeFactor,
    BearishEngulfingFactor,
    BollingerBreakoutFactor,
    BullishEngulfingFactor,
    GapUpFactor,
    GoldenCrossFactor,
    HammerFactor,
    InsiderSentimentFactor,
    MACDDivergenceFactor,
    MassDivergenceFactor,
    MoneyFlowIndexFactor,
    MoneyFlowStrengthFactor,
    NetCapitalFlowFactor,
    NewsSentimentFactor,
    NorthboundFlowFactor,
    PriceVolumeDivergenceFactor,
    RSIDivergenceFactor,
    ShootingStarFactor,
    SocialSentimentFactor,
)
from .base import Factor, FactorEngine, FactorResult
from .composite import CompositeFactor
from .fundamental import (
    DebtToAssetFactor,
    DividendYieldFactor,
    EarningsGrowthFactor,
    EbitMarginFactor,
    EquityMultiplierFactor,
    GrossMarginFactor,
    NetMarginFactor,
    OperatingCashflowFactor,
    PBFactor,
    PEFactor,
    PEGFactor,
    PSFactor,
    QuickRatioFactor,
    RevenueGrowthFactor,
    ROEFactor,
    TurnoverFactor,
)
from .ic_analyzer import ICAnalyzer
from .technical import (
    ADFactor,
    ATRBandPositionFactor,
    ATRFactor,
    ATRPctFactor,
    BollingerPositionFactor,
    BollingerWidthFactor,
    CCIFactor,
    DEMAFactor,
    MACDFactor,
    MACDHistogramFactor,
    MassIndexFactor,
    MomentumFactor,
    OBVFactor,
    RSIFactor,
    RSIOverboughtFactor,
    RSIOversoldFactor,
    TRIXFactor,
    VolumeMAFactor,
    VolumePriceTrendFactor,
    VolumeRatioFactor,
    WilliamsRFactor,
)

__all__ = [
    "CompositeFactor",
    "Factor",
    "FactorEngine",
    "FactorResult",
    "ICAnalyzer",
]

# Convenience: auto-register all built-in factors
_BUILT_IN_FACTORS: list[type[Factor]] = [
    # Technical
    MomentumFactor,
    RSIFactor,
    MACDFactor,
    MACDHistogramFactor,
    ATRFactor,
    ATRPctFactor,
    ATRBandPositionFactor,
    BollingerPositionFactor,
    BollingerWidthFactor,
    CCIFactor,
    DEMAFactor,
    MassIndexFactor,
    OBVFactor,
    TRIXFactor,
    VolumeMAFactor,
    VolumeRatioFactor,
    VolumePriceTrendFactor,
    WilliamsRFactor,
    RSIOverboughtFactor,
    RSIOversoldFactor,
    ADFactor,
    # Fundamental
    PEFactor,
    PBFactor,
    PSFactor,
    PEGFactor,
    ROEFactor,
    DebtToAssetFactor,
    EquityMultiplierFactor,
    GrossMarginFactor,
    NetMarginFactor,
    EbitMarginFactor,
    OperatingCashflowFactor,
    QuickRatioFactor,
    RevenueGrowthFactor,
    EarningsGrowthFactor,
    DividendYieldFactor,
    TurnoverFactor,
    # Alternative
    NewsSentimentFactor,
    SocialSentimentFactor,
    InsiderSentimentFactor,
    NorthboundFlowFactor,
    NetCapitalFlowFactor,
    MoneyFlowStrengthFactor,
    MoneyFlowIndexFactor,
    GoldenCrossFactor,
    MACDDivergenceFactor,
    RSIDivergenceFactor,
    PriceVolumeDivergenceFactor,
    MassDivergenceFactor,
    AbnormalVolumeFactor,
    GapUpFactor,
    BullishEngulfingFactor,
    BearishEngulfingFactor,
    BollingerBreakoutFactor,
    HammerFactor,
    ShootingStarFactor,
]


def create_default_engine() -> FactorEngine:
    """Return an engine pre-loaded with all built-in factors."""
    engine = FactorEngine()
    for f in _BUILT_IN_FACTORS:
        engine.register(f())
    return engine
