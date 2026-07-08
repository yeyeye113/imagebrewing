"""v15 因子库特征 — 接入 quanttrader.analysis 指标体系，扩充 ML 特征维度。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def append_factor_library_features(
    features: pd.DataFrame,
    closes: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    vols: pd.Series,
) -> pd.DataFrame:
    """在已有特征表上追加因子库派生列（向量化，可回测）。"""
    # 多参数 MACD 面板
    for fast, slow in ((5, 13), (8, 21), (12, 26), (19, 39)):
        ema_f = closes.ewm(span=fast, adjust=False).mean()
        ema_s = closes.ewm(span=slow, adjust=False).mean()
        macd = ema_f - ema_s
        sig = macd.ewm(span=9, adjust=False).mean()
        features[f"macd_hist_{fast}_{slow}"] = macd - sig
        features[f"macd_line_{fast}_{slow}"] = macd / (closes + 1e-10)

    # 多周期 KDJ
    for period in (9, 14, 21):
        low_n = lows.rolling(period).min()
        high_n = highs.rolling(period).max()
        rsv = (closes - low_n) / (high_n - low_n + 1e-10) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        features[f"kdj_k_{period}"] = k
        features[f"kdj_d_{period}"] = d
        features[f"kdj_j_{period}"] = j

    # 五因子滚动代理 (对齐 analysis/factors 语义)
    for w in (10, 20, 40, 60, 90, 120):
        ret_w = closes / closes.shift(w) - 1
        vol_w = closes.pct_change().rolling(w).std()
        sma_w = closes.rolling(w).mean()
        features[f"factor_mom_{w}"] = ret_w
        features[f"factor_vol_{w}"] = vol_w
        features[f"factor_trend_{w}"] = (closes - sma_w) / (vol_w * closes + 1e-10)
        features[f"factor_mr_{w}"] = (sma_w - closes) / (closes + 1e-10)
        features[f"factor_volm_{w}"] = vols / (vols.rolling(w).mean() + 1e-10)

    # 多窗口布林带
    for w in (10, 30, 40):
        sma = closes.rolling(w).mean()
        std = closes.rolling(w).std()
        features[f"bb_pct_{w}"] = (closes - (sma - 2 * std)) / (4 * std + 1e-10)
        features[f"bb_z_{w}"] = (closes - sma) / (std + 1e-10)

    # 多窗口 ATR%
    tr = pd.concat([
        highs - lows,
        (highs - closes.shift(1)).abs(),
        (lows - closes.shift(1)).abs(),
    ], axis=1).max(axis=1)
    for w in (7, 14, 21, 28):
        features[f"atr_pct_{w}"] = tr.rolling(w).mean() / (closes + 1e-10)

    # 均线排列得分 (多组)
    for w1, w2, w3 in ((5, 10, 20), (10, 20, 60), (20, 60, 120)):
        s1 = closes.rolling(w1).mean()
        s2 = closes.rolling(w2).mean()
        s3 = closes.rolling(w3).mean()
        bull = ((s1 > s2) & (s2 > s3)).astype(float)
        bear = ((s1 < s2) & (s2 < s3)).astype(float)
        features[f"ma_align_{w1}_{w2}_{w3}"] = bull - bear

    # 量价背离近似
    price_chg = closes.pct_change(5)
    vol_chg = vols.pct_change(5)
    features["vol_price_div_5"] = price_chg - vol_chg
    features["vol_price_div_20"] = closes.pct_change(20) - vols.pct_change(20)

    # 资金流 OBV 系列
    direction = np.sign(closes.diff()).fillna(0)
    obv = (direction * vols).cumsum()
    for w in (10, 20, 40):
        features[f"obv_norm_{w}"] = obv / (obv.rolling(w).std() + 1e-10)

    return features
