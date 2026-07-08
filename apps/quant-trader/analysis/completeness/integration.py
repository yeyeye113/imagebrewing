"""集成层 — 把 completeness 模块与现有系统打通。

功能:
  1. SymbolFilter 硬规则集成
  2. config 费率读取
  3. strategy_params 准确率数据
  4. tracker 记录预测结果
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 路径常量 ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_STRATEGY_PARAMS = _PROJECT_ROOT / "logs" / "strategy_params.json"
_TRACKER_FILE = _PROJECT_ROOT / "logs" / "completeness_tracker.json"


# ══════════════════════════════════════════════════════════════════
# 1. SymbolFilter 集成
# ══════════════════════════════════════════════════════════════════

def get_symbol_filter_status(symbol: str) -> dict:
    """查询 SymbolFilter 对某品种的允许状态。

    Returns:
        dict: {
            allowed: bool,           # 是否在白名单
            allowed_directions: [],  # 允许的方向 ["BUY"] / ["SELL"] / ["BUY","SELL"]
            tier: str,               # tier1 / tier2 / tier3 / ""
            accuracy: float,         # 历史准确率
            sample_count: int,       # 样本数
            confidence_mult: float,  # 仓位乘数
        }
    """
    try:
        from quanttrader.engine.symbol_filter import SymbolFilter
        sf = SymbolFilter()
        allowed = sf.get_allowed()

        # 标准化 symbol (去掉尾部0: SI0 -> SI, M0 -> M)
        normalized = symbol.rstrip("0") if symbol.endswith("0") else symbol

        # 查找匹配的条目
        directions = []
        tier = ""
        accuracy = 0.0
        sample_count = 0
        confidence_mult = 1.0

        for sym_key, dirs in allowed.items():
            if sym_key in (symbol, normalized):
                directions = dirs
                break

        # 从 strategy_params.json 读取详细信息
        if _STRATEGY_PARAMS.exists():
            try:
                params = json.loads(_STRATEGY_PARAMS.read_text(encoding="utf-8"))
                for combo in params.get("best_combos_10d", []):
                    name = combo.get("name", "")
                    combo_sym = name.split("+")[0] if "+" in name else name
                    combo_dir = name.split("+")[1] if "+" in name else ""
                    if combo_sym in (symbol, normalized):
                        if combo_dir in directions:
                            tier = combo.get("tier", "")
                            accuracy = combo.get("acc", 0) / 100
                            sample_count = combo.get("n", 0)
                            # tier 对应的仓位乘数
                            if tier == "tier1":
                                confidence_mult = 1.2
                            elif tier == "tier2":
                                confidence_mult = 1.0
                            elif tier == "tier3":
                                confidence_mult = 0.8
            except Exception as e:
                logger.warning("读取 strategy_params.json 失败: %s", e)

        return {
            "allowed": len(directions) > 0,
            "allowed_directions": directions,
            "tier": tier,
            "accuracy": accuracy,
            "sample_count": sample_count,
            "confidence_mult": confidence_mult,
        }
    except Exception as e:
        logger.warning("SymbolFilter 加载失败: %s", e)
        return {
            "allowed": False,
            "allowed_directions": [],
            "tier": "",
            "accuracy": 0,
            "sample_count": 0,
            "confidence_mult": 1.0,
        }


def check_direction_with_filter(symbol: str, predicted_direction: int) -> dict:
    """将方向预测与 SymbolFilter 硬规则交叉验证。

    Args:
        symbol: 品种代码
        predicted_direction: 预测方向 (1=涨, -1=跌, 0=平)

    Returns:
        dict: {
            filter_allows: bool,        # SymbolFilter 是否允许该方向
            predicted_direction: int,    # 原始预测
            final_direction: int,        # 最终方向 (被过滤后)
            reason: str,                 # 决策原因
            filter_status: dict,         # SymbolFilter 完整状态
        }
    """
    filter_status = get_symbol_filter_status(symbol)

    if not filter_status["allowed"]:
        return {
            "filter_allows": False,
            "predicted_direction": predicted_direction,
            "final_direction": 0,  # HOLD
            "reason": f"{symbol} 不在 SymbolFilter 白名单中",
            "filter_status": filter_status,
        }

    allowed_dirs = filter_status["allowed_directions"]
    dir_map = {1: "BUY", -1: "SELL", 0: "HOLD"}
    predicted_dir_str = dir_map.get(predicted_direction, "HOLD")

    if predicted_dir_str in allowed_dirs:
        return {
            "filter_allows": True,
            "predicted_direction": predicted_direction,
            "final_direction": predicted_direction,
            "reason": f"SymbolFilter 允许 {predicted_dir_str} ({filter_status['tier']})",
            "filter_status": filter_status,
        }
    else:
        return {
            "filter_allows": False,
            "predicted_direction": predicted_direction,
            "final_direction": 0,  # HOLD
            "reason": f"SymbolFilter 不允许 {predicted_dir_str}，允许: {allowed_dirs}",
            "filter_status": filter_status,
        }


# ══════════════════════════════════════════════════════════════════
# 2. Config 费率读取
# ══════════════════════════════════════════════════════════════════

def load_trading_costs(symbol: str = "") -> dict:
    """从 config.yaml 或默认值加载交易成本参数。

    Returns:
        dict: {commission_rate, slippage_bps, impact_model}
    """
    defaults = {
        "commission_rate": 0.00005,  # 万0.5
        "slippage_bps": 2.0,
        "impact_model": "sqrt",
    }

    # 尝试从 config_base.yaml 读取
    config_files = [
        _PROJECT_ROOT / "config_llm.yaml",
        _PROJECT_ROOT / "config_base.yaml",
        _PROJECT_ROOT / "config.yaml",
    ]

    for cfg_path in config_files:
        if cfg_path.exists():
            try:
                import yaml
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                risk = cfg.get("risk", {})
                if "commission" in risk:
                    defaults["commission_rate"] = risk["commission"]
                if "slippage" in risk:
                    defaults["slippage_bps"] = risk["slippage"] * 10000  # 转换为基点
                break
            except Exception:
                pass

    # 品种特定费率 (期货各品种手续费不同)
    symbol_rates = {
        "AU0": 0.0001,   # 黄金 万1
        "AG0": 0.00005,  # 白银 万0.5
        "CU0": 0.00005,  # 铜 万0.5
        "RB0": 0.0001,   # 螺纹钢 万1
        "I0": 0.0001,    # 铁矿石 万1
        "SI0": 0.00003,  # 工业硅 万0.3
        "M0": 0.00005,   # 豆粕 万0.5
    }
    if symbol in symbol_rates:
        defaults["commission_rate"] = symbol_rates[symbol]

    return defaults


# ══════════════════════════════════════════════════════════════════
# 3. Strategy Params 准确率数据
# ══════════════════════════════════════════════════════════════════

def get_combo_accuracy(symbol: str) -> dict:
    """获取某品种+方向组合的历史准确率。

    Returns:
        dict: {buy_acc, sell_acc, buy_n, sell_n, best_direction, best_acc}
    """
    result: dict[str, Any] = {
        "buy_acc": 0.0, "sell_acc": 0.0,
        "buy_n": 0, "sell_n": 0,
        "best_direction": "HOLD", "best_acc": 0.0,
    }

    if not _STRATEGY_PARAMS.exists():
        return result

    try:
        params = json.loads(_STRATEGY_PARAMS.read_text(encoding="utf-8"))
        normalized = symbol.rstrip("0") if symbol.endswith("0") else symbol

        for combo in params.get("best_combos_10d", []):
            name = combo.get("name", "")
            parts = name.split("+")
            if len(parts) != 2:
                continue
            combo_sym, combo_dir = parts
            if combo_sym != symbol and combo_sym != normalized:
                continue
            acc = combo.get("acc", 0) / 100
            n = combo.get("n", 0)
            if combo_dir == "BUY":
                result["buy_acc"] = acc
                result["buy_n"] = n
            elif combo_dir == "SELL":
                result["sell_acc"] = acc
                result["sell_n"] = n

        # 最佳方向
        if result["buy_acc"] > result["sell_acc"] and result["buy_acc"] > 0:
            result["best_direction"] = "BUY"
            result["best_acc"] = result["buy_acc"]
        elif result["sell_acc"] > result["buy_acc"] and result["sell_acc"] > 0:
            result["best_direction"] = "SELL"
            result["best_acc"] = result["sell_acc"]
    except Exception as e:
        logger.warning("读取准确率失败: %s", e)

    return result


# ══════════════════════════════════════════════════════════════════
# 4. Tracker 记录预测结果
# ══════════════════════════════════════════════════════════════════

def track_prediction(symbol: str, module: str, result: dict) -> None:
    """记录预测结果到 tracker，用于后续验证准确率。"""
    import datetime as dt

    record = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "module": module,
        "direction": result.get("direction", result.get("ensemble_signal", 0)),
        "confidence": result.get("confidence", result.get("agreement_score", 0)),
    }

    # 追加到 tracker 文件
    records = []
    if _TRACKER_FILE.exists():
        try:
            records = json.loads(_TRACKER_FILE.read_text(encoding="utf-8"))
        except Exception:
            records = []

    records.append(record)
    # 只保留最近 1000 条
    records = records[-1000:]

    try:
        _TRACKER_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("写入 tracker 失败: %s", e)


def get_tracker_stats(symbol: str = "", days: int = 7) -> dict:
    """获取 tracker 统计: 近期预测准确率。"""
    if not _TRACKER_FILE.exists():
        return {"total": 0, "accuracy": 0}

    try:
        records = json.loads(_TRACKER_FILE.read_text(encoding="utf-8"))
        import datetime as dt
        cutoff = (dt.datetime.now() - dt.timedelta(days=days)).isoformat()
        recent = [r for r in records if r.get("timestamp", "") > cutoff]
        if symbol:
            recent = [r for r in recent if r.get("symbol") == symbol]
        return {"total": len(recent), "records": recent[-20:]}
    except Exception:
        return {"total": 0, "accuracy": 0}
