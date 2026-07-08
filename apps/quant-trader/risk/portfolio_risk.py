"""组合风险控制 — 多品种组合风险管理。

功能:
  - 相关性检查
  - 行业集中度
  - 总仓位控制
  - 风险预警

用法:
    from quanttrader.risk.portfolio_risk import PortfolioRiskManager
    manager = PortfolioRiskManager()
    result = manager.check_risk(positions)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np


@dataclass
class RiskCheckResult:
    """风险检查结果。"""

    risk_level: str  # 'low', 'medium', 'high', 'critical'
    warnings: list[str]
    suggestions: list[str]
    max_position_pct: float
    sector_concentration: dict[str, float]
    correlation_risk: float


class PortfolioRiskManager:
    """组合风险管理器。"""

    # 板块分类
    SECTORS: ClassVar[dict[str, list[str]]] = {
        "黑色系": ["I", "RB", "HC"],
        "能化": ["SC", "FU", "TA", "MA", "SA", "BU", "EG", "EB"],
        "贵金属": ["AU", "AG"],
        "有色": ["CU", "AL", "ZN", "NI", "SN", "SS"],
        "农产品": ["M", "P", "Y", "A", "RM", "C", "CS"],
        "金融": ["IF", "IC", "IH", "IM", "T", "TF", "TS"],
    }

    # 相关性矩阵 (简化)
    CORRELATIONS: ClassVar[dict[tuple[str, str], float]] = {
        ("I", "RB"): 0.8,
        ("I", "HC"): 0.7,
        ("RB", "HC"): 0.9,
        ("AU", "AG"): 0.9,
        ("CU", "AL"): 0.7,
        ("CU", "ZN"): 0.8,
        ("SC", "FU"): 0.8,
        ("SC", "TA"): 0.6,
        ("MA", "TA"): 0.7,
        ("M", "P"): 0.6,
        ("M", "Y"): 0.7,
        ("P", "Y"): 0.8,
    }

    def __init__(self, max_total_exposure: float = 0.8, max_sector_exposure: float = 0.4):
        self.max_total_exposure = max_total_exposure
        self.max_sector_exposure = max_sector_exposure

    def check_risk(self, positions: dict[str, float]) -> RiskCheckResult:
        """检查组合风险。

        Args:
            positions: {品种: 仓位比例}

        Returns:
            风险检查结果
        """
        warnings = []
        suggestions = []

        # 1. 总仓位检查
        total_exposure = sum(positions.values())
        if total_exposure > self.max_total_exposure:
            warnings.append(f"总仓位过高({total_exposure * 100:.0f}% > {self.max_total_exposure * 100:.0f}%)")
            suggestions.append("建议减仓至80%以下")

        # 2. 行业集中度检查
        sector_exposure = self._calculate_sector_exposure(positions)
        for sector, exposure in sector_exposure.items():
            if exposure > self.max_sector_exposure:
                warnings.append(f"{sector}板块集中度过高({exposure * 100:.0f}%)")
                suggestions.append(f"建议分散{sector}板块仓位")

        # 3. 相关性检查
        correlation_risk = self._calculate_correlation_risk(positions)
        if correlation_risk > 0.7:
            warnings.append(f"品种相关性过高({correlation_risk:.2f})")
            suggestions.append("建议增加低相关品种")

        # 4. 单品种仓位检查
        for symbol, pct in positions.items():
            if pct > 0.3:
                warnings.append(f"{symbol}仓位过重({pct * 100:.0f}%)")
                suggestions.append(f"建议降低{symbol}仓位至30%以下")

        # 风险等级
        risk_level = self._determine_risk_level(warnings, correlation_risk, total_exposure)

        return RiskCheckResult(
            risk_level=risk_level,
            warnings=warnings,
            suggestions=suggestions,
            max_position_pct=max(positions.values()) if positions else 0,
            sector_concentration=sector_exposure,
            correlation_risk=correlation_risk,
        )

    def _calculate_sector_exposure(self, positions: dict[str, float]) -> dict[str, float]:
        """计算行业集中度。"""
        sector_exposure = {sector: 0.0 for sector in self.SECTORS}

        for symbol, pct in positions.items():
            for sector, symbols in self.SECTORS.items():
                if symbol in symbols:
                    sector_exposure[sector] += pct
                    break

        return sector_exposure

    def _calculate_correlation_risk(self, positions: dict[str, float]) -> float:
        """计算相关性风险。"""
        if len(positions) < 2:
            return 0

        symbols = list(positions.keys())
        correlations = []

        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                pair = (symbols[i], symbols[j])
                reverse_pair = (symbols[j], symbols[i])

                if pair in self.CORRELATIONS:
                    correlations.append(self.CORRELATIONS[pair])
                elif reverse_pair in self.CORRELATIONS:
                    correlations.append(self.CORRELATIONS[reverse_pair])
                else:
                    # 默认中等相关性
                    correlations.append(0.5)

        return np.mean(correlations) if correlations else 0

    def _determine_risk_level(
        self,
        warnings: list[str],
        correlation_risk: float,
        total_exposure: float,
    ) -> str:
        """确定风险等级。"""
        if len(warnings) >= 3 or correlation_risk > 0.8 or total_exposure > 0.9:
            return "critical"
        elif len(warnings) >= 2 or correlation_risk > 0.7 or total_exposure > 0.8:
            return "high"
        elif len(warnings) >= 1 or correlation_risk > 0.6:
            return "medium"
        else:
            return "low"

    def suggest_position_size(
        self,
        capital: float,
        risk_per_trade: float,
        stop_loss_distance: float,
    ) -> float:
        """建议仓位大小。

        Args:
            capital: 总资金
            risk_per_trade: 单笔风险比例 (如0.02 = 2%)
            stop_loss_distance: 止损距离 (如0.03 = 3%)

        Returns:
            建议仓位金额
        """
        # 单笔风险金额
        risk_amount = capital * risk_per_trade

        # 仓位大小
        position_size = risk_amount / stop_loss_distance if stop_loss_distance > 0 else 0

        # 最大仓位限制
        max_position = capital * 0.2  # 最大20%

        return min(position_size, max_position)

    def calculate_portfolio_risk(
        self,
        positions: dict[str, float],
        volatilities: dict[str, float],
    ) -> float:
        """计算组合风险 (简化版VaR)。

        Args:
            positions: {品种: 仓位比例}
            volatilities: {品种: 波动率}

        Returns:
            组合风险值
        """
        if not positions:
            return 0

        # 计算加权波动率
        weighted_vol = 0.0
        for symbol, pct in positions.items():
            vol = volatilities.get(symbol, 0.02)
            weighted_vol += (pct * vol) ** 2

        # 考虑相关性 (简化)
        correlation_factor = 0.7  # 假设平均相关性
        portfolio_vol = np.sqrt(weighted_vol) * (1 + correlation_factor * (len(positions) - 1) / len(positions))

        return float(portfolio_vol)
