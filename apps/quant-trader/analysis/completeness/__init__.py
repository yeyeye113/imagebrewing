"""AI 预测完整性补充模块 — 只读适配器，不覆盖策略核心逻辑。

7个展示模块:
  1. DirectionPredictor   — 方向预测（做多/做空/中性概率）
  2. WalkForwardValidator — 滚动训练验证（每期表现）
  3. ModelEnsemble        — 模型集成（LightGBM/XGBoost/CatBoost）
  4. FeatureSelector      — 特征重要性（排名/剔除/噪音）
  5. MarketRegimeDetector — 市场状态（趋势/震荡/高波动）
  6. CostModel            — 成本模型（手续费+滑点+冲击成本）
  7. OutOfSampleReport    — 样本外报告（训练vs OOS对比）

最高原则: 只增强解释和验证，不覆盖现有策略硬规则。
"""

from .cost_model import analyze as cost_analyze
from .direction import analyze as direction_analyze
from .ensemble import analyze as ensemble_analyze
from .feature_selector import analyze as feature_analyze
from .oos_report import analyze as oos_analyze
from .regime import analyze as regime_analyze
from .walk_forward import analyze as walk_forward_analyze

__all__ = [
    "cost_analyze",
    "direction_analyze",
    "ensemble_analyze",
    "feature_analyze",
    "oos_analyze",
    "regime_analyze",
    "walk_forward_analyze",
]
