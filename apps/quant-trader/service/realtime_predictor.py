"""实时预测服务 — 开盘时段每10分钟自动预测。

功能:
  - 开盘时段自动预测
  - 结果缓存到JSON
  - 前端实时读取

用法:
    python -m quanttrader.service.realtime_predictor
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("quanttrader.realtime")

# 精选品种
FUTURES_SYMBOLS = ["I", "RB", "SC", "AU", "AG", "CU", "AL", "ZN", "TA", "MA"]
STOCKS_SYMBOLS = ["600519", "000858", "002594", "601318", "600036", "000001", "002415", "601888", "300750", "002475"]

# 缓存文件
CACHE_FILE = Path("logs/realtime_predictions.json")


def is_market_open() -> bool:
    """检查是否在交易时段。"""
    now = dt.datetime.now()
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute
    t = hour * 60 + minute

    # 周末
    if weekday >= 5:
        return False

    # 夜盘: 21:00-02:30
    if t >= 21 * 60 or t < 2 * 60 + 30:
        return True

    # 日盘: 09:00-10:15, 10:30-11:30, 13:30-15:00
    if 9 * 60 <= t < 10 * 60 + 15:
        return True
    if 10 * 60 + 30 <= t < 11 * 60 + 30:
        return True
    if 13 * 60 + 30 <= t < 15 * 60:
        return True

    return False


def run_prediction() -> dict:
    """运行一次预测。"""
    import os

    from quanttrader.forecast import run_forecast

    os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")

    log.info("开始实时预测...")
    t0 = time.time()

    # 期货预测
    futures_results = run_forecast(futures=FUTURES_SYMBOLS)

    # 股票预测
    stocks_results = run_forecast(stocks=STOCKS_SYMBOLS)

    elapsed = time.time() - t0

    # 合并结果
    all_results = []
    for r in futures_results + stocks_results:
        # 提取高低点数据
        support = 0
        resistance = 0
        atr = 0
        trend = ""
        for s in r.steps:
            if s.name == "高低点分析" and s.status == "ok":
                support = s.data.get("nearest_support", 0)
                resistance = s.data.get("nearest_resistance", 0)
                atr = s.data.get("atr", 0)
                trend = s.data.get("trend", "")

        all_results.append(
            {
                "symbol": r.symbol,
                "name": r.name,
                "market": r.market,
                "signal": r.signal,
                "confidence": r.confidence,
                "price": r.forecast_price,
                "support": support,
                "resistance": resistance,
                "atr": atr,
                "trend": trend,
                "target": r.take_profit,
                "stop_loss": r.stop_loss,
                "suggestion": r.suggestion,
                "reason": r.reason,
            }
        )

    # 统计
    long_count = sum(1 for r in all_results if r["signal"] == "LONG")
    short_count = sum(1 for r in all_results if r["signal"] == "SHORT")
    neutral_count = sum(1 for r in all_results if r["signal"] == "NEUTRAL")

    result = {
        "timestamp": dt.datetime.now().isoformat(),
        "elapsed": round(elapsed, 1),
        "count": len(all_results),
        "long_count": long_count,
        "short_count": short_count,
        "neutral_count": neutral_count,
        "results": all_results,
    }

    # 保存缓存
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(
        f"预测完成: {len(all_results)}品种, LONG={long_count} SHORT={short_count} NEUTRAL={neutral_count}, 耗时{elapsed:.1f}秒"
    )

    return result


def run_loop(interval_minutes: int = 10):
    """循环运行预测。"""
    log.info(f"实时预测服务启动, 间隔{interval_minutes}分钟")

    while True:
        if is_market_open():
            try:
                run_prediction()
            except Exception as e:
                log.error(f"预测失败: {e}")
        else:
            log.info("非交易时段，等待...")

        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_loop()
