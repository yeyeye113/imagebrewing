# 未来模拟引擎 · 代码审查与修复方案（REVIEW_FIXPLAN）

> 审查日期：2026-06-29
> 审查范围：`src/` 全量（引擎 / 回测 / 状态 / 存储 / 工具 / 类型 / App / 8 页面 / UI 组件）
> 性质：静态代码审查 + 修复路线图。所有结论均附文件行号。

---

## 一、项目概况

- **定位**：作品未来推演引擎（Future Simulation Engine）——用蒙特卡洛在浏览器 Web Worker 中模拟一个软件/App/游戏/内容作品未来的成败分布、排名率、敏感性与策略对比。
- **技术栈**：React 19 + TypeScript 6 + Vite 8 + Zustand + Recharts + idb(IndexedDB) + Tailwind 4。
- **核心链路**：`PROMPT.md`(设计) → `types/index.ts` → `workers/simulator.ts`(蒙特卡洛心脏) → `lib/backtest.ts`(回测) → `store/index.ts` → `lib/database.ts` → `pages/*`。
- **整体评价**：分层清晰、类型完整、纯本地运行无隐私风险；但作为"推演引擎"，数值可信度与若干致命缺陷较突出，结果当前不可全信。

---

## 二、问题总览

### P0 致命级（编译失败 / 崩溃 / 假数据）

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| ① | 类型名 `BackTestCase` 未定义（应为 `BacktestCase`）| `lib/backtest.ts:343` | `tsc` 编译失败 |
| ② | 进度页用 `Math.random()` 编造"实时统计"展示给用户 | `pages/RunPage.tsx:104-108,151-159` | 欺骗性 UI，数字乱跳 |
| ③ | `Math.max(...runs.map(...))` 大数组 spread | `workers/simulator.ts:602` | 深度模式(10万)栈溢出崩溃 |

### P1 严重级（数值/逻辑错误，结论失真）

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| ④ | 排名率用 `composite.overall` 套线性公式硬算，非真实分布/benchmark | `simulator.ts:565-577` | 排名率失真，违背 PROMPT 设计 |
| ⑤ | 敏感性量纲错误：概率 `top10 × 10000` 当用户数阈值 | `simulator.ts:459-460` | 敏感性数值无意义 |
| ⑥ | 敏感性 `top10Change` 用各自分布 P90 → 恒约等于 0 | `simulator.ts:450-453` | 该影响因子永久失效 |
| ⑦ | 结果分类 if-else 顺序错乱，`long_compound` 抢在 `blockbuster` 前 | `simulator.ts:316-363` | 爆款几乎不可达，分类错误 |
| ⑧ | 增长/流失 `×stepDays` 但留存按绝对天数 + 隐藏系数，三粒度结果不一致 | `simulator.ts:244-285` | day/week/month 结论不可比 |
| ⑨ | 策略名与实际加成变量不符（`clarity_boost` 实加 `qualityFactor`）| `simulator.ts:190` | 策略对比名不副实 |
| ⑰ | `config.scenarios` 引擎从不消费——场景选择是摆设 | `simulator.ts` / `ConfigPage` | 多场景模拟未实现 |
| ⑱ | 主模拟 `strategyBoosts` 写死 `{}`，用户策略勾选无效 | `pages/RunPage.tsx:73-78` | 策略配置与引擎脱节 |
| ⑲ | 报告"最可能未来路径"为写死静态文案 | `pages/ReportPage.tsx:78-93` | 假个性化，千篇一律 |

### P2 性能级

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| ⑩ | 期望百分位 `O(n²)`（每 run 全量扫描）| `simulator.ts:556-563` | 深度模式 Worker 假死 |
| ⑪ | 敏感性/策略在聚合内同步串行，`cancel` 无法中断 | `simulator.ts` + `RunPage` | 取消无效、长阻塞 |
| ⑫ | `powerLawRandom` 同一表达式计算两次 | `simulator.ts:45-47` | 轻微性能浪费 |

### P3 可维护性 / 代码质量

