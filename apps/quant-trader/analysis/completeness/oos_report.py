"""模块7: OutOfSampleReport — 样本外报告适配器。

只读展示: 真正样本外测试结果（训练vs OOS对比）。
如果样本外表现明显低于训练表现，提示可能过拟合。
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)


def analyze(prices: pd.DataFrame, symbol: str = "", train_ratio: float = 0.7, horizon: int = 5, **kwargs) -> dict:
    """执行严格的样本外评估。

    流程:
      1. 前 70% 数据训练，后 30% 数据测试（完全不看）
      2. 分别计算训练集和测试集的胜率、净期望、Sharpe
      3. 对比两者差异，检测过拟合

    Args:
        prices: OHLCV DataFrame
        symbol: 品种代码
        train_ratio: 训练集比例
        horizon: 预测窗口

    Returns:
        dict: 样本外报告展示数据
    """
    if prices is None or len(prices) < 150:
        return _empty(symbol, "数据不足（需至少150根K线）")

    closes = prices["close"].astype(float)

    # ── 特征构建 ──
    features = _build_features(prices)
    if features is None:
        return _empty(symbol, "特征构建失败")

    # ── 标签 ──
    future_return = closes.shift(-horizon) / closes - 1
    labels = pd.Series(0, index=closes.index)
    labels[future_return > 0.005] = 1
    labels[future_return < -0.005] = -1

    # 对齐
    valid_mask = features.notna().all(axis=1) & labels.notna()
    X = features[valid_mask]
    y = labels[valid_mask]

    if len(X) < 100:
        return _empty(symbol, "有效数据不足")

    # ── 严格 train/test 分割 ──
    split_idx = int(len(X) * train_ratio)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    if len(X_test) < 20:
        return _empty(symbol, "测试集不足20条")

    # ── 训练模型 ──
    from sklearn.ensemble import RandomForestClassifier
    model = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    # ── 训练集表现 ──
    train_preds = model.predict(X_train)
    train_metrics = _compute_metrics(train_preds, y_train, closes, X_train.index, future_return, horizon)

    # ── 测试集表现 (样本外) ──
    test_preds = model.predict(X_test)
    test_metrics = _compute_metrics(test_preds, y_test, closes, X_test.index, future_return, horizon)

    # ── 过拟合检测 ──
    overfit_ratio = test_metrics["win_rate"] / train_metrics["win_rate"] if train_metrics["win_rate"] > 0 else 0
    overfitting_flag = overfit_ratio < 0.7  # OOS胜率低于训练的70%

    # 稳定性: 测试集分段计算胜率的标准差
    test_chunk_size = max(10, len(X_test) // 5)
    test_win_rates = []
    for start in range(0, len(X_test) - test_chunk_size, test_chunk_size):
        chunk_preds = test_preds[start:start + test_chunk_size]
        chunk_y = y_test.iloc[start:start + test_chunk_size]
        chunk_wr = float(np.mean(chunk_preds == chunk_y))
        test_win_rates.append(chunk_wr)
    stability = round(1.0 - min(1.0, np.std(test_win_rates) * 3), 3) if test_win_rates else 0

    # 建议
    if overfitting_flag:
        recommendation = "过拟合风险高！OOS表现显著低于训练，建议减少特征或增加数据"
    elif stability < 0.5:
        recommendation = "稳定性不足，建议增加训练数据或简化模型"
    elif test_metrics["win_rate"] < 0.45:
        recommendation = "OOS胜率偏低，策略可能无效"
    else:
        recommendation = "样本外表现尚可，建议进一步WalkForward验证"

    return {
        "symbol": symbol,
        "training": train_metrics,
        "oos": test_metrics,
        "overfitting_flag": overfitting_flag,
        "overfit_ratio": round(overfit_ratio, 3),
        "stability": stability,
        "recommendation": recommendation,
        "train_size": len(X_train),
        "test_size": len(X_test),
        "strategy_impact": "none",
    }


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "training": {"win_rate": 0, "sharpe": 0, "total_return": 0, "max_drawdown": 0},
        "oos": {"win_rate": 0, "sharpe": 0, "total_return": 0, "max_drawdown": 0},
        "overfitting_flag": False,
        "overfit_ratio": 0,
        "stability": 0,
        "recommendation": reason,
        "train_size": 0,
        "test_size": 0,
        "strategy_impact": "none",
    }


def _compute_metrics(preds, y_true, closes, indices, future_return, horizon):
    """计算预测指标。"""
    preds = np.asarray(preds)
    y_true = np.asarray(y_true)

    # 准确率
    accuracy = float(np.mean(preds == y_true))

    # 交易收益
    trade_returns = []
    for i, idx in enumerate(indices):
        if preds[i] != 0:
            ret = future_return.get(idx, 0)
            if ret is not None and not np.isnan(ret):
                trade_returns.append(preds[i] * ret)

    trade_returns = np.array(trade_returns) if trade_returns else np.array([0])

    # 胜率
    win_rate = float(np.mean(trade_returns > 0))

    # 净期望
    total_return = float(np.sum(trade_returns))

    # Sharpe (简化: 均值/标准差)
    mean_ret = np.mean(trade_returns)
    std_ret = np.std(trade_returns) if np.std(trade_returns) > 0 else 1
    sharpe = float(mean_ret / std_ret * np.sqrt(252))

    # 最大回撤
    cum = np.cumsum(trade_returns)
    peak = np.maximum.accumulate(cum)
    max_dd = float(np.max(peak - cum))

    return {
        "accuracy": round(accuracy, 3),
        "win_rate": round(win_rate, 3),
        "sharpe": round(sharpe, 2),
        "total_return": round(total_return, 4),
        "max_drawdown": round(max_dd, 4),
        "n_trades": len(trade_returns),
    }


def _build_features(prices: pd.DataFrame) -> pd.DataFrame | None:
    """构建特征矩阵。"""
    try:
        closes = prices["close"].astype(float)
        highs = prices["high"].astype(float) if "high" in prices.columns else closes
        lows = prices["low"].astype(float) if "low" in prices.columns else closes
        vols = prices["volume"].astype(float) if "volume" in prices.columns else pd.Series(0, index=prices.index)

        features = pd.DataFrame(index=prices.index)

        for w in [5, 10, 20]:
            sma = closes.rolling(w).mean()
            features[f'close_sma{w}_ratio'] = closes / (sma + 1e-10)

        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        features['rsi_14'] = 100 - (100 / (1 + rs))

        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        features['macd_hist'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()

        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        features['atr_14'] = tr.rolling(14).mean()

        sma20 = closes.rolling(20).mean()
        std20 = closes.rolling(20).std()
        features['bb_pct'] = (closes - (sma20 - 2 * std20)) / (4 * std20 + 1e-10)

        features['roc_5'] = closes / closes.shift(5) - 1
        features['roc_10'] = closes / closes.shift(10) - 1

        vol_sma5 = vols.rolling(5).mean()
        features['vol_ratio'] = vols / (vol_sma5 + 1e-10)

        return features
    except Exception:
        return None
