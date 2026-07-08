"""ML v15 重训流水线 — 带防泄漏检查的可复现训练入口."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ..log import get_logger

logger = get_logger("ml.retrain")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ml_direction_v15.py"
DEFAULT_MODEL = Path("logs/ml_v15_GLOBAL.pkl")


def model_age_days(path: Path | str = DEFAULT_MODEL) -> float | None:
    p = Path(path)
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 86400.0


def should_retrain_v15(
    *,
    max_age_days: float = 7.0,
    min_oos: float = 0.53,
    model_path: Path | str = DEFAULT_MODEL,
) -> tuple[bool, str]:
    """判断是否需要重训 v15（模型缺失 / 过旧 / OOS 弱）。"""
    p = Path(model_path)
    if not p.exists():
        return True, "model_missing"
    age = model_age_days(p)
    if age is not None and age > max_age_days:
        return True, f"stale_{age:.1f}d"
    try:
        import joblib
        md = joblib.load(p)
        oos = float(md.get("oos_accuracy", 0) or 0)
        if oos < min_oos:
            return True, f"low_oos_{oos:.3f}"
    except Exception as e:
        return True, f"load_error_{e}"
    return False, "ok"


def maybe_retrain_v15(
    *,
    horizon: int = 5,
    symbol_list: list[str] | None = None,
    history_days: int = 1260,
    n_trials: int = 2000,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    need, reason = should_retrain_v15()
    if not force and not need:
        logger.info("v15 跳过重训: %s", reason)
        return {"retrained": False, "reason": reason}
    logger.info("v15 触发重训: %s", reason)
    code = run_v15_retrain(
        horizon=horizon,
        symbol_list=symbol_list,
        history_days=history_days,
        n_trials=n_trials,
        dry_run=dry_run,
    )
    return {"retrained": code == 0, "reason": reason, "exit_code": code}


def run_v15_retrain(
    *,
    horizon: int = 5,
    symbol_list: list[str] | None = None,
    output_dir: str | Path = "models/ml_strategy",
    history_days: int = 1260,
    n_trials: int = 2000,
    dry_run: bool = False,
) -> int:
    """调用 scripts/ml_direction_v15.py 训练方向分类器.

    训练前检查脚本是否通过 leakage_guard 基本扫描。
    """
    if not SCRIPT.is_file():
        logger.error("训练脚本不存在: %s", SCRIPT)
        return 1

    try:
        from experiments.quant_repatrol.leakage_guard import check_code_for_leakage

        violations = check_code_for_leakage(SCRIPT)
        critical = [v for v in violations if v.get("severity") == "critical"]
        if critical:
            logger.warning("泄漏检查发现 %d 条 critical, 请先复核: %s", len(critical), critical[:3])
    except Exception as e:
        logger.debug("leakage_guard 跳过: %s", e)

    if dry_run:
        logger.info(
            "dry-run: horizon=%s symbols=%s days=%s out=%s script=%s",
            horizon, symbol_list or "GLOBAL", history_days, output_dir, SCRIPT,
        )
        return 0

    argv = [
        str(SCRIPT),
        "--horizon", str(horizon),
        "--days", str(history_days),
        "--trials", str(n_trials),
    ]
    if symbol_list:
        argv.append("--symbols")
        argv.extend(symbol_list)

    logger.info("启动 v15 重训: %s", " ".join(argv))
    import subprocess
    proc = subprocess.run([sys.executable, *argv], cwd=str(ROOT))
    if proc.returncode == 0:
        try:
            from .ml_v15_signal import invalidate_model_cache
            invalidate_model_cache()
        except Exception:
            pass
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ML v15 方向分类器重训")
    p.add_argument("--horizon", type=int, default=5, help="预测未来 N 根 K 线方向")
    p.add_argument("--symbols", default="", help="逗号分隔品种, 空=GLOBAL")
    p.add_argument("--out", default="models/ml_strategy", help="模型输出目录")
    p.add_argument("--days", type=int, default=1260, help="历史 K 线天数 (~5 年)")
    p.add_argument("--trials", type=int, default=2000, help="超参搜索轮数")
    p.add_argument("--force", action="store_true", help="忽略 should_retrain 强制训练")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    syms = [s.strip() for s in args.symbols.split(",") if s.strip()] or None
    if args.force:
        return run_v15_retrain(
            horizon=args.horizon,
            symbol_list=syms,
            output_dir=args.out,
            history_days=args.days,
            n_trials=args.trials,
            dry_run=args.dry_run,
        )
    res = maybe_retrain_v15(
        horizon=args.horizon,
        symbol_list=syms,
        history_days=args.days,
        n_trials=args.trials,
        dry_run=args.dry_run,
        force=False,
    )
    return 0 if res.get("retrained") or res.get("reason") == "ok" else int(res.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