| # | 问题 | 位置 |
|---|---|---|
| ⑬ | 死代码：`totalUsers`(`:280`)、`getVariableScore`(`:756`)、疑似未用的 `betaRandom/gammaRandom` |
| ⑭ | 重复实现：`clamp/normalRandom/quantile` 散落多处（`RunPage.tsx:194` 重复 clamp）|
| ⑮ | 状态割裂：store 的 `isSimulating/progress` 未用；`saveCurrentProject()` 未 await |
| ⑯ | 魔法数字遍地（8000/2.5/0.008/0.005…）无注释无配置 |
| ⑳ | 敏感性表 `+/-` 号语义错乱 | `pages/DashboardPage.tsx:236-237` |
| ㉑ | `generateMarkdownReport(result: any)` 放弃类型；`<pre>` 渲染 markdown 源码 | `pages/ReportPage.tsx` |

---

## 三、修复批次计划

### 批次一：P0 止血（~1h）
1. `backtest.ts:343` → `BacktestCase[]`
2. `simulator.ts:602` → `runs.reduce((m,r)=>Math.max(m,r.pathData.length),0)`
3. `RunPage.tsx` → 移除假随机中间统计（后续由 worker 回传真实 `currentStats`）
- **关卡**：`npx tsc --noEmit` 必须先绿

### 批次二：P1 可信度（~1–2 天）
4. 排名率改为基于模拟 `finalUsers` 真实分布；接 `cases/` 案例库做 benchmark，无库时如实标注
5. 敏感性改用统一基准阈值，修正量纲与 `top10Change` 恒零
6. 重排结果分类（先高用户 blockbuster/clear_success，再 long_compound/niche），补单测
7. 统一以"天"为内部积分步长，granularity 仅决定采样输出，移除隐藏系数
8. 策略名与加成变量对齐；让 `config.scenarios`/`strategies` 真正驱动模拟
9. 报告未来路径基于 `pathData` + 概率动态生成
- **关卡**：跑 `cases/backtest/run_backtest.mjs` 对比命中率不下降

### 批次三：P2 性能（~2–3h）
10. 期望百分位用秩计算降到 `O(n log n)`
11. 敏感性/策略移入 worker 分批 + 响应 `cancelled`
12. `powerLawRandom` 抽变量算一次
- **关卡**：`npm run build` + 三档冒烟无崩溃

### 批次四：P3 整洁（~0.5–1h）
13. 清死代码、合并重复工具函数、魔法数字具名化、`ReportPage` 去 `any` + 富文本渲染
- **关卡**：tsc/build 复绿

---

## 四、验证策略（每批必跑）

1. `npx tsc --noEmit`（批次一后必绿）
2. `npm run build`（Vite 构建通过）
3. `node cases/backtest/run_backtest.mjs`（对比修复前后命中率，防回归）
4. 手动冒烟：quick/standard/deep × day/week/month 各跑一次，确认无崩溃、结果一致性提升

---

## 五、工量与风险

- **总工量**：约 1.5–2.5 人/天；批次一 ~1h 即可消除崩溃与编译失败。
- **风险**：批次二改分类/粒度会改变历史结果分布，须用回测守护命中率；排名率与场景化是较大改动，建议小步提交、逐项验证。
- **注意**：本项目位于 `C:\Users\眠\未来模拟引擎\`，不在主工作区内。

---

## 六、执行结果（已完成 · 2026-06-29）

本轮已按计划全部落地并验证：

- **批次一 P0**：编译错误 `BackTestCase`、`RunPage` 假数据 UI、spread 爆栈 — 全修；顺带清掉 `tsconfig` 弃用 `baseUrl` 及连带暴露的 8 个预存类型错。
- **批次二 P1**：回测守门员根治(import 真引擎)、敏感性量纲与 top10Change、策略名对齐、排名率派生自模拟分布、报告未来路径动态化、分类顺序(blockbuster 可达)、时间粒度统一(三粒度一致)、scenarios/strategies 真正生效。
- **批次三 P2**：O(n²)→O(1) 期望百分位、worker async 可中断、`powerLawRandom` 去重。
- **批次四 P3**：删死代码(`totalUsers`/`getVariableScore`/`betaRandom`/`gammaRandom`)、`ReportPage` 去 any、魔法数字提取为 `SIM` 常量。
- **增强**：worker 回传真实中间统计、回测案例库 5→9、路由页面懒加载分包。

**验证**：`tsc --noEmit` exit 0；`npm run build` exit 0；真引擎回测 9 案例 Exact 66.7% / Top-2 77.8%；场景生效实锤(死亡率随场景单调变化)。

**遗留(非阻塞)**：边界案例(Cursor/Arc)进一步校准。
