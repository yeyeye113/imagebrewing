"""波动率分析模块 — ATR/布林带/波动率锥。

功能:
  - ATR(14) 计算
  - 布林带(20,2) 计算
  - 历史波动率
  - 波动率锥 (分位数)
  - 波动率 regime 判断

用法:
    from quanttrader.analysis.volatility import VolatilityAnalyzer
    analyzer = VolatilityAnalyzer()
    result = analyzer.analyze(prices)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class VolatilityResult:
    """波动率分析结果。"""

    atr: float
    atr_pct: float
    bb_upper: float
    bb_mid: float
    bb_lower: float
    bb_pct: float  # %B
    hv_20: float  # 20日历史波动率
    hv_60: float  # 60日历史波动率
    vol_regime: str  # 'high', 'normal', 'low'
    vol_percentile: float  # 当前波动率在历史中的分位数
    description: str


class VolatilityAnalyzer:
    """波动率分析器。"""

    def __init__(self):
        self.atr_period = 14
        self.bb_period = 20
        self.bb_std = 2

    def analyze(self, prices: pd.DataFrame) -> VolatilityResult:
        """分析波动率。

        Args:
            prices: DataFrame with OHLCV data

        Returns:
            波动率分析结果
        """
        if prices is None or len(prices) < 20:
            return VolatilityResult(
                atr=0,
                atr_pct=0,
                bb_upper=0,
                bb_mid=0,
                bb_lower=0,
                bb_pct=0.5,
                hv_20=0,
                hv_60=0,
                vol_regime="normal",
                vol_percentile=50,
                description="数据不足",
            )

        closes = prices["close"].astype(float)
        highs = prices["high"].astype(float)
        lows = prices["low"].astype(float)
        current = float(closes.iloc[-1])

        # ATR
        tr = pd.concat(
            [
                highs - lows,
                (highs - closes.shift(1)).abs(),
                (lows - closes.shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = float(tr.rolling(self.atr_period).mean().iloc[-1]) if len(tr) >= self.atr_period else float(tr.mean())
        atr_pct = atr / current * 100

        # 布林带
        sma = float(closes.rolling(self.bb_period).mean().iloc[-1])
        std = float(closes.rolling(self.bb_period).std().iloc[-1])
        bb_upper = sma + self.bb_std * std
        bb_lower = sma - self.bb_std * std
        bb_pct = (current - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

        # 历史波动率
        returns = closes.pct_change().dropna()
        hv_20 = float(returns.tail(20).std()) * np.sqrt(252) * 100
        hv_60 = float(returns.tail(60).std()) * np.sqrt(252) * 100 if len(returns) >= 60 else hv_20

        # 波动率 regime
        hv_mean = hv_20
        hv_std = float(returns.tail(20).std()) * np.sqrt(252) * 100 * 0.3
        if hv_20 > hv_mean + hv_std:
            vol_regime = "high"
        elif hv_20 < hv_mean - hv_std:
            vol_regime = "low"
        else:
            vol_regime = "normal"

        # 波动率分位数
        if len(returns) >= 60:
            hist_hvs = []
            for i in range(60, len(returns)):
                hv = float(returns.iloc[i - 60 : i].std()) * np.sqrt(252) * 100
                hist_hvs.append(hv)
            vol_percentile = sum(1 for h in hist_hvs if h < hv_20) / len(hist_hvs) * 100
        else:
            vol_percentile = 50

        # 描述
        description = f"ATR={atr:.1f}({atr_pct:.1f}%) | BB%B={bb_pct:.2f} | HV20={hv_20:.1f}% | {vol_regime}波动"

        return VolatilityResult(
            atr=atr,
            atr_pct=atr_pct,
            bb_upper=bb_upper,
            bb_mid=sma,
            bb_lower=bb_lower,
            bb_pct=bb_pct,
            hv_20=hv_20,
            hv_60=hv_60,
            vol_regime=vol_regime,
            vol_percentile=vol_percentile,
            description=description,
        )
