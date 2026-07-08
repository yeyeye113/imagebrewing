"""factor_db — 因子数据库模块

将因子计算结果存储到 SQLite，支持快速查询和分析。

Usage::

    from quanttrader.factor_db import FactorDB, compute_factors, ic_analysis

    db = FactorDB()                        # 默认 factor_db.sqlite
    compute_factors(prices_df, symbols, db)  # 计算并入库
    query = FactorQuery(db)
    df = query.get_factor("momentum_20d", symbols=["AAPL"])
    ic_df = ic_analysis(db, factor="momentum_20d", horizon=5)
"""

from .analysis import group_backtest, ic_analysis
from .compute import FACTOR_REGISTRY, compute_factors
from .query import FactorQuery
from .storage import FactorDB

__all__ = [
    "FACTOR_REGISTRY",
    "FactorDB",
    "FactorQuery",
    "compute_factors",
    "group_backtest",
    "ic_analysis",
]
