# 回测候选案例 — 2025-06-29

## 可回测标准
- 有 pre_launch 信息
- 有 day_1 或 week_1 信息
- 有 month_1 / month_3 / year_1 或 current 结果
- final_outcome 相对明确
- 来源等级至少 B
- 阶段时间线不混乱

## 已识别的可回测案例

### 高质量回测案例（有完整时间线）

| # | 名称 | 路径类型 | 时间线完整性 | 证据质量 | 回测价值 |
|---|------|---------|------------|---------|---------|
| 1 | Lovable | breakout | pre_launch → year_1 | B | 高 |
| 2 | marblism | monetization_failed | pre_launch → kill | B | 高 |
| 3 | Google Stadia | high_exposure_low_retention | pre_launch → kill | A | 极高 |
| 4 | Photopea | long_compound | pre_launch → current | B | 高 |
| 5 | Postiz | niche_compound | pre_launch → year_1 | B | 高 |
| 6 | Chatbase | breakout | pre_launch → year_1 | B | 高 |
| 7 | Post Bridge | strong_pain_tool | pre_launch → year_1 | B | 高 |

### 中等质量回测案例（有部分时间线）

| # | 名称 | 路径类型 | 时间线完整性 | 证据质量 | 回测价值 |
|---|------|---------|------------|---------|---------|
| 8 | AudioPen | strong_pain_tool | pre_launch → current | B | 中 |
| 9 | Kleo | short_burst→niche | pre_launch → year_1 | B | 中 |
| 10 | Formula Bot | community_slow_burn | pre_launch → year_1 | B | 中 |
| 11 | Papermark | niche_compound | pre_launch → year_1 | B | 中 |
| 12 | Flodesk | breakout | pre_launch → year_1 | B | 中 |
| 13 | Interview Coder | short_burst_decay | pre_launch → month_1 | B | 中 |

## 回测方法

### Round 1: 只给 pre_launch 信息
预测 day_1、week_1、month_1、month_3、year_1 路径

### Round 2: 给 pre_launch + day_1 信息
预测 week_1 之后路径

### Round 3: 给 pre_launch + day_1 + week_1 信息
预测 month_1 之后路径

### 每轮输出
1. 预测路径类型
2. 预测依据
3. 关键转移点
4. 置信度
5. 后续真实路径
6. 是否命中
7. 偏差原因

## 回测统计

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| path_type 命中率 | 待计算 | > 50% |
| final_outcome 命中率 | 待计算 | > 60% |
| 高估变量 | 待分析 | — |
| 低估变量 | 待分析 | — |
| 最常见误差 | 待分析 | — |
| 需要调整的权重 | 待分析 | — |

## 建议

1. **优先回测 Google Stadia** — 最高质量案例，有完整时间线
2. **优先回测 marblism** — 失败路径典型，校准价值高
3. **优先回测 Lovable** — 成功路径典型，校准价值高
4. **批量回测 IH 案例** — 有相似数据结构，可批量处理

## 不适合回测的案例
- 缺少 pre_launch 信息
- 时间线不清晰
- 来源等级低于 B
- 数据冲突严重
