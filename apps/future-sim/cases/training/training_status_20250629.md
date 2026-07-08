# 训练状态 — 2025-06-29

## 累计指标

| 指标 | 数值 |
|------|------|
| total_candidates_found | 62+ |
| total_cases_structured | 3 (lovable-001 + 9 待完成) |
| total_cases_accepted | 0 (待 QA) |
| total_cases_watchlist | 0 |
| total_cases_rejected | 0 |
| total_duplicate_cases | 0 |
| total_deep_dive_cases | 0 |
| backtest_candidate_count | 0 |

## 已采集来源质量评估

| 来源 | 可用性 | 数据质量 | 证据等级 |
|------|--------|---------|---------|
| Product Hunt | ✅ 可访问 | 中（PH votes + 描述） | B |
| GitHub Trending | ✅ 可访问 | 中（stars + 描述） | B |
| Indie Hackers 案例库 | ✅ 可访问 | 高（MRR + 创始人故事） | A-B |
| Indie Hackers 付费内容 | ❌ 付费墙 | — | — |
| Hacker News | ✅ 可访问 | 低（讨论多，数据少） | C |
| Chrome Web Store | ✅ 可访问 | 中（评分 + 描述） | B |
| Killed by Google | ✅ 可访问 | 高（时间线 + 产品信息） | A |
| GitHub deprecated | ✅ 可访问 | 中（stars + 描述） | B |
| Failory | ❌ 被限流 | — | — |
| 中文来源 | ⚠️ 未搜索 | 待评估 | — |

## 证据等级分布（当前）

| 等级 | 比例 | 说明 |
|------|------|------|
| A 级 | 25% | 官方数据、GitHub、商店页面 |
| B 级 | 40% | 创始人故事、媒体报道 |
| C 级 | 25% | 社区讨论、用户评论 |
| D 级 | 10% | 推断数据 |
| E 级 | 0% | 未使用 |

## 路径类型分布

| 路径类型 | 样本数 | 是否充足 |
|---------|--------|---------|
| breakout | 3 | 需要更多 |
| niche_compound | 3 | 需要更多 |
| strong_pain_tool | 3 | 需要更多 |
| long_compound | 2 | 严重不足 |
| short_burst_decay | 1 | 严重不足 |
| low_exposure_death | 0 | 缺失 |
| high_exposure_low_retention | 0 | 缺失 |
| channel_dependent | 0 | 缺失 |
| competition_crushed | 0 | 缺失 |
| monetization_failed | 1 | 严重不足 |
| technical_debt_collapse | 0 | 缺失 |
| pivot_success | 0 | 缺失 |
| abandoned_by_creator | 0 | 缺失 |

## 当前数据质量评分
**55/100** — 中低质量

主要问题：
1. 缺失低曝光死亡案例
2. 缺失失败路径详细数据
3. 缺失留存率数据
4. 缺失收入增长曲线
5. 缺失用户增长时间线

## 明日搜索方向
1. **优先搜索失败案例** — 需要 low_exposure_death、high_exposure_low_retention、competition_crushed 路径
2. **搜索长期复利案例** — 需要 3 年以上增长数据
3. **搜索中文独立开发案例** — 扩展来源多样性
4. **搜索 AI 工具 postmortem** — 最高价值方向
5. **搜索 Chrome 插件增长故事** — 新类型数据

## 模拟器调整建议
1. **降低 distribution_power 权重** — 初期分发弱不代表死亡
2. **增加 retention_design 权重** — 留存是长期复利的关键
3. **增加 pain_intensity 权重** — 痛点是最强预测变量
4. **增加 competition_pressure 阈值** — 竞争强但有差异化可以存活
5. **限制爆款概率输出** — 当前数据不足以支持精确爆款预测
