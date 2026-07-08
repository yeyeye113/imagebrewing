"""SQLite 存储层 — 因子数据持久化。

表结构:
    factors  — 因子元数据 (name, params, description)
    factor_values — 因子值 (factor_id, symbol, date, value)
    returns       — 未来收益率 (symbol, date, ret_1d, ret_5d, ...)
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "factor_db.sqlite"


class FactorDB:
    """轻量 SQLite 因子仓库，线程安全（每个调用一个连接）。"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else _DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── connection ──────────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS factors (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    NOT NULL,
                    params      TEXT    DEFAULT '{}',
                    description TEXT    DEFAULT '',
                    created_at  TEXT    DEFAULT (datetime('now')),
                    UNIQUE(name, params)
                );

                CREATE TABLE IF NOT EXISTS factor_values (
                    factor_id INTEGER NOT NULL,
                    symbol    TEXT    NOT NULL,
                    date      TEXT    NOT NULL,
                    value     REAL,
                    PRIMARY KEY (factor_id, symbol, date),
                    FOREIGN KEY (factor_id) REFERENCES factors(id)
                );

                CREATE TABLE IF NOT EXISTS returns (
                    symbol  TEXT NOT NULL,
                    date    TEXT NOT NULL,
                    ret_1d  REAL,
                    ret_5d  REAL,
                    ret_10d REAL,
                    ret_20d REAL,
                    PRIMARY KEY (symbol, date)
                );

                CREATE INDEX IF NOT EXISTS idx_factor_values_factor ON factor_values(factor_id);
                CREATE INDEX IF NOT EXISTS idx_factor_values_symbol ON factor_values(symbol);
                CREATE INDEX IF NOT EXISTS idx_factor_values_date   ON factor_values(date);
                CREATE INDEX IF NOT EXISTS idx_returns_symbol ON returns(symbol);
                CREATE INDEX IF NOT EXISTS idx_returns_date   ON returns(date);
                """
            )

    # ── factor CRUD ────────────────────────────────────────────

    def upsert_factor(self, name: str, params: str = "{}", description: str = "") -> int:
        """插入或获取因子 ID。"""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO factors (name, params, description) VALUES (?, ?, ?)",
                (name, params, description),
            )
            row = conn.execute("SELECT id FROM factors WHERE name=? AND params=?", (name, params)).fetchone()
            return int(row[0])

    def list_factors(self) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql("SELECT * FROM factors", conn)

    # ── batch write ────────────────────────────────────────────

    def write_factor_values(self, factor_id: int, df: pd.DataFrame) -> int:
        """批量写入因子值。df 需含 columns: symbol, date, value。
        date 列会自动转为字符串。返回写入行数。
        """
        rows = []
        for _, r in df.iterrows():
            rows.append(
                (
                    factor_id,
                    str(r["symbol"]),
                    str(r["date"])[:10],
                    float(r["value"]) if pd.notna(r["value"]) else None,
                )
            )
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO factor_values (factor_id, symbol, date, value) VALUES (?, ?, ?, ?)",
                rows,
            )
            return len(rows)

    def write_returns(self, df: pd.DataFrame) -> int:
        """批量写入未来收益。df 需含 columns: symbol, date, ret_1d[, ret_5d, ...]。"""
        rows = []
        for _, r in df.iterrows():
            rows.append(
                (
                    str(r["symbol"]),
                    str(r["date"])[:10],
                    _safe_float(r.get("ret_1d")),
                    _safe_float(r.get("ret_5d")),
                    _safe_float(r.get("ret_10d")),
                    _safe_float(r.get("ret_20d")),
                )
            )
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO returns (symbol, date, ret_1d, ret_5d, ret_10d, ret_20d) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            return len(rows)

    # ── read ───────────────────────────────────────────────────

    def read_factor_values(self, factor_id: int, symbols: list[str] | None = None) -> pd.DataFrame:
        with self._conn() as conn:
            if symbols:
                ph = ",".join("?" * len(symbols))
                return pd.read_sql(
                    f"SELECT symbol, date, value FROM factor_values WHERE factor_id=? AND symbol IN ({ph})",
                    conn,
                    params=[factor_id, *symbols],
                )
            return pd.read_sql(
                "SELECT symbol, date, value FROM factor_values WHERE factor_id=?",
                conn,
                params=(factor_id,),
            )

    def read_returns(self, symbols: list[str] | None = None) -> pd.DataFrame:
        with self._conn() as conn:
            if symbols:
                ph = ",".join("?" * len(symbols))
                return pd.read_sql(
                    f"SELECT * FROM returns WHERE symbol IN ({ph})",
                    conn,
                    params=symbols,
                )
            return pd.read_sql("SELECT * FROM returns", conn)

    # ── meta ───────────────────────────────────────────────────

    def count(self, table: str = "factor_values") -> int:
        # 表名无法参数化, 用白名单校验防注入
        if table not in ("factor_values", "factors", "returns"):
            raise ValueError(f"unknown table: {table!r}")
        with self._conn() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def symbols(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT DISTINCT symbol FROM factor_values ORDER BY symbol").fetchall()
            return [r[0] for r in rows]

    def factor_id_by_name(self, name: str, params: str = "{}") -> int | None:
        with self._conn() as conn:
            row = conn.execute("SELECT id FROM factors WHERE name=? AND params=?", (name, params)).fetchone()
            return row[0] if row else None


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None and pd.notna(v) else None
    except (ValueError, TypeError):
        return None
