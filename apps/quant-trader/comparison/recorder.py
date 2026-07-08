"""交易决策记录器 — 记录每次交易决策及模拟结果，供对比分析。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class TradeDecision:
    """单次交易决策快照 — 决策时刻记录。"""

    id: str = ""  # {date}_{symbol}_{seq}
    ts: str = ""  # ISO timestamp
    symbol: str = ""
    action: str = ""  # BUY / SELL / HOLD
    signal: int = 0  # 1=多, -1=空, 0=中性
    price: float = 0.0  # 决策时价格
    confidence: float = 0.0  # LLM 置信度 0-1
    reason: str = ""  # LLM 决策理由
    hexagram: str = ""  # 保留字段，兼容旧记录
    news_sentiment: float = 0.0  # 保留字段，兼容旧记录
    equity: float = 0.0  # 决策时权益
    position: float = 0.0  # 决策时仓位
    # 回测对照
    backtest_price: float = 0.0  # 回测同时间点价格
    backtest_signal: int = 0  # 回测信号
    backtest_confidence: float = 0.0  # 回测置信度


@dataclass
class SimulationRecord:
    """单笔交易的模拟执行记录 — 平仓时刻追加。"""

    decision_id: str = ""
    symbol: str = ""
    entry_ts: str = ""
    exit_ts: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    qty: float = 0.0
    notional: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""  # STOP_LOSS / TAKE_PROFIT / SIGNAL / MANUAL
    total_fees: float = 0.0
    # 回测对照
    backtest_pnl: float = 0.0
    backtest_pnl_pct: float = 0.0
    # 模拟偏差
    slippage: float = 0.0  # 实际成交价 - 决策价
    fill_delay_ms: float = 0.0  # 模拟成交延迟


@dataclass
class ComparisonRecord:
    """完整对比记录 — 决策 + 模拟结果 + 归因标签。"""

    decision: TradeDecision = field(default_factory=TradeDecision)
    simulation: SimulationRecord = field(default_factory=SimulationRecord)
    attribution: dict = field(default_factory=dict)  # 归因分析结果


class TradeRecorder:
    """交易记录管理器 — 写入/读取/查询决策和模拟记录。"""

    def __init__(self, log_dir: str | Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._decisions_path = self.log_dir / "comparison_decisions.jsonl"
        self._simulations_path = self.log_dir / "comparison_simulations.jsonl"
        self._records_path = self.log_dir / "comparison_records.json"

    # ── 写入 ────────────────────────────────────────────────────────

    def record_decision(self, decision: TradeDecision) -> str:
        """记录一次交易决策，返回 decision_id。"""
        if not decision.id:
            decision.id = self._make_id(decision.symbol)
        if not decision.ts:
            decision.ts = datetime.now().isoformat()
        self._append_jsonl(self._decisions_path, asdict(decision))
        return decision.id

    def record_simulation(self, record: SimulationRecord) -> None:
        """记录模拟执行结果。"""
        self._append_jsonl(self._simulations_path, asdict(record))

    def save_comparison(self, comp: ComparisonRecord) -> None:
        """保存完整对比记录（合并到 JSON 数组）。"""
        records = self.load_all()
        records.append(comp)
        self._save_json(self._records_path, records)

    # ── 读取 ────────────────────────────────────────────────────────

    def load_all(self) -> list[ComparisonRecord]:
        """加载所有对比记录 — 优先从 JSON 快照读取，否则动态配对 JSONL。"""
        # 优先读取已保存的完整快照
        if self._records_path.exists():
            raw = json.loads(self._records_path.read_text(encoding="utf-8"))
            out = []
            for r in raw:
                d = TradeDecision(**r.get("decision", {}))
                s = SimulationRecord(**r.get("simulation", {}))
                a = r.get("attributions", {})
                out.append(ComparisonRecord(decision=d, simulation=s, attribution=a))
            return out
        # 动态配对: decisions + simulations JSONL → ComparisonRecord
        return self._pair_from_jsonl()

    def load_decisions(self) -> list[TradeDecision]:
        """加载所有决策记录。"""
        return [TradeDecision(**r) for r in self._read_jsonl(self._decisions_path)]

    def load_simulations(self) -> list[SimulationRecord]:
        """加载所有模拟记录。"""
        return [SimulationRecord(**r) for r in self._read_jsonl(self._simulations_path)]

    def get_by_symbol(self, symbol: str) -> list[ComparisonRecord]:
        """按标的过滤对比记录。"""
        return [r for r in self.load_all() if r.decision.symbol == symbol]

    def get_by_date(self, date_str: str) -> list[ComparisonRecord]:
        """按日期过滤（ts 开头匹配）。"""
        return [r for r in self.load_all() if r.decision.ts.startswith(date_str)]

    def get_recent(self, n: int = 20) -> list[ComparisonRecord]:
        """获取最近 n 条记录。"""
        return self.load_all()[-n:]

    # ── 统计 ────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """快速统计摘要。"""
        records = self.load_all()
        if not records:
            return {"total": 0}
        sims = [r.simulation for r in records]
        wins = [s for s in sims if s.pnl > 0]
        losses = [s for s in sims if s.pnl <= 0]
        total_pnl = sum(s.pnl for s in sims)
        return {
            "total": len(records),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(records) if records else 0.0,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(records), 2) if records else 0.0,
            "avg_slippage": round(sum(s.slippage for s in sims) / len(sims), 4) if sims else 0.0,
        }

    # ── 内部方法 ─────────────────────────────────────────────────────

    @staticmethod
    def _make_id(symbol: str) -> str:
        now = datetime.now()
        return f"{now.strftime('%Y%m%d_%H%M%S')}_{symbol}"

    @staticmethod
    def _append_jsonl(path: Path, row: dict) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    @staticmethod
    def _save_json(path: Path, records: list[ComparisonRecord]) -> None:
        data = []
        for r in records:
            d = asdict(r.decision)
            s = asdict(r.simulation)
            data.append({"decision": d, "simulation": s, "attributions": r.attribution})
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _pair_from_jsonl(self) -> list[ComparisonRecord]:
        """动态配对 decisions + simulations JSONL → ComparisonRecord 列表。"""
        decisions = self.load_decisions()
        simulations = self.load_simulations()
        # 按 decision_id 索引模拟记录
        sim_map: dict[str, SimulationRecord] = {}
        for s in simulations:
            if s.decision_id:
                sim_map[s.decision_id] = s
        paired = []
        for d in decisions:
            s = sim_map.get(d.id, SimulationRecord())
            paired.append(ComparisonRecord(decision=d, simulation=s))
        # 未配对的模拟记录 (decision_id 为空) 追加到末尾
        paired_ids = {d.id for d in decisions}
        for s in simulations:
            if s.decision_id and s.decision_id not in paired_ids:
                paired.append(ComparisonRecord(simulation=s))
        return paired
