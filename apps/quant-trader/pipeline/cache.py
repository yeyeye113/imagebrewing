"""本地文件缓存 — CSV 格式，自动过期。无需额外依赖。"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
from typing import Any

import pandas as pd


class FileCache:
    """基于文件系统的 DataFrame 缓存。

    缓存结构::

        cache_dir/
            meta.json          # symbol → {path, ts, params}
            {hash}.csv         # 实际数据

    Parameters
    ----------
    cache_dir : str
        缓存目录。
    ttl : int
        缓存有效期（秒），默认 3600。
    """

    def __init__(self, cache_dir: str = "cache", ttl: int = 3600) -> None:
        self.dir = pathlib.Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.dir / "meta.json"
        self.ttl = ttl
        self._meta: dict[str, Any] = self._load_meta()

    # ── 公开接口 ──────────────────────────────────────────────
    def get(self, symbol: str, **params: Any) -> pd.DataFrame | None:
        """按 symbol + params 查缓存，命中且未过期返回 DataFrame，否则 None。"""
        key = self._key(symbol, params)
        entry = self._meta.get(key)
        if entry is None:
            return None

        # 过期
        if time.time() - entry["ts"] > self.ttl:
            self._evict(key)
            return None

        csv_path = self.dir / entry["path"]
        if not csv_path.exists():
            self._evict(key)
            return None

        try:
            return pd.read_csv(csv_path, index_col=0, parse_dates=True)
        except Exception:
            self._evict(key)
            return None

    def put(self, symbol: str, df: pd.DataFrame, **params: Any) -> None:
        """写入缓存。"""
        key = self._key(symbol, params)
        # 仅作缓存文件名指纹, 非安全用途
        fname = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:12] + ".csv"
        csv_path = self.dir / fname

        df.to_csv(csv_path, index=True)
        self._meta[key] = {
            "path": fname,
            "ts": time.time(),
            "params": params,
            "rows": len(df),
        }
        self._save_meta()

    def invalidate(self, symbol: str, **params: Any) -> None:
        """手动失效某条缓存。"""
        key = self._key(symbol, params)
        self._evict(key)

    def clear(self) -> int:
        """清空全部缓存，返回删除文件数。"""
        count = 0
        for entry in self._meta.values():
            p = self.dir / entry["path"]
            if p.exists():
                p.unlink()
                count += 1
        self._meta.clear()
        self._save_meta()
        return count

    def stats(self) -> dict[str, Any]:
        """返回缓存统计信息。"""
        total_rows = sum(e.get("rows", 0) for e in self._meta.values())
        total_files = sum(1 for e in self._meta.values() if (self.dir / e["path"]).exists())
        return {
            "entries": len(self._meta),
            "files": total_files,
            "total_rows": total_rows,
            "ttl_seconds": self.ttl,
            "dir": str(self.dir),
        }

    # ── 内部 ──────────────────────────────────────────────────
    @staticmethod
    def _key(symbol: str, params: dict[str, Any]) -> str:
        parts = [symbol] + [f"{k}={v}" for k, v in sorted(params.items()) if v is not None]
        return "|".join(parts)

    def _load_meta(self) -> dict[str, Any]:
        if self.meta_path.exists():
            try:
                data = json.loads(self.meta_path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}

    def _save_meta(self) -> None:
        self.meta_path.write_text(json.dumps(self._meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _evict(self, key: str) -> None:
        entry = self._meta.pop(key, None)
        if entry:
            p = self.dir / entry["path"]
            if p.exists():
                p.unlink()
            self._save_meta()
