"""模块4: FeatureSelector — 特征重要性展示适配器。

只读展示: 特征重要性排名、被剔除特征、高噪音特征、近期失效特征。
不在前端重新筛选核心特征。
"""

from __future__ import annotations

import logging
import warnings

import pandas as pd

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)


def analyze(prices: pd.DataFrame, symbol: str = "", top_n: int = 15, **kwargs) -> dict:
    """分析特征重要性，返回展示数据。

    流程:
      1. 构建特征矩阵
      2. 训练 RandomForest 获取 feature_importances_
      3. 排序并分类: 核心 / 普通 / 低效 / 噪音
      4. 对比近期数据检测失效特征

    Args:
        prices: OHLCV DataFrame
        symbol: 品种代码
        top_n: 展示前N个重要特征

    Returns:
        dict: 特征重要性展示数据
    """
    if prices is None or len(prices) < 100:
        return _empty(symbol, "数据不足（需至少100根K线）")

    closes = prices["close"].astype(float)

    # ── 特征构建 ──
    features = _build_features(prices)
    if features is None or len(features) < 80:
        return _empty(symbol, "特征构建失败")

    # ── 标签: 5根K线后方向 ──
    future_return = closes.shift(-5) / closes - 1
    labels = pd.Series(0, index=closes.index)
    labels[future_return > 0.005] = 1
    labels[future_return < -0.005] = -1

    # 对齐
    valid_mask = features.notna().all(axis=1) & labels.notna()
    X = features[valid_mask]
    y = labels[valid_mask]

    if len(X) < 80:
        return _empty(symbol, "有效数据不足")

    # ── 训练 RandomForest 获取重要性 ──
    from sklearn.ensemble import RandomForestClassifier
    model = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)
    model.fit(X, y)

    importance_scores = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)

    # ── 分类 ──
    total_features = len(importance_scores)
    core_features = importance_scores.head(top_n).index.tolist()
    # 噪音: 重要性为0或极低 (< 0.001)
    noise_features = importance_scores[importance_scores < 0.001].index.tolist()
    # 低效: 重要性排名后30%
    low_efficiency = importance_scores.tail(max(1, int(total_features * 0.3))).index.tolist()

    # ── 近期失效检测 ──
    # 将数据分为前半和后半，对比重要性变化
    half_idx = len(X) // 2
    X_first, y_first = X.iloc[:half_idx], y.iloc[:half_idx]
    X_second, y_second = X.iloc[half_idx:], y.iloc[half_idx:]

    model_first = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42, n_jobs=-1)
    model_first.fit(X_first, y_first)
    imp_first = pd.Series(model_first.feature_importances_, index=X.columns)

    model_second = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42, n_jobs=-1)
    model_second.fit(X_second, y_second)
    imp_second = pd.Series(model_second.feature_importances_, index=X.columns)

    # 近期失效: 后半重要性显著下降 (降幅 > 50% 且绝对值 > 0.01)
    imp_change = imp_second - imp_first
    recently_failed = imp_change[imp_change < -0.01].index.tolist()

    # ── 组装结果 ──
    feature_list = []
    for name in importance_scores.index:
        score = float(importance_scores[name])
        if name in core_features:
            status = "core"
        elif name in noise_features:
            status = "noise"
        elif name in recently_failed:
            status = "failed"
        elif name in low_efficiency:
            status = "low"
        else:
            status = "normal"
        feature_list.append({
            "name": name,
            "importance": round(score, 5),
            "status": status,
        })

    return {
        "symbol": symbol,
        "features": feature_list[:top_n * 2],  # 返回前2倍数量供展示
        "top_features": core_features,
        "removed_features": noise_features[:10],
        "high_noise_features": [f for f in noise_features if f in recently_failed],
        "recently_failed_features": recently_failed[:10],
        "total_features": total_features,
        "core_count": len(core_features),
        "noise_count": len(noise_features),
        "strategy_impact": "none",
    }


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "features": [],
        "top_features": [],
        "removed_features": [],
        "high_noise_features": [],
        "recently_failed_features": [],
        "total_features": 0,
        "core_count": 0,
        "noise_count": 0,
        "strategy_impact": "none",
    }


def _build_features(prices: pd.DataFrame) -> pd.DataFrame | None:
    """构建特征矩阵。"""
    try:
        closes = prices["close"].astype(float)
        highs = prices["high"].astype(float) if "high" in prices.columns else closes
        lows = prices["low"].astype(float) if "low" in prices.columns else closes
        vols = prices["volume"].astype(float) if "volume" in prices.columns else pd.Series(0, index=prices.index)

        features = pd.DataFrame(index=prices.index)

        for w in [5, 10, 20, 60]:
            sma = closes.rolling(w).mean()
            features[f'close_sma{w}_ratio'] = closes / (sma + 1e-10)

        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        features['rsi_14'] = 100 - (100 / (1 + rs))

        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9).mean()
        features['macd_hist'] = macd - signal_line

        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        for w in [10, 14, 20]:
            features[f'atr_{w}'] = tr.rolling(w).mean()

        sma20 = closes.rolling(20).mean()
        std20 = closes.rolling(20).std()
        features['bb_pct'] = (closes - (sma20 - 2 * std20)) / (4 * std20 + 1e-10)
        features['bb_width'] = (4 * std20) / (sma20 + 1e-10)

        features['roc_5'] = closes / closes.shift(5) - 1
        features['roc_10'] = closes / closes.shift(10) - 1
        features['roc_20'] = closes / closes.shift(20) - 1

        vol_sma5 = vols.rolling(5).mean()
        vol_sma20 = vols.rolling(20).mean()
        features['vol_ratio'] = vols / (vol_sma5 + 1e-10)
        features['vol_sma_ratio'] = vol_sma5 / (vol_sma20 + 1e-10)

        # ADX
        plus_dm = highs.diff().clip(lower=0)
        minus_dm = (-lows.diff()).clip(lower=0)
        plus_di = plus_dm.rolling(14).mean() / (tr.rolling(14).mean() + 1e-10) * 100
        minus_di = minus_dm.rolling(14).mean() / (tr.rolling(14).mean() + 1e-10) * 100
        dx = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10) * 100
        features['adx'] = dx.rolling(14).mean()

        # 价格位置
        high_20 = highs.rolling(20).max()
        low_20 = lows.rolling(20).min()
        features['close_position'] = (closes - low_20) / (high_20 - low_20 + 1e-10)

        return features
    except Exception as e:
        logger.warning("特征构建失败: %s", e)
        return None
