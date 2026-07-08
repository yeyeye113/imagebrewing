"""模块2: WalkForwardValidator — 滚动训练验证适配器。

只读展示: 滚动训练窗口、预测窗口、每期表现（胜率/净期望/最大回撤/连续亏损）。
用于判断模型是否接近真实交易流程。
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)


def analyze(prices: pd.DataFrame, symbol: str = "", n_splits: int = 5, horizon: int = 5, **kwargs) -> dict:
    """执行滚动训练验证，返回每期表现数据。

    流程:
      1. 将数据分为 n_splits 个滚动窗口
      2. 每个窗口: 用前面的数据训练，用后面的数据测试
      3. 计算每期的胜率、净期望、最大回撤、连续亏损
      4. 汇总为整体评估

    Args:
        prices: OHLCV DataFrame
        symbol: 品种代码
        n_splits: 滚动窗口数
        horizon: 预测窗口

    Returns:
        dict: 滚动验证展示数据
    """
    if prices is None or len(prices) < 150:
        return _empty(symbol, "数据不足（需至少150根K线）")

    closes = prices["close"].astype(float)

    # ── 特征构建 ──
    features = _build_simple_features(prices)
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

    # ── 滚动窗口 ──
    total_len = len(X)
    train_size = int(total_len * 0.5)  # 训练集占50%
    test_size = (total_len - train_size) // n_splits

    if test_size < 20:
        return _empty(symbol, "数据不足以分出足够窗口")

    periods = []
    all_test_returns = []

    for i in range(n_splits):
        test_start = train_size + i * test_size
        test_end = min(test_start + test_size, total_len)
        if test_end - test_start < 10:
            break

        train_end = test_start
        train_start = max(0, train_end - train_size)

        X_train = X.iloc[train_start:train_end]
        y_train = y.iloc[train_start:train_end]
        X_test = X.iloc[test_start:test_end]
        y_test = y.iloc[test_start:test_end]

        # 训练
        try:
            from sklearn.ensemble import RandomForestClassifier
            model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42, n_jobs=-1)
            model.fit(X_train, y_train)
        except Exception as e:
            logger.warning("窗口 %d 训练失败: %s", i, e)
            continue

        # 预测
        preds = model.predict(X_test)
        acc = float(np.mean(preds == y_test))

        # 计算每笔交易的收益（用预测方向 × 实际收益率）
        test_indices = X_test.index
        period_returns = []
        for j, idx in enumerate(test_indices):
            if preds[j] != 0:  # 有方向预测
                actual_ret = future_return.get(idx, 0)
                if actual_ret is not None and not np.isnan(actual_ret):
                    trade_ret = preds[j] * actual_ret
                    period_returns.append(trade_ret)
                    all_test_returns.append(trade_ret)

        returns_arr = np.array(period_returns) if period_returns else np.array([0])

        # 胜率
        win_rate = float(np.mean(returns_arr > 0)) if len(returns_arr) > 0 else 0

        # 净期望 (平均每笔收益)
        net_expectation = float(np.mean(returns_arr)) if len(returns_arr) > 0 else 0

        # 最大回撤
        cum_returns = np.cumsum(returns_arr)
        peak = np.maximum.accumulate(cum_returns)
        drawdown = peak - cum_returns
        max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0

        # 连续亏损
        consecutive_losses = 0
        max_consecutive_losses = 0
        for ret in returns_arr:
            if ret <= 0:
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_losses = 0

        periods.append({
            "period": i + 1,
            "train_bars": train_end - train_start,
            "test_bars": test_end - test_start,
            "accuracy": round(acc, 3),
            "win_rate": round(win_rate, 3),
            "net_expectation": round(net_expectation, 5),
            "max_drawdown": round(max_drawdown, 5),
            "max_consecutive_losses": max_consecutive_losses,
            "n_trades": len(returns_arr),
        })

    if not periods:
        return _empty(symbol, "所有窗口训练失败")

    # ── 汇总 ──
    avg_win_rate = np.mean([p["win_rate"] for p in periods])
    avg_net_exp = np.mean([p["net_expectation"] for p in periods])
    overall_max_dd = max(p["max_drawdown"] for p in periods)
    worst_consecutive = max(p["max_consecutive_losses"] for p in periods)

    # 稳定性: 各期胜率的标准差
    win_rates = [p["win_rate"] for p in periods]
    stability = 1.0 - min(1.0, np.std(win_rates) * 3)  # 标准差越小越稳定

    # 过拟合信号: 如果某些期表现极好但整体一般
    max_period_wr = max(win_rates)
    min_period_wr = min(win_rates)
    overfit_signal = max_period_wr - min_period_wr > 0.3

    return {
        "symbol": symbol,
        "periods": periods,
        "summary": {
            "avg_win_rate": round(float(avg_win_rate), 3),
            "avg_net_expectation": round(float(avg_net_exp), 5),
            "overall_max_drawdown": round(float(overall_max_dd), 5),
            "worst_consecutive_losses": worst_consecutive,
            "total_folds": len(periods),
            "stability": round(float(stability), 3),
        },
        "overfit_signal": overfit_signal,
        "strategy_impact": "none",
    }


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "periods": [],
        "summary": {
            "avg_win_rate": 0,
            "avg_net_expectation": 0,
            "overall_max_drawdown": 0,
            "worst_consecutive_losses": 0,
            "total_folds": 0,
            "stability": 0,
        },
        "overfit_signal": False,
        "strategy_impact": "none",
    }


def _build_simple_features(prices: pd.DataFrame) -> pd.DataFrame | None:
    """构建简化特征矩阵。"""
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
