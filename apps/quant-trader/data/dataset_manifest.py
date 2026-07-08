"""数据集清单 — 训练样本的完整追溯。

每条训练/验证/OOS 记录都必须绑定:
- dataset_id
- data_hash
- feature_hash
- label_hash
- source_name
- source_type
- is_synthetic

没有这些字段，不允许训练。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def compute_hash(data: str) -> str:
    """计算 SHA-256 哈希。"""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_data_hash(df_rows: list[dict]) -> str:
    """计算数据哈希 (基于关键字段)。"""
    content = "|".join(
        f"{r.get('trading_date', r.get('date', ''))}:{r.get('open', '')}:{r.get('high', '')}:{r.get('low', '')}:{r.get('close', '')}:{r.get('volume', '')}"
        for r in df_rows[:1000]  # 采样前1000行
    )
    return compute_hash(content)


def compute_feature_hash(feature_names: list[str]) -> str:
    """计算特征名列表哈希。"""
    return compute_hash("|".join(sorted(feature_names)))


def compute_label_hash(label_values: list[float]) -> str:
    """计算标签值哈希。"""
    content = "|".join(f"{v:.6f}" for v in label_values[:1000])
    return compute_hash(content)


def create_dataset_manifest(
    dataset_id: str,
    symbols: list[str],
    timeframe: str,
    start_date: str,
    end_date: str,
    rows: int,
    source_name: str,
    source_type: str,
    data_hash: str,
    feature_hash: str,
    label_hash: str,
    train_period: str,
    val_period: str,
    oos_period: str,
    feature_names: list[str],
    label_names: list[str],
    is_synthetic: bool = False,
    generator_version: str = "1.0",
) -> dict:
    """创建数据集清单。"""
    manifest = {
        "dataset_id": dataset_id,
        "created_at": datetime.now().isoformat(),
        "generator_version": generator_version,
        "symbols": symbols,
        "timeframe": timeframe,
        "train_period": train_period,
        "val_period": val_period,
        "oos_period": oos_period,
        "rows": rows,
        "source": {
            "name": source_name,
            "type": source_type,
            "is_synthetic": is_synthetic,
        },
        "hashes": {
            "data_hash": data_hash,
            "feature_hash": feature_hash,
            "label_hash": label_hash,
        },
        "feature_schema": {
            "version": "v14_1.0",
            "names": feature_names,
            "count": len(feature_names),
        },
        "label_schema": {
            "names": label_names,
            "count": len(label_names),
        },
    }

    if is_synthetic:
        manifest["warning"] = "⚠️ 合成数据，禁止用于训练/回测/paper"
        manifest["allowed_for_training"] = False
        manifest["allowed_for_backtest"] = False
        manifest["allowed_for_paper"] = False

    return manifest


def save_manifest(manifest: dict, output_dir: str | Path):
    """保存清单到文件。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"manifest_{manifest['dataset_id']}.json"
    path = output_dir / filename

    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return path


def load_manifest(path: str | Path) -> dict:
    """加载清单。"""
    with open(Path(path), "r", encoding="utf-8") as f:
        return json.load(f)


def validate_manifest_for_training(manifest: dict) -> tuple[bool, list[str]]:
    """验证清单是否允许训练。

    Returns:
        (allowed, reasons)
    """
    issues = []

    # 检查合成数据
    if manifest.get("source", {}).get("is_synthetic", False):
        issues.append("BLOCKED: 合成数据禁止用于训练")

    # 检查必需字段
    required_fields = ["dataset_id", "data_hash", "feature_hash", "label_hash"]
    for field in required_fields:
        if not manifest.get(field) and not manifest.get("hashes", {}).get(field.replace("_hash", "_hash")):
            issues.append(f"BLOCKED: 缺少必需字段 {field}")

    # 检查 hash 非空
    hashes = manifest.get("hashes", {})
    for key in ["data_hash", "feature_hash", "label_hash"]:
        if not hashes.get(key):
            issues.append(f"BLOCKED: {key} 为空")

    return len(issues) == 0, issues


def validate_manifest_for_paper(manifest: dict) -> tuple[bool, list[str]]:
    """验证清单是否允许 paper。"""
    issues = []

    if manifest.get("source", {}).get("is_synthetic", False):
        issues.append("BLOCKED: 合成数据禁止用于 paper")

    # 检查 data quality
    if manifest.get("data_quality", {}).get("critical_count", 0) > 0:
        issues.append("BLOCKED: 存在 critical 数据质量问题")

    return len(issues) == 0, issues
