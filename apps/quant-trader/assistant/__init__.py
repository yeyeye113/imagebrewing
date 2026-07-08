"""半自动AI量化辅助决策系统。

系统只负责筛选、评分、提示、记录；最终下单由人确认。

预留接口：
  - DataSource: 行情数据源（可接入akshare/sina/yahoo等）
  - SignalSource: 信号源（可接入v530/LLM/技术指标等）
  - Notifier: 通知渠道（可接入微信/钉钉/Telegram等）
  - Storage: 存储后端（可接入SQLite/JSON/CSV等）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# ══════════════════════════════════════════════════════════════════
#  数据源接口 — 接入新数据源只需实现这个接口
# ══════════════════════════════════════════════════════════════════

class DataSource(ABC):
    """行情数据源接口。"""

    @abstractmethod
    def get_closes(self, symbol: str, days: int = 300) -> list[float]:
        """获取收盘价序列。"""

    @abstractmethod
    def get_highs(self, symbol: str, days: int = 300) -> list[float]:
        """获取最高价序列。"""

    @abstractmethod
    def get_lows(self, symbol: str, days: int = 300) -> list[float]:
        """获取最低价序列。"""

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """获取当前最新价。"""


class SinaFuturesSource(DataSource):
    """Sina期货数据源（现有）。"""

    def get_closes(self, symbol: str, days: int = 300) -> list[float]:
        from quanttrader.data.sina_futures import get_history
        df = get_history(symbol, days=days)
        if df is None:
            return []
        return [float(v) for v in df["close"].tolist()]

    def get_highs(self, symbol: str, days: int = 300) -> list[float]:
        from quanttrader.data.sina_futures import get_history
        df = get_history(symbol, days=days)
        if df is None:
            return []
        return [float(v) for v in df["high"].tolist()]

    def get_lows(self, symbol: str, days: int = 300) -> list[float]:
        from quanttrader.data.sina_futures import get_history
        df = get_history(symbol, days=days)
        if df is None:
            return []
        return [float(v) for v in df["low"].tolist()]

    def get_current_price(self, symbol: str) -> float:
        closes = self.get_closes(symbol, days=5)
        return closes[-1] if closes else 0.0


# ══════════════════════════════════════════════════════════════════
#  信号源接口 — 接入新信号源只需实现这个接口
# ══════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """一个交易信号。"""
    symbol: str
    direction: str  # "BUY" / "SELL" / "HOLD"
    confidence: float = 0.0
    reason: str = ""
    source: str = ""  # 信号来源标识


class SignalSource(ABC):
    """信号源接口。"""

    @abstractmethod
    def generate(self, symbol: str, closes: list[float], highs: list[float], lows: list[float]) -> Signal:
        """生成交易信号。"""


class V530SignalSource(SignalSource):
    """v530高低点预测信号源（现有）。"""

    def generate(self, symbol: str, closes: list[float], highs: list[float], lows: list[float]) -> Signal:
        import numpy as np

        from quanttrader.predictor.hl_predict import predict_range

        c = np.array(closes)
        h = np.array(highs)
        lo = np.array(lows)
        pred = predict_range(symbol, c, h, lo)

        if pred is None:
            return Signal(symbol=symbol, direction="HOLD", reason="v530预测不可用", source="v530")

        if not pred.is_tradeable:
            return Signal(symbol=symbol, direction="HOLD", reason=f"波动{pred.range_pct:.1f}%<1.5%", source="v530")

        # v530只预测范围，方向交给SymbolFilter
        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=pred.range_pct / 10,
            reason=f"v530: 高={pred.predicted_high:.1f} 低={pred.predicted_low:.1f} 范围={pred.range_pct:.1f}%",
            source="v530",
        )


# ══════════════════════════════════════════════════════════════════
#  通知接口 — 接入新通知渠道只需实现这个接口
# ══════════════════════════════════════════════════════════════════

class Notifier(ABC):
    """通知渠道接口。"""

    @abstractmethod
    def send(self, title: str, content: str, level: str = "info") -> bool:
        """发送通知。返回是否成功。"""


class LogNotifier(Notifier):
    """日志通知（现有）。"""

    def send(self, title: str, content: str, level: str = "info") -> bool:
        import logging
        log = logging.getLogger("assistant")
        log.info(f"[{level}] {title}: {content}")
        return True


# ══════════════════════════════════════════════════════════════════
#  存储接口 — 接入新存储后端只需实现这个接口
# ══════════════════════════════════════════════════════════════════

class Storage(ABC):
    """存储后端接口。"""

    @abstractmethod
    def save(self, key: str, data: Any) -> None:
        """保存数据。"""

    @abstractmethod
    def load(self, key: str) -> Any:
        """加载数据。"""

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """列出所有key。"""


class JsonFileStorage(Storage):
    """JSON文件存储（现有）。"""

    def __init__(self, base_dir: str = "logs"):
        from pathlib import Path
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: Any) -> None:
        import json
        path = self.base_dir / f"{key}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, key: str) -> Any:
        import json
        path = self.base_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def list_keys(self, prefix: str = "") -> list[str]:
        return [f.stem for f in self.base_dir.glob(f"{prefix}*.json")]


# ══════════════════════════════════════════════════════════════════
#  全局实例 — 默认配置，可随时替换
# ══════════════════════════════════════════════════════════════════

# 默认数据源
data_source: DataSource = SinaFuturesSource()

# 默认信号源列表（可追加）
signal_sources: list[SignalSource] = [V530SignalSource()]

# 默认通知器
notifier: Notifier = LogNotifier()

# 默认存储
storage: Storage = JsonFileStorage()


def register_data_source(source: DataSource) -> None:
    """注册新的数据源。"""
    global data_source
    data_source = source


def register_signal_source(source: SignalSource) -> None:
    """追加新的信号源。"""
    signal_sources.append(source)


def register_notifier(n: Notifier) -> None:
    """注册新的通知器。"""
    global notifier
    notifier = n


def register_storage(s: Storage) -> None:
    """注册新的存储后端。"""
    global storage
    storage = s
