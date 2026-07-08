# 模拟器校准报告 — 最终版 (2025-06-29)

## 回测结果汇总

### 产品自身质量回测（5 案例）
| 案例 | 预测 | 实际 | 概率 | 结果 |
|------|------|------|------|------|
| Lovable | clear_success | clear_success | 92.5% | ✅ |
| Photopea | long_compound | long_compound | 96.9% | ✅ |
| Marblism | dead | dead | 56.0% | ✅ |
| Google Stadia | dead | dead | 51.9% | ✅ |
| Post Bridge | low_alive | moderate_success | 39.1% | ⚠️ TOP-2 |
**准确率: 80% exact, 80% top-2**

### 扩展回测（20 案例含外部因素）
| 类型 | 准确率 | 案例数 |
|------|--------|--------|
| 产品自身失败 | 80% | 5 |
| 外部因素死亡 | 35% | 20 |
| **总体** | **50%** | **25** |

### 模型能力边界
| 能力 | 状态 | 说明 |
|------|------|------|
| 评估产品自身质量 | ✅ 可用 | 留存、痛点、清晰度 |
| 预测外部因素死亡 | ❌ 不可用 | 大公司砍产品、治理、硬件 |
| 预测爆款概率 | ⚠️ 低置信 | 需要更多数据 |
| 预测长期复利 | ✅ 可用 | 留存强+竞争适中 |

## 校准的关键参数

### 1. 权重（v3）
| 维度 | 权重 | 校准依据 |
|------|------|---------|
| product | 0.20 | 产品好不等于成功 |
| market | 0.18 | 市场大不等于能赢 |
| distribution | 0.12 | 分发弱≠死亡（Photopea） |
| retention | 0.22 | 留存是长期复利关键 |
| business | 0.13 | 变现是生存基础 |
| risk | 0.15 | 风险是最大死因 |

### 2. 留存曲线（两段式）
```
D1-D7: R(d) = D1 * (d/1)^(-0.3)   // 快速衰减
D7-D180: R(d) = D7 * (d/7)^(-0.12) // 缓慢衰减
```

### 3. 分发-留存失衡惩罚
```
distRetentionGap = max(0, distribution - retention - 0.1)
distRetentionPenalty = 1 - distRetentionGap * 0.9
```

### 4. 外部风险因子
```
externalRisk = platformDependency*0.3 + legalRisk*0.25 + founderDependency*0.2 + copycatRisk*0.15 + competition*0.1
externalDeathChance = externalRisk * (1 - differentiation*0.5)
```

### 5. 死亡条件
```
users < 30 → dead
externalDeathChance > 0.5 && users < 2000 && random < chance → dead
users < 100 && finalRetention < 0.12 → dead
distRetentionGap > 0.25 && users < 400 → dead
retention < 0.45 && distribution > retention+0.2 && users < 800 → dead
```

### 6. 长期复利条件
```
retentionFactor > 0.6 && finalRetention > 0.15 && competition < 75
```

## 案例库统计

| 指标 | 数值 |
|------|------|
| 总候选案例 | 82+ |
| 结构化案例 | 30 |
| 接受案例 | 25 |
| 深挖案例 | 3 |
| 回测案例 | 25 |
| 路径类型覆盖 | 8/13 |

## 下一步改进方向

1. **添加 benchmark 数据** — 需要真实产品数据来校准排名率
2. **添加更多长期复利案例** — 当前只有 2 个
3. **添加更多 low_exposure_death 案例** — 需要更多低曝光死亡数据
4. **改进变现模型** — 需要更多收入数据
5. **添加平台差异模型** — 不同平台的推荐机制不同
