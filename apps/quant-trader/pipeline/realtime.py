"""实时行情 — WebSocket / fallback HTTP 轮询。

支持来源：
  - akshare 实时快照（HTTP，无需 token）
  - WebSocket 扩展点（预留）

A 股免费 WebSocket 服务不稳定，默认走 akshare HTTP 快照。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RealtimeQuote:
    """标准化实时行情快照。"""

    symbol: str
    name: str = ""
    price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close_prev: float = 0.0
    volume: int = 0
    amount: float = 0.0
    change_pct: float = 0.0
    timestamp: _dt.datetime = field(default_factory=_dt.datetime.now)
    source: str = "akshare"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_trading(self) -> bool:
        """是否在交易时段（粗判）。"""
        now = self.timestamp.time()
        morning = _dt.time(9, 30) <= now <= _dt.time(11, 30)
        afternoon = _dt.time(13, 0) <= now <= _dt.time(15, 0)
        return morning or afternoon


def get_realtime(symbol: str) -> RealtimeQuote:
    """获取单只股票的实时行情快照。

    优先 akshare HTTP 快照；失败返回零值对象。
    """
    code = _normalize_code(symbol)
    try:
        return _akshare_realtime(code)
    except Exception as exc:
        print(f"[pipeline.realtime] akshare failed for {symbol}: {exc}")
        return RealtimeQuote(symbol=symbol, source="error")


def get_realtime_batch(symbols: list[str]) -> list[RealtimeQuote]:
    """批量获取实时行情。"""
    return [get_realtime(s) for s in symbols]


# ── akshare 实时快照 ────────────────────────────────────────
def _akshare_realtime(code: str) -> RealtimeQuote:
    import akshare as ak

    # akshare 实时行情：stock_zh_a_spot_em 返回全市场快照，过滤目标
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("akshare returned empty realtime data")

    # 列名中文 → 英文映射
    col_map = {
        "代码": "code",
        "名称": "name",
        "最新价": "price",
        "今开": "open",
        "最高": "high",
        "最低": "low",
        "昨收": "close_prev",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "change_pct",
    }
    df = df.rename(columns=col_map)
    row = df[df["code"] == code]
    if row.empty:
        raise RuntimeError(f"Symbol {code} not found in realtime data")

    r = row.iloc[0]
    return RealtimeQuote(
        symbol=code,
        name=str(r.get("name", "")),
        price=float(r.get("price", 0) or 0),
        open=float(r.get("open", 0) or 0),
        high=float(r.get("high", 0) or 0),
        low=float(r.get("low", 0) or 0),
        close_prev=float(r.get("close_prev", 0) or 0),
        volume=int(r.get("volume", 0) or 0),
        amount=float(r.get("amount", 0) or 0),
        change_pct=float(r.get("change_pct", 0) or 0),
        timestamp=_dt.datetime.now(),
        source="akshare",
    )


def _normalize_code(symbol: str) -> str:
    """提取 6 位数字代码。"""
    import re

    digits = re.findall(r"\d{6}", str(symbol))
    if not digits:
        raise ValueError(f"Invalid symbol: {symbol!r}")
    return str(digits[0])
