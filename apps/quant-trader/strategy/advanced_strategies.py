"""高级技术策略库 — MACD交叉/KDJ信号/一目均衡/放量突破/均线带.

与基础策略 (SMA/RSI/Bollinger/Momentum) 配合使用，构成 9 策略投票系统。
每个策略实现 Strategy ABC，返回 Signal 序列 (BUY/HOLD/SELL).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .base import Signal, Strategy
from .signal_utils import long_only_hold_targets

# ═══════════════════════════════════════════════════════════════════════
# 策略 5: MACD 交叉策略
# ═══════════════════════════════════════════════════════════════════════

class MacdCrossStrategy(Strategy):
    """MACD 金叉/死叉 + 零轴位置确认.

    买入条件: MACD 金叉 且 (MACD > 0 或 柱状图连续放大 2 天)
    卖出条件: MACD 死叉 且 (MACD < 0 或 柱状图连续缩小 2 天)
    """

    name = "macd_cross"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        close = prices["close"]
        n = len(close)
        if n < self.slow + self.signal + 2:
            return pd.Series(Signal.HOLD, index=prices.index)

        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
        histogram = macd_line - signal_line

        sig_arr = np.full(n, Signal.HOLD, dtype=int)
        h_arr = histogram.values
        m_arr = macd_line.values

        for i in range(2, n):
            h = h_arr[i]
            h_prev = h_arr[i - 1]
            h_prev2 = h_arr[i - 2]
            m = m_arr[i]

            # 金叉: 柱状图从负转正
            if h > 0 and h_prev <= 0:
                # 零轴之上金叉更强，零轴之下也行但需要柱状图放大确认
                if m > 0 or (h > h_prev):
                    sig_arr[i] = Signal.BUY
            # 死叉: 柱状图从正转负
            elif h < 0 and h_prev >= 0:
                if m < 0 or (h < h_prev):
                    sig_arr[i] = Signal.SELL
            # 柱状图持续放大 → 维持方向
            elif h > 0 and h > h_prev and h_prev > h_prev2:
                sig_arr[i] = Signal.BUY
            elif h < 0 and h < h_prev and h_prev < h_prev2:
                sig_arr[i] = Signal.SELL

        return pd.Series(long_only_hold_targets(sig_arr), index=prices.index)


# ═══════════════════════════════════════════════════════════════════════
# 策略 6: KDJ 信号策略
# ═══════════════════════════════════════════════════════════════════════

class KdjStrategy(Strategy):
    """KDJ 超买超卖 + 金叉死叉.

    买入条件: K/D 在超卖区 (<20) 金叉，或 K 线从超卖区回升
    卖出条件: K/D 在超买区 (>80) 死叉，或 K 线从超买区回落
    """

    name = "kdj"

    def __init__(self, period: int = 9, k_smooth: int = 3, d_smooth: int = 3):
        self.period = period
        self.k_smooth = k_smooth
        self.d_smooth = d_smooth

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        n = len(prices)
        if n < self.period + self.k_smooth + self.d_smooth + 2:
            return pd.Series(Signal.HOLD, index=prices.index)

        high = prices["high"]
        low = prices["low"]
        close = prices["close"]

        lowest_low = low.rolling(self.period).min()
        highest_high = high.rolling(self.period).max()
        rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
        rsv = rsv.fillna(50)

        k = rsv.ewm(span=self.k_smooth, adjust=False).mean()
        d = k.ewm(span=self.d_smooth, adjust=False).mean()

        sig_arr = np.full(n, Signal.HOLD, dtype=int)
        k_arr = k.values
        d_arr = d.values

        for i in range(2, n):
            k_val = k_arr[i]
            d_val = d_arr[i]
            k_prev = k_arr[i - 1]
            d_prev = d_arr[i - 1]

            # 金叉: K 上穿 D
            golden = k_val > d_val and k_prev <= d_prev
            # 死叉: K 下穿 D
            death = k_val < d_val and k_prev >= d_prev

            if golden:
                # 只在超卖区金叉才买 (收紧条件)
                if k_val < 25:
                    sig_arr[i] = Signal.BUY
            elif death:
                # 只在超买区死叉才卖 (收紧条件)
                if k_val > 75:
                    sig_arr[i] = Signal.SELL
            # K 线从极端区回升 (保留)
            elif k_prev < 15 and k_val > 20:
                sig_arr[i] = Signal.BUY
            elif k_prev > 85 and k_val < 80:
                sig_arr[i] = Signal.SELL

        return pd.Series(long_only_hold_targets(sig_arr), index=prices.index)


# ═══════════════════════════════════════════════════════════════════════
# 策略 7: 一目均衡表策略
# ═══════════════════════════════════════════════════════════════════════

class IchimokuStrategy(Strategy):
    """一目均衡表 (Ichimoku Cloud) 信号.

    买入条件: 价格在云图之上 且 转换线 > 基准线 (TK 金叉)
    卖出条件: 价格在云图之下 且 转换线 < 基准线 (TK 死叉)
    """

    name = "ichimoku"

    def __init__(self, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52):
        self.tenkan = tenkan
        self.kijun = kijun
        self.senkou_b = senkou_b

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        n = len(prices)
        if n < self.senkou_b + 2:
            return pd.Series(Signal.HOLD, index=prices.index)

        high = prices["high"]
        low = prices["low"]
        close = prices["close"]

        # 转换线 (Tenkan-sen): (9日最高 + 9日最低) / 2
        tenkan = (high.rolling(self.tenkan).max() + low.rolling(self.tenkan).min()) / 2
        # 基准线 (Kijun-sen): (26日最高 + 26日最低) / 2
        kijun = (high.rolling(self.kijun).max() + low.rolling(self.kijun).min()) / 2
        # 先行 A: (转换线 + 基准线) / 2
        senkou_a = (tenkan + kijun) / 2
        # 先行 B: (52日最高 + 52日最低) / 2
        senkou_b_line = (high.rolling(self.senkou_b).max() + low.rolling(self.senkou_b).min()) / 2

        sig_arr = np.full(n, Signal.HOLD, dtype=int)
        close_arr = close.values
        tenkan_arr = tenkan.values
        kijun_arr = kijun.values
        sa_arr = senkou_a.values
        sb_arr = senkou_b_line.values

        for i in range(self.senkou_b + 1, n):
            price = close_arr[i]
            t = tenkan_arr[i]
            k = kijun_arr[i]
            t_prev = tenkan_arr[i - 1]
            k_prev = kijun_arr[i - 1]
            sa = sa_arr[i]
            sb = sb_arr[i]

            cloud_top = max(sa, sb)
            cloud_bottom = min(sa, sb)

            above_cloud = price > cloud_top
            below_cloud = price < cloud_bottom

            # TK 金叉
            tk_golden = t > k and t_prev <= k_prev
            # TK 死叉
            tk_death = t < k and t_prev >= k_prev

            if above_cloud and tk_golden:
                sig_arr[i] = Signal.BUY
            elif below_cloud and tk_death:
                sig_arr[i] = Signal.SELL
            # 云图变色信号 (senkou_a 穿越 senkou_b)
            elif i >= 2:
                sa_prev = sa_arr[i - 1]
                sb_prev = sb_arr[i - 1]
                # 云图变多头 (A 上穿 B)
                if sa > sb and sa_prev <= sb_prev and above_cloud:
                    sig_arr[i] = Signal.BUY
                # 云图变空头 (A 下穿 B)
                elif sa < sb and sa_prev >= sb_prev and below_cloud:
                    sig_arr[i] = Signal.SELL

        return pd.Series(long_only_hold_targets(sig_arr), index=prices.index)


# ═══════════════════════════════════════════════════════════════════════
# 策略 8: 放量突破策略
# ═══════════════════════════════════════════════════════════════════════

class VolumeBreakoutStrategy(Strategy):
    """放量突破 N 日高点.

    买入条件: 收盘价突破 20 日最高 且 成交量 > 1.5 倍 20 日均量
    卖出条件: 收盘价跌破 20 日最低 且 成交量 > 1.5 倍 20 日均量
    """

    name = "volume_breakout"

    def __init__(self, lookback: int = 20, vol_multiplier: float = 1.5):
        self.lookback = lookback
        self.vol_multiplier = vol_multiplier

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        n = len(prices)
        if n < self.lookback + 2:
            return pd.Series(Signal.HOLD, index=prices.index)

        close = prices["close"]
        high = prices["high"]
        low = prices["low"]

        has_volume = "volume" in prices.columns
        if has_volume:
            volume = prices["volume"]
            vol_ma = volume.rolling(self.lookback).mean()

        sig_arr = np.full(n, Signal.HOLD, dtype=int)
        close_arr = close.values
        high_arr = high.values
        low_arr = low.values
        holding = 0

        min_breakout_pct = 0.003

        if has_volume:
            vol_arr = volume.values
            vol_ma_arr = vol_ma.values

        for i in range(self.lookback + 1, n):
            price = close_arr[i]
            high_n = float(high_arr[i - self.lookback:i].max())
            low_n = float(low_arr[i - self.lookback:i].min())

            if has_volume:
                vol = vol_arr[i]
                vol_avg = vol_ma_arr[i - 1] if i > 0 else 1
                vol_confirm = vol > vol_avg * self.vol_multiplier if vol_avg > 0 else False
            else:
                vol_confirm = True

            if price > high_n * (1 + min_breakout_pct) and vol_confirm:
                holding = 1
            elif price < low_n * (1 - min_breakout_pct) and vol_confirm:
                holding = 0
            sig_arr[i] = Signal.BUY if holding else Signal.HOLD

        return pd.Series(sig_arr, index=prices.index)


# ═══════════════════════════════════════════════════════════════════════
# 策略 9: 均线带策略 (MA Ribbon)
# ═══════════════════════════════════════════════════════════════════════

class MaRibbonStrategy(Strategy):
    """均线带 (MA Ribbon) 多头/空头排列.

    买入条件: 5/10/20/60 均线多头排列 (5>10>20>60) 且价格在所有均线之上
    卖出条件: 均线空头排列 且价格在所有均线之下
    """

    name = "ma_ribbon"

    def __init__(self, periods: list[int] | None = None, slow_tail: int = 60):
        if periods is not None:
            self.periods = periods
        else:
            self.periods = [5, 10, 20, int(slow_tail)]

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        n = len(prices)
        max_p = max(self.periods)
        if n < max_p + 2:
            return pd.Series(Signal.HOLD, index=prices.index)

        close = prices["close"]

        # 计算所有均线
        mas = {}
        for p in self.periods:
            if n >= p:
                mas[p] = close.rolling(p).mean()

        sig_arr = np.full(n, Signal.HOLD, dtype=int)
        close_arr = close.values
        mas_arr = {p: mas[p].values for p in mas}
        holding = 0

        for i in range(max_p + 1, n):
            price = close_arr[i]
            values = []
            all_above = True
            all_below = True

            for p in sorted(self.periods):
                if p in mas_arr:
                    ma_val = mas_arr[p][i]
                    values.append(ma_val)
                    if price <= ma_val:
                        all_above = False
                    if price >= ma_val:
                        all_below = False

            if len(values) < 3:
                continue

            # 多头排列: 短期均线 > 长期均线
            bullish_align = all(values[j] >= values[j + 1] for j in range(len(values) - 1))
            # 空头排列: 短期均线 < 长期均线
            bearish_align = all(values[j] <= values[j + 1] for j in range(len(values) - 1))

            if bullish_align and all_above:
                holding = 1
            elif bearish_align and all_below:
                holding = 0
            sig_arr[i] = Signal.BUY if holding else Signal.HOLD

        return pd.Series(sig_arr, index=prices.index)


# ═══════════════════════════════════════════════════════════════════════
# 策略 10: VWAP 交叉策略
# ═══════════════════════════════════════════════════════════════════════

class VwapCrossStrategy(Strategy):
    """价格穿越 VWAP 信号.

    买入条件: 价格上穿 20 日滚动 VWAP
    卖出条件: 价格下穿 20 日滚动 VWAP
    """

    name = "vwap_cross"

    def __init__(self, period: int = 20):
        self.period = period

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        n = len(prices)
        if n < self.period + 2 or "volume" not in prices.columns:
            return pd.Series(Signal.HOLD, index=prices.index)

        close = prices["close"]
        typical = (prices["high"] + prices["low"] + prices["close"]) / 3
        vol = prices["volume"].clip(lower=1)
        vwap = (typical * vol).rolling(self.period).sum() / vol.rolling(self.period).sum()

        sig_arr = np.full(n, Signal.HOLD, dtype=int)
        close_arr = close.values
        vwap_arr = vwap.values

        for i in range(self.period + 1, n):
            price = close_arr[i]
            v = vwap_arr[i]
            p_prev = close_arr[i - 1]
            v_prev = vwap_arr[i - 1]

            if np.isnan(v) or np.isnan(v_prev):
                continue

            # 价格上穿 VWAP
            if price > v and p_prev <= v_prev:
                sig_arr[i] = Signal.BUY
            # 价格下穿 VWAP
            elif price < v and p_prev >= v_prev:
                sig_arr[i] = Signal.SELL

        return pd.Series(long_only_hold_targets(sig_arr), index=prices.index)


# ═══════════════════════════════════════════════════════════════════════
# 策略 11: Supertrend 策略
# ═══════════════════════════════════════════════════════════════════════

class SupertrendStrategy(Strategy):
    """Supertrend 自适应趋势跟踪.

    买入条件: 方向从空翻多 (价格突破上轨)
    卖出条件: 方向从多翻空 (价格跌破下轨)
    """

    name = "supertrend"

    def __init__(self, period: int = 10, multiplier: float = 3.0):
        self.period = period
        self.multiplier = multiplier

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        n = len(prices)
        if n < self.period + 5:
            return pd.Series(Signal.HOLD, index=prices.index)

        high = prices["high"]
        low = prices["low"]
        close = prices["close"]

        # ATR
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(self.period).mean()

        # 基础上下轨
        hl2 = (high + low) / 2
        upper_band = hl2 + self.multiplier * atr
        lower_band = hl2 - self.multiplier * atr

        # 方向跟踪（pandas 3.0 下 .values 是只读视图，需取可写副本再赋值）
        direction = pd.Series(1, index=prices.index)
        dir_arr = direction.to_numpy(copy=True)
        close_arr = close.values
        ub_arr = upper_band.values
        lb_arr = lower_band.values

        for i in range(self.period + 1, n):
            price = close_arr[i]
            ub = ub_arr[i]
            lb = lb_arr[i]
            if np.isnan(ub) or np.isnan(lb):
                continue
            if price > ub:
                dir_arr[i] = 1
            elif price < lb:
                dir_arr[i] = -1
            else:
                dir_arr[i] = dir_arr[i - 1]

        # 目标持仓：多头方向持有多单，空头方向空仓（long-only Backtester）
        sig_arr = np.where(dir_arr == 1, Signal.BUY, Signal.HOLD)
        return pd.Series(sig_arr, index=prices.index)


# ═══════════════════════════════════════════════════════════════════════
# 策略注册表
# ═══════════════════════════════════════════════════════════════════════

ADVANCED_STRATEGIES = {
    "macd_cross": MacdCrossStrategy,
    "kdj": KdjStrategy,
    "ichimoku": IchimokuStrategy,
    "volume_breakout": VolumeBreakoutStrategy,
    "ma_ribbon": MaRibbonStrategy,
    "vwap_cross": VwapCrossStrategy,
    "supertrend": SupertrendStrategy,
}

# 全部 11 策略 (4 基础 + 7 高级) — 用于投票系统
# 参数 dict 为 int/float/list 混合, 显式标注避免推断成 object
ALL_STRATEGY_CONFIGS: list[tuple[str, dict[str, Any], str]] = [
    # 基础策略
    ("sma_cross", {"fast": 20, "slow": 50}, "双均线"),
    ("rsi", {"period": 14, "oversold": 30, "overbought": 70}, "RSI"),
    ("bollinger", {"period": 20, "num_std": 2.0}, "布林带"),
    ("momentum", {"lookback": 90}, "动量"),
    # 高级策略
    ("macd_cross", {"fast": 12, "slow": 26, "signal": 9}, "MACD交叉"),
    ("kdj", {"period": 9, "k_smooth": 3, "d_smooth": 3}, "KDJ"),
    ("ichimoku", {"tenkan": 9, "kijun": 26, "senkou_b": 52}, "一目均衡"),
    ("volume_breakout", {"lookback": 20, "vol_multiplier": 1.5}, "放量突破"),
    ("ma_ribbon", {"periods": [5, 10, 20, 60]}, "均线带"),
    ("vwap_cross", {"period": 20}, "VWAP交叉"),
    ("supertrend", {"period": 10, "multiplier": 3.0}, "Supertrend"),
]
