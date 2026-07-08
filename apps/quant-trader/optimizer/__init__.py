"""Portfolio Optimizer — 组合优化模块.

提供多种组合优化算法，集成到 quant-trader 系统。

Algorithms:
- Mean-Variance (Markowitz): 最大夏普 / 最小方差 / 目标收益
- Black-Litterman: 结合市场均衡 + 主观观点
- Risk Parity: 风险平价 / 风险预算
- Max Diversification: 最大分散化
- Equal Weight: 等权基准

Risk Models:
- Historical covariance
- Ledoit-Wolf shrinkage
- Factor risk model (PCA)

Rebalancing:
- Periodic / threshold-triggered
- Turnover & transaction cost constraints
- Minimum trade filtering
"""

from __future__ import annotations

from .black_litterman import BlackLitterman, BLView
from .mean_variance import (
    MaxDiversification,
    MeanVarianceOptimizer,
    efficient_frontier,
    max_sharpe_weights,
    min_variance_weights,
)
from .rebalancer import RebalanceConfig, Rebalancer, RebalanceResult
from .risk_models import (
    CovarianceEstimator,
    factor_covariance,
    ledoit_wolf_covariance,
    sample_covariance,
)
from .risk_parity import RiskBudget, RiskParity, risk_budget_weights, risk_parity_weights

__all__ = [
    "BLView",
    "BlackLitterman",
    "CovarianceEstimator",
    "MaxDiversification",
    "MeanVarianceOptimizer",
    "RebalanceConfig",
    "RebalanceResult",
    "Rebalancer",
    "RiskBudget",
    "RiskParity",
    "efficient_frontier",
    "factor_covariance",
    "ledoit_wolf_covariance",
    "max_sharpe_weights",
    "min_variance_weights",
    "risk_budget_weights",
    "risk_parity_weights",
    "sample_covariance",
]
