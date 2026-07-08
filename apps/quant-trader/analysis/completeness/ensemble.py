"""模块3: ModelEnsemble — 模型集成展示适配器。

只读展示: 各模型(LightGBM/XGBoost/CatBoost)结果 + 一致性评分。
模型分歧较大时降低交易评级。
"""

from __future__ import annotations

import logging
import warnings

import pandas as pd

logger = logging.getLogger(__name__)

# 抑制训练时的警告
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning, module="xgboost")


def analyze(prices: pd.DataFrame, symbol: str = "", horizon: int = 5, **kwargs) -> dict:
    """训练3个模型并展示各自预测和一致性评分。

    使用3个模型进行3分类预测 (涨/跌/平):
      - XGBoost (如果可用)
      - RandomForest
      - GradientBoosting

    每个模型在最近一段数据上预测方向，汇总一致性。

    Args:
        prices: OHLCV DataFrame
        symbol: 品种代码
        horizon: 预测窗口（几根K线后）

    Returns:
        dict: 模型集成展示数据
    """
    if prices is None or len(prices) < 100:
        return _empty(symbol, "数据不足（需至少100根K线）")

    closes = prices["close"].astype(float)

    # ── 生成标签: 未来horizon根K线的方向 ──
    future_return = closes.shift(-horizon) / closes - 1
    # 3分类: 涨(1) / 平(0) / 跌(-1)
    labels = pd.Series(0, index=closes.index)
    labels[future_return > 0.005] = 1    # 涨超0.5%
    labels[future_return < -0.005] = -1  # 跌超0.5%

    # ── 特征工程 ──
    features = _build_features(prices)
    if features is None or len(features) < 80:
        return _empty(symbol, "特征工程数据不足")

    # 对齐标签
    valid_mask = features.notna().all(axis=1) & labels.notna()
    X = features[valid_mask]
    y = labels[valid_mask]

    if len(X) < 80:
        return _empty(symbol, "有效数据不足80条")

    # ── 训练/测试分割 (最后20%做测试) ──
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    # ── 训练3个模型 ──
    model_results = []
    all_preds = []

    # 模型1: RandomForest (始终可用)
    try:
        rf_pred, rf_prob, rf_acc, rf_importance = _train_rf(X_train, y_train, X_test, y_test)
        model_results.append({
            "name": "RandomForest",
            "signal": int(rf_pred),
            "signal_label": {1: "涨", -1: "跌", 0: "平"}.get(int(rf_pred), "平"),
            "confidence": round(float(max(rf_prob)), 3),
            "probabilities": {k: round(float(v), 3) for k, v in zip(["跌", "平", "涨"], rf_prob)},
            "accuracy": round(rf_acc, 3),
            "top_features": rf_importance[:5] if rf_importance else [],
        })
        all_preds.append(int(rf_pred))
    except Exception as e:
        logger.warning("RF训练失败: %s", e)

    # 模型2: XGBoost (可选)
    xgb_pred, xgb_prob, xgb_acc, xgb_importance = _train_xgb(X_train, y_train, X_test, y_test)
    if xgb_pred is not None:
        model_results.append({
            "name": "XGBoost",
            "signal": int(xgb_pred),
            "signal_label": {1: "涨", -1: "跌", 0: "平"}.get(int(xgb_pred), "平"),
            "confidence": round(float(max(xgb_prob)), 3),
            "probabilities": {k: round(float(v), 3) for k, v in zip(["跌", "平", "涨"], xgb_prob)},
            "accuracy": round(xgb_acc, 3),
            "top_features": xgb_importance[:5] if xgb_importance else [],
        })
        all_preds.append(int(xgb_pred))

    # 模型3: GradientBoosting (始终可用)
    try:
        gb_pred, gb_prob, gb_acc, gb_importance = _train_gb(X_train, y_train, X_test, y_test)
        model_results.append({
            "name": "GradientBoosting",
            "signal": int(gb_pred),
            "signal_label": {1: "涨", -1: "跌", 0: "平"}.get(int(gb_pred), "平"),
            "confidence": round(float(max(gb_prob)), 3),
            "probabilities": {k: round(float(v), 3) for k, v in zip(["跌", "平", "涨"], gb_prob)},
            "accuracy": round(gb_acc, 3),
            "top_features": gb_importance[:5] if gb_importance else [],
        })
        all_preds.append(int(gb_pred))
    except Exception as e:
        logger.warning("GB训练失败: %s", e)

    if not all_preds:
        return _empty(symbol, "所有模型训练失败")

    # ── 一致性评分 ──
    from collections import Counter
    counts = Counter(all_preds)
    most_common_count = counts.most_common(1)[0][1]
    agreement_score = round(most_common_count / len(all_preds), 3)

    # 集成信号: 多数投票
    ensemble_signal = counts.most_common(1)[0][0]
    high_disagreement = agreement_score < 0.67  # 3个模型中2个以上不一致

    return {
        "symbol": symbol,
        "models": model_results,
        "agreement_score": agreement_score,
        "ensemble_signal": ensemble_signal,
        "ensemble_signal_label": {1: "涨", -1: "跌", 0: "平"}.get(ensemble_signal, "平"),
        "high_disagreement": high_disagreement,
        "n_models": len(model_results),
        "horizon": horizon,
        "strategy_impact": "none",
    }


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "models": [],
        "agreement_score": 0,
        "ensemble_signal": 0,
        "ensemble_signal_label": "未知",
        "high_disagreement": True,
        "n_models": 0,
        "horizon": 5,
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

        # SMA 比率
        for w in [5, 10, 20, 60]:
            sma = closes.rolling(w).mean()
            features[f'close_sma{w}_ratio'] = closes / (sma + 1e-10)

        # RSI
        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        features['rsi_14'] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        features['macd_hist'] = macd - signal

        # ATR
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        features['atr_14'] = tr.rolling(14).mean()

        # 布林带
        sma20 = closes.rolling(20).mean()
        std20 = closes.rolling(20).std()
        features['bb_pct'] = (closes - (sma20 - 2 * std20)) / (4 * std20 + 1e-10)

        # 动量
        features['roc_5'] = closes / closes.shift(5) - 1
        features['roc_10'] = closes / closes.shift(10) - 1

        # 成交量
        vol_sma5 = vols.rolling(5).mean()
        features['vol_ratio'] = vols / (vol_sma5 + 1e-10)

        return features
    except Exception as e:
        logger.warning("特征构建失败: %s", e)
        return None


