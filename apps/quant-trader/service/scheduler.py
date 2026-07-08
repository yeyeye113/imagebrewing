"""定时任务调度器 — 开盘时段自动预测。

功能:
  - 期货夜盘预测 (20:50)
  - 期货日盘预测 (08:50)
  - 股票预测 (09:20)
  - 回测验证 (15:30)
  - 实时监控 (每10分钟)

用法:
    python -m quanttrader.service.scheduler
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("quanttrader.scheduler")

# 缓存文件
CACHE_DIR = Path("logs/scheduler")
PREDICTIONS_FILE = CACHE_DIR / "predictions.json"
STATS_FILE = CACHE_DIR / "stats.json"


def get_next_task_time(now: dt.datetime) -> tuple[str, dt.datetime]:
    """计算下一个任务时间。"""
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()

    # 周末不运行
    if weekday >= 5:
        # 下周一 08:50
        next_day = now + dt.timedelta(days=(7 - weekday))
        return "期货日盘预测", next_day.replace(hour=8, minute=50, second=0)

    current_minutes = hour * 60 + minute

    # 任务时间表 (分钟数)
    tasks = [
        (20 * 60 + 50, "期货夜盘预测"),  # 20:50
        (8 * 60 + 50, "期货日盘预测"),  # 08:50
        (9 * 60 + 20, "股票预测"),  # 09:20
        (15 * 60 + 30, "回测验证"),  # 15:30
    ]

    # 找下一个任务
    for task_minutes, task_name in tasks:
        if current_minutes < task_minutes:
            target = now.replace(hour=task_minutes // 60, minute=task_minutes % 60, second=0)
            return task_name, target

    # 所有任务都过了，明天第一个
    next_day = now + dt.timedelta(days=1)
    return "期货夜盘预测", next_day.replace(hour=20, minute=50, second=0)


def run_scheduled_task(task_name: str):
    """运行定时任务。"""
    log.info(f"运行定时任务: {task_name}")

    if "期货" in task_name:
        _run_futures_prediction()
    elif "股票" in task_name:
        _run_stocks_prediction()
    elif "回测" in task_name:
        _run_backtest_validation()


def _run_futures_prediction():
    """期货预测任务。"""
    import os

    os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")

    from quanttrader.forecast import run_forecast

    symbols = ["I", "RB", "SC", "AU", "AG", "CU", "AL", "ZN", "TA", "MA"]
    results = run_forecast(futures=symbols)

    _save_prediction("futures", results)
    log.info(f"期货预测完成: {len(results)} 品种")


def _run_stocks_prediction():
    """股票预测任务。"""
    import os

    os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")

    from quanttrader.forecast import run_forecast

    symbols = ["600519", "000858", "002594", "601318", "600036"]
    results = run_forecast(stocks=symbols)

    _save_prediction("stocks", results)
    log.info(f"股票预测完成: {len(results)} 品种")


def _run_backtest_validation():
    """回测验证任务。"""
    from quanttrader.tracker import verify_predictions

    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    results = verify_predictions(yesterday)
    log.info(f"回测验证完成: {len(results)} 条")


def _save_prediction(market: str, results: list):
    """保存预测结果。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    result_rows: list[dict] = []
    data = {
        "timestamp": dt.datetime.now().isoformat(),
        "market": market,
        "count": len(results),
        "results": result_rows,
    }

    for r in results:
        result_rows.append(
            {
                "symbol": r.symbol,
                "signal": r.signal,
                "confidence": r.confidence,
                "price": r.forecast_price,
                "high": r.high_point,
                "low": r.low_point,
                "target": r.take_profit,
                "stop": r.stop_loss,
            }
        )

    # 追加到文件
    existing = []
    if PREDICTIONS_FILE.exists():
        try:
            existing = json.loads(PREDICTIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing.append(data)
    # 只保留最近50条
    if len(existing) > 50:
        existing = existing[-50:]

    PREDICTIONS_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def start_scheduler():
    """启动定时调度器。"""
    log.info("定时任务调度器启动")

    while True:
        now = dt.datetime.now()
        task_name, next_time = get_next_task_time(now)

        wait_seconds = (next_time - now).total_seconds()
        log.info(f"下一个任务: {task_name} @ {next_time.strftime('%H:%M')} (等待{wait_seconds / 60:.0f}分钟)")

        # 等待到任务时间
        while dt.datetime.now() < next_time:
            time.sleep(30)

        # 运行任务
        try:
            run_scheduled_task(task_name)
        except Exception as e:
            log.error(f"任务失败: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_scheduler()
