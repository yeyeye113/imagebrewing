"""多品种组合管理器。

功能:
- 跨品种相关性矩阵计算
- 品种分散化评分
- 组合VaR风险计算
- 仓位分配优化

用法:
    from quanttrader.portfolio.multi_asset import MultiAssetPortfolio
    mp = MultiAssetPortfolio()
    mp.add_position('RB', 10, 3500)
    mp.add_position('HC', 20, 3200)
    risk = mp.calculate_correlation_risk(prices_dict)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class Position:
    """单品种持仓信息。"""
    symbol: str
    qty: float
    entry_price: float
    direction: int  # 1=long, -1=short
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        """持仓市值 (多头为正，空头为负)。"""
        return self.qty * self.current_price * self.direction

    @property
    def pnl(self) -> float:
        """持仓盈亏。"""
        if self.current_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) * self.qty * self.direction


@dataclass
class CorrelationResult:
    """相关性分析结果。"""
    correlation_matrix: pd.DataFrame
    avg_correlation: float
    high_correlation_pairs: list[tuple[str, str, float]]  # (sym1, sym2, corr)
    diversification_score: float  # 0-1, 越高越分散
    concentrated_symbols: list[str]  # 高相关性品种
    var_95: float  # 95% VaR
    var_99: float  # 99% VaR


class MultiAssetPortfolio:
    """多品种组合管理器。

    支持:
    - 多空双向持仓
    - 跨品种相关性分析
    - 分散化评分
    - 风险预警
    """

    def __init__(self, initial_capital: float = 1_000_000):
        self.initial_capital = initial_capital
        self.positions: dict[str, Position] = {}
        self.cash: float = initial_capital

    def add_position(
        self,
        symbol: str,
        qty: float,
        entry_price: float,
        direction: int = 1,
        current_price: float | None = None,
    ) -> None:
        """添加持仓。"""
        self.positions[symbol] = Position(
            symbol=symbol,
            qty=qty,
            entry_price=entry_price,
            direction=direction,
            current_price=current_price or entry_price,
        )

    def update_prices(self, prices: dict[str, float]) -> None:
        """更新持仓价格。"""
        for symbol, pos in self.positions.items():
            if symbol in prices:
                pos.current_price = prices[symbol]

    def get_portfolio_value(self) -> float:
        """获取组合总价值。"""
        return self.cash + sum(pos.market_value for pos in self.positions.values())

    def get_returns(self) -> pd.DataFrame:
        """获取各品种收益率 (如果有历史数据)。"""
        # 这个需要历史数据，这里返回空DataFrame
        return pd.DataFrame()

    def calculate_correlation_matrix(
        self,
        price_history: dict[str, pd.Series],
        lookback: int = 60,
    ) -> pd.DataFrame:
        """计算品种相关性矩阵。

        Args:
            price_history: 品种代码 -> 价格序列
            lookback: 回溯期

        Returns:
            相关性矩阵 DataFrame
        """
        if not price_history:
            return pd.DataFrame()

        # 对齐数据
        series_list = []
        symbols = []
        for symbol, prices in price_history.items():
            if len(prices) >= 10:
                series_list.append(prices.tail(lookback))
                symbols.append(symbol)

        if len(series_list) < 2:
            return pd.DataFrame()

        # 合并并计算收益率
        df = pd.DataFrame(series_list, index=symbols).T
        returns = df.pct_change().dropna()

        if returns.empty or returns.shape[1] < 2:
            return pd.DataFrame()

        # 计算相关性矩阵
        corr = returns.corr()
        return corr

    def analyze_correlation_risk(
        self,
        price_history: dict[str, pd.Series],
        correlation_threshold: float = 0.6,
        lookback: int = 60,
    ) -> CorrelationResult:
        """分析组合相关性风险。

        Args:
            price_history: 品种代码 -> 价格序列
            correlation_threshold: 高相关性阈值 (默认0.6)
            lookback: 回溯期

        Returns:
            CorrelationResult
        """
        corr_matrix = self.calculate_correlation_matrix(price_history, lookback)

        if corr_matrix.empty:
            return CorrelationResult(
                correlation_matrix=corr_matrix,
                avg_correlation=0.0,
                high_correlation_pairs=[],
                diversification_score=1.0,
                concentrated_symbols=[],
                var_95=0.0,
                var_99=0.0,
            )

        # 计算平均相关性
        # 获取当前持仓品种
        held_symbols = list(self.positions.keys())
        held_corr = corr_matrix.loc[
            [s for s in held_symbols if s in corr_matrix.index],
            [s for s in held_symbols if s in corr_matrix.columns]
        ]

        # 取上三角矩阵 (排除对角线)
        if held_corr.shape[0] > 1:
            upper = held_corr.where(
                np.triu(np.ones(held_corr.shape), k=1).astype(bool)
            )
            avg_corr = upper.stack().mean()
        else:
            avg_corr = 0.0

        # 找出高相关性品种对
        high_corr_pairs = []
        for i, sym1 in enumerate(held_symbols):
            for sym2 in held_symbols[i+1:]:
                if sym1 in corr_matrix.index and sym2 in corr_matrix.columns:
                    corr_val = corr_matrix.loc[sym1, sym2]
                    if abs(corr_val) >= correlation_threshold:
                        high_corr_pairs.append((sym1, sym2, corr_val))

        # 计算分散化评分 (基于平均相关性)
        # avg_corr=1 -> score=0, avg_corr=0 -> score=1
        div_score = max(0, 1 - abs(avg_corr)) if not np.isnan(avg_corr) else 1.0

        # 找出集中持仓的品种 (与其他品种高度相关的)
        concentrated = []
        if len(held_symbols) > 1:
            avg_per_symbol = corr_matrix.loc[held_symbols, held_symbols].mean()
            for sym, avg in avg_per_symbol.items():
                if abs(avg) >= correlation_threshold:
                    concentrated.append(sym)

        # 计算VaR (简化版: 基于收益率标准差)
        returns_by_symbol = {}
        for symbol in held_symbols:
            if symbol in price_history:
                returns = price_history[symbol].pct_change().dropna().tail(lookback)
                if len(returns) > 0:
                    returns_by_symbol[symbol] = returns

        if returns_by_symbol:
            # 加权组合收益率 (假设等权重)
            weights = np.array([
                abs(self.positions[s].qty * self.positions[s].current_price)
                for s in returns_by_symbol.keys()
            ])
            weights = weights / weights.sum()

            # 简化VaR计算
            combined_std = 0
            for i, (sym, ret) in enumerate(returns_by_symbol.items()):
                ret_std = ret.std()
                combined_std += (weights[i] * ret_std) ** 2

            # 添加相关性影响
            for i, sym1 in enumerate(returns_by_symbol.keys()):
                for j, sym2 in enumerate(returns_by_symbol.keys()):
                    if i < j:
                        corr = 0
                        if sym1 in corr_matrix.index and sym2 in corr_matrix.columns:
                            corr = corr_matrix.loc[sym1, sym2]
                        combined_std += 2 * weights[i] * weights[j] * ret_std * returns_by_symbol[sym2].std() * corr

            combined_std = np.sqrt(combined_std)

            # VaR = std * z_score
            var_95 = combined_std * 1.65
            var_99 = combined_std * 2.33
        else:
            var_95 = var_99 = 0.0

        return CorrelationResult(
            correlation_matrix=corr_matrix,
            avg_correlation=float(avg_corr) if not np.isnan(avg_corr) else 0.0,
            high_correlation_pairs=high_corr_pairs,
            diversification_score=div_score,
            concentrated_symbols=concentrated,
            var_95=var_95,
            var_99=var_99,
        )

    def optimize_weights(
        self,
        price_history: dict[str, pd.Series],
        method: str = "min_variance",
        max_weight: float = 0.3,
        lookback: int = 60,
    ) -> dict[str, float]:
        """优化品种权重。

        Args:
            price_history: 品种代码 -> 价格序列
            method: 优化方法 ("min_variance", "equal_risk", "inverse_vol")
            max_weight: 单品种最大权重

        Returns:
            品种 -> 权重
        """
        symbols = list(price_history.keys())
        if len(symbols) < 2:
            return {s: 1.0 for s in symbols}

        # 计算收益率和协方差
        returns_dict = {}
        for sym in symbols:
            ret = price_history[sym].pct_change().dropna().tail(lookback)
            if len(ret) > 10:
                returns_dict[sym] = ret

        if len(returns_dict) < 2:
            return {s: 1.0 / len(symbols) for s in symbols}

        # 对齐数据
        min_len = min(len(r) for r in returns_dict.values())
        aligned_returns = pd.DataFrame({
            sym: returns_dict[sym].tail(min_len).values
            for sym in returns_dict.keys()
        })

        # 计算协方差矩阵
        cov = aligned_returns.cov()
        std = aligned_returns.std()

        n = len(symbols)

        if method == "equal_risk":
            # 等风险贡献: 权重反比于波动率
            weights = (1 / std) / (1 / std).sum()
        elif method == "inverse_vol":
            # 反波动率权重
            weights = (1 / std**2) / (1 / std**2).sum()
        else:  # min_variance
            # 最小方差 (简化)
            weights = np.linalg.solve(cov, np.ones(n))
            weights = weights / weights.sum()

        # 应用权重上限
        weights = pd.Series(weights).clip(upper=max_weight)
        weights = weights / weights.sum()  # 重新归一化

        return weights.to_dict()

    def get_risk_report(self) -> dict[str, Any]:
        """生成风险报告。"""
        total_value = self.get_portfolio_value()

        # 持仓分布
        positions_value = {
            sym: pos.market_value
            for sym, pos in self.positions.items()
            if abs(pos.market_value) > 0
        }

        # 权重
        weights = {
            sym: mv / total_value
            for sym, mv in positions_value.items()
        }

        # 多空比
        long_value = sum(pos.market_value for pos in self.positions.values() if pos.direction > 0)
        short_value = sum(abs(pos.market_value) for pos in self.positions.values() if pos.direction < 0)

        return {
            "total_value": total_value,
            "cash": self.cash,
            "positions": {
                sym: {
                    "qty": pos.qty,
                    "direction": "LONG" if pos.direction > 0 else "SHORT",
                    "entry": pos.entry_price,
                    "current": pos.current_price,
                    "market_value": pos.market_value,
                    "pnl": pos.pnl,
                    "weight": weights.get(sym, 0),
                }
                for sym, pos in self.positions.items()
            },
            "weights": weights,
            "long_short_ratio": long_value / short_value if short_value > 0 else float('inf'),
            "n_positions": len([p for p in self.positions.values() if abs(p.market_value) > 0]),
        }

    def check_risk_limits(
        self,
        max_position_pct: float = 0.3,
        max_total_exposure: float = 0.8,
        max_single_direction: float = 0.6,
    ) -> list[str]:
        """检查风险限制，返回违规信息。"""
        violations = []
        total_value = self.get_portfolio_value()

        for sym, pos in self.positions.items():
            weight = abs(pos.market_value) / total_value if total_value > 0 else 0
            if weight > max_position_pct:
                violations.append(f"单品种权重超限: {sym} {weight*100:.1f}% > {max_position_pct*100:.0f}%")

        # 总敞口
        total_exposure = sum(abs(pos.market_value) for pos in self.positions.values()) / total_value
        if total_exposure > max_total_exposure:
            violations.append(f"总敞口超限: {total_exposure*100:.1f}% > {max_total_exposure*100:.0f}%")

        # 单方向敞口
        long_value = sum(pos.market_value for pos in self.positions.values() if pos.direction > 0)
        short_value = sum(abs(pos.market_value) for pos in self.positions.values() if pos.direction < 0)

        if long_value / total_value > max_single_direction:
            violations.append(f"多头敞口超限: {long_value/total_value*100:.1f}% > {max_single_direction*100:.0f}%")

        if short_value / total_value > max_single_direction:
            violations.append(f"空头敞口超限: {short_value/total_value*100:.1f}% > {max_single_direction*100:.0f}%")

        return violations
