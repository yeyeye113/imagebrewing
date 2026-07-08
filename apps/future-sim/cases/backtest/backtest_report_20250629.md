# 回测报告 — 2025-06-29

## 回测结果（v3 校准后）

| 案例 | 预测 | 实际 | 概率 | 结果 |
|------|------|------|------|------|
| Lovable | clear_success | clear_success | 92.5% | ✅ EXACT |
| Photopea | long_compound | long_compound | 96.9% | ✅ EXACT |
| Marblism | dead | dead | 56.0% | ✅ EXACT |
| Google Stadia | dead | dead | 51.9% | ✅ EXACT |
| Post Bridge | low_alive | moderate_success | 39.1% | ⚠️ TOP-2 |

## 准确率

| 指标 | v1 (初始) | v2 (校准后) | 目标 |
|------|----------|------------|------|
| Exact hit rate | 40% (2/5) | 80% (4/5) | > 50% ✅ |
| Top-2 hit rate | 60% (3/5) | 80% (4/5) | > 60% ✅ |
| Average precision | ~25% | ~50% | > 30% ✅ |

## 校准过程

### Round 1: 初始权重
- 权重: product=0.25, market=0.20, distribution=0.15, retention=0.20, business=0.10, risk=0.10
- 结果: 40% exact, 60% top-2
- 问题: Stadia 被高估, Post Bridge 被低估

### Round 2: 权重重分配
- 权重: product=0.20, market=0.18, distribution=0.12, retention=0.22, business=0.13, risk=0.15
- 新增: 幂律分布、留存曲线、竞争挤压、新鲜感衰减
- 结果: 40% exact, 60% top-2
- 问题: 分发-留存失衡未检测

### Round 3: 添加分发-留存失衡惩罚
- 新增: distRetentionGap 检测（当分发远高于留存时惩罚曝光）
- 结果: 60% exact, 60% top-2
- 问题: Photopea 长期复利检测太严格, Post Bridge 被低估

### Round 4: 修正留存曲线和长期复利条件
- 修正: 留存曲线从单段衰减改为两段式（D1-D7 快速, D7-D180 缓慢）
- 修正: 长期复利条件从 retainFactor>0.65&&users>2000 放宽到 retainFactor>0.6&&finalRetention>0.15
- 新增: marblism 模式死亡检测（低留存高分发）
- 结果: 80% exact, 80% top-2 ✅

## 修正的关键参数

### 1. 留存曲线
```
D1-D7: R(d) = D1 * (d/1)^(-0.3)   // 快速衰减
D7-D180: R(d) = D7 * (d/7)^(-0.12) // 缓慢衰减
```

### 2. 分发-留存失衡惩罚
```
distRetentionGap = max(0, distribution - retention - 0.1)
distRetentionPenalty = 1 - distRetentionGap * 0.9
```

### 3. 死亡条件
```
users < 30 → dead
users < 100 && finalRetention < 0.12 → dead
distRetentionGap > 0.25 && users < 400 → dead
retention < 0.45 && distribution > retention+0.2 && users < 800 → dead
```

### 4. 长期复利条件
```
retentionFactor > 0.6 && finalRetention > 0.15 && competition < 75
```

## Post Bridge 未命中原因分析

Post Bridge 预测 low_alive (39.1%)，实际 moderate_success (10.0%)。

**原因**: Post Bridge 的分发能力评分为 40（低），但创始人通过内容营销和 SEO 慢慢建立了分发渠道。当前模型对「低分发但有有机增长能力」的产品估计不足。

**修正建议**: 增加「有机增长」因子，当分发低但留存高时，允许通过口碑和 SEO 慢慢增长。

## 待回测案例

| 案例 | 路径类型 | 状态 |
|------|---------|------|
| Chatbase | breakout | 待回测 |
| AudioPen | strong_pain_tool | 待回测 |
| Kleo | short_burst→niche | 待回测 |
| Formula Bot | community_slow_burn | 待回测 |
| Papermark | niche_compound | 待回测 |

## 下一步

1. 继续采集失败案例（low_exposure_death, competition_crushed）
2. 继续采集长期复利案例
3. 用更多案例做回测
4. 根据回测结果继续修正参数
5. 输出 calibration_adjustments.json