def _train_rf(X_train, y_train, X_test, y_test):
    """训练 RandomForest。"""
    from sklearn.ensemble import RandomForestClassifier
    model = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)[-1]
    prob = model.predict_proba(X_test)[-1]
    acc = model.score(X_test, y_test)
    importance = sorted(
        zip(X_train.columns, model.feature_importances_),
        key=lambda x: x[1], reverse=True
    )
    return pred, prob, acc, [f"{n}({v:.3f})" for n, v in importance[:5]]


def _train_xgb(X_train, y_train, X_test, y_test):
    """训练 XGBoost (可选)。"""
    try:
        import xgboost as xgb
        # 将标签映射为 0,1,2 (XGBoost要求)
        label_map = {-1: 0, 0: 1, 1: 2}
        y_train_mapped = y_train.map(label_map)
        y_test_mapped = y_test.map(label_map)

        model = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05, random_state=42, verbosity=0)
        model.fit(X_train, y_train_mapped, eval_set=[(X_test, y_test_mapped)], verbose=False)
        pred_mapped = model.predict(X_test)[-1]
        prob = model.predict_proba(X_test)[-1]
        acc = model.score(X_test, y_test_mapped)
        # 映射回原始标签
        reverse_map = {0: -1, 1: 0, 2: 1}
        pred = reverse_map.get(pred_mapped, 0)
        importance = sorted(
            zip(X_train.columns, model.feature_importances_),
            key=lambda x: x[1], reverse=True
        )
        return pred, prob, acc, [f"{n}({v:.3f})" for n, v in importance[:5]]
    except ImportError:
        return None, None, 0, []
    except Exception as e:
        logger.warning("XGBoost训练失败: %s", e)
        return None, None, 0, []


def _train_gb(X_train, y_train, X_test, y_test):
    """训练 GradientBoosting。"""
    from sklearn.ensemble import GradientBoostingClassifier
    model = GradientBoostingClassifier(n_estimators=200, max_depth=5, learning_rate=0.05, random_state=42)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)[-1]
    prob = model.predict_proba(X_test)[-1]
    acc = model.score(X_test, y_test)
    importance = sorted(
        zip(X_train.columns, model.feature_importances_),
        key=lambda x: x[1], reverse=True
    )
    return pred, prob, acc, [f"{n}({v:.3f})" for n, v in importance[:5]]
