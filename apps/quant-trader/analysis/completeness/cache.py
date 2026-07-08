"""预测缓存层 — 避免重复训练模型。

缓存策略:
  - 方向/状态/成本: 缓存10分钟（计算快，但避免重复）
  - 模型集成/特征/WF/OOS: 缓存60分钟（计算慢，训练一次够用）
  - 缓存键: symbol + module_name
  - 过期后自动重新计算
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

_CACHE_DIR = Path("logs/prediction_cache")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 各模块缓存时长（秒）
_TTL = {
    "direction": 600,       # 10分钟
    "regime": 600,          # 10分钟
    "cost": 600,            # 10分钟
    "ensemble": 3600,       # 60分钟
    "features": 3600,       # 60分钟
    "walk_forward": 3600,   # 60分钟
    "oos": 3600,            # 60分钟
}


def get_cached(symbol: str, module: str) -> dict | None:
    """读取缓存，过期返回None。"""
    cache_file = _CACHE_DIR / f"{symbol}_{module}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        ts = data.get("_cached_at", 0)
        ttl = _TTL.get(module, 600)
        if time.time() - ts > ttl:
            return None  # 过期
        return data
    except Exception:
        return None


def set_cache(symbol: str, module: str, data: dict) -> None:
    """写入缓存。"""
    data["_cached_at"] = time.time()
    cache_file = _CACHE_DIR / f"{symbol}_{module}.json"
    try:
        cache_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:
        pass


def cached_analyze(symbol: str, module: str, fn: Callable[..., dict], *args, **kwargs) -> dict:
    """带缓存的分析函数包装。

    symbol 用作缓存键，不会传递给 fn。
    """
    # 确保 symbol 不会同时作为位置参数和关键字参数传递
    kwargs.pop("symbol", None)
    cached = get_cached(symbol, module)
    if cached is not None:
        cached["_from_cache"] = True
        return cached
    result = fn(*args, symbol=symbol, **kwargs)
    if "error" not in result:
        set_cache(symbol, module, result)
    result["_from_cache"] = False
    return result


def clear_cache(symbol: str | None = None) -> int:
    """清除缓存。返回清除数量。"""
    count = 0
    for f in _CACHE_DIR.glob("*.json"):
        if symbol is None or f.name.startswith(symbol):
            f.unlink()
            count += 1
    return count
