// 运行：node cases/backtest/run_smoke_test.ts
// 冒烟测试：模拟聚合、产品诊断、边界输入

import { createDefaultScores, createDefaultExistingData } from '../../src/lib/defaults.ts'
import type { ArtifactProfile, SimulationConfig } from '../../src/types/index.ts'
import {
  computeCompositeScore,
  simulateOneRun,
  setSeed,
  classifyOutcome,
  buildSimulationResult,
} from '../../src/workers/simulator.ts'
import { buildDynamicOptimizationSuggestions } from '../../src/lib/optimization-builder.ts'
import { buildProductInsightReport, insightToFailurePaths, insightToSuccessPaths } from '../../src/lib/product-insight-report.ts'
import { runBacktest, BACKTEST_CASES } from '../../src/lib/backtest.ts'

let passed = 0
let failed = 0

function assert(cond: boolean, msg: string) {
  if (cond) {
    passed++
    console.log(`  ✅ ${msg}`)
  } else {
    failed++
    console.error(`  ❌ ${msg}`)
  }
}

function sumOutcome(op: { dead: number; lowAlive: number; nicheSuccess: number; moderateSuccess: number; clearSuccess: number; blockbuster: number; longCompound: number }): number {
  return op.dead + op.lowAlive + op.nicheSuccess + op.moderateSuccess + op.clearSuccess + op.blockbuster + op.longCompound
}

function miniAggregate(scores: ReturnType<typeof createDefaultScores>, config: SimulationConfig, profile: ArtifactProfile | null) {
  setSeed(42)
  const composite = computeCompositeScore(scores)
  const runs = []
  for (let i = 0; i < config.runs; i++) {
    runs.push(simulateOneRun(composite, scores, config, {}))
  }
  setSeed(undefined)

  const counts = { dead: 0, low_alive: 0, niche_success: 0, moderate_success: 0, clear_success: 0, blockbuster: 0, long_compound: 0 }
  for (const r of runs) counts[r.outcomeClass]++
  const n = runs.length
  const outcomeProbabilities = {
    dead: counts.dead / n,
    lowAlive: counts.low_alive / n,
    nicheSuccess: counts.niche_success / n,
    moderateSuccess: counts.moderate_success / n,
    clearSuccess: counts.clear_success / n,
    blockbuster: counts.blockbuster / n,
    longCompound: counts.long_compound / n,
  }

  const usersSorted = runs.map((r) => r.finalUsers).sort((a, b) => a - b)
  const medianUsers = usersSorted[Math.floor(usersSorted.length / 2)] ?? 0
  const ranking = {
    aboveMedian: 0.5, top30: 0.4, top20: 0.3, top10: 0.2, top5: 0.1, top1: 0.05,
    expectedPercentile: 0.5, medianPercentile: 0.5, worst5Percentile: 0.1, best5Percentile: 1,
    hasBenchmarkData: false,
  }

  const sensitivity = [] as import('../../src/types/index.ts').SensitivityResult[]
  const strategyComparison = [] as import('../../src/types/index.ts').StrategyResult[]
  const optimizationSuggestions = buildDynamicOptimizationSuggestions(sensitivity, ranking, outcomeProbabilities)

  const riskAnalysis = {
    topFailureReason: '测试',
    mostLikelyCrashTime: '第7-30天',
    mostVulnerableVariable: '留存能力',
    negativeEventTriggerProb: 0.1,
    competitorShockProb: 0.2,
    platformDependencyRisk: 0.3,
    updateInterruptionRisk: 0.2,
    technicalDebtDragRisk: 0.2,
  }

  const coreJudgment = {
    mostLikelyOutcome: '中等成功',
    worthInvesting: true,
    biggestRisk: riskAnalysis.topFailureReason,
    topOptimizationDirection: '留存能力',
  }

  return buildProductInsightReport({
    scores,
    composite,
    outcomeProbabilities,
    ranking,
    riskAnalysis,
    sensitivity,
    strategyComparison,
    optimizationSuggestions,
    coreJudgment,
    confidence: 0.6,
    profile,
  })
}

console.log('=== Future-Sim Smoke Tests ===\n')

// 1. 默认分数诊断不崩溃
console.log('1. 默认画像诊断')
const defaultProfile: ArtifactProfile = {
  id: 't1', name: 'Test SaaS', type: 'software', stage: 'mvp',
  description: 'A test product for smoke', targetUsers: 'developers',
  coreFeatures: ['feat'], coreSellingPoints: ['fast'], competitors: ['Notion'],
  channelResources: 'twitter', budget: 'low', teamSize: 2, updateFrequency: 'weekly',
  creatorInfluence: 'low', existingData: createDefaultExistingData(),
  createdAt: '', updatedAt: '',
}
const cfg: SimulationConfig = { runs: 200, periodDays: 90, granularity: 'week', mode: 'quick', scenarios: ['baseline'], strategies: ['original'] }
const insight1 = miniAggregate(createDefaultScores(), cfg, defaultProfile)
assert(insight1.deathReasons.length > 0, '死亡原因非空')
assert(insight1.improvementPlan.length >= 0, '改进方案可生成')
assert(insight1.successOpportunities.length > 0, '增长机会非空')
assert(insight1.actionRoadmap.length >= 0, '路线图可生成')
assert(insight1.artifactContext.typeLabel === '软件', '类型标签正确')

// 2. 极端高分
console.log('\n2. 极端高分画像')
const high = createDefaultScores()
for (const g of Object.keys(high) as (keyof typeof high)[]) {
  for (const k of Object.keys(high[g])) {
    ;(high[g] as Record<string, number>)[k] = 90
  }
}
const insight2 = miniAggregate(high, cfg, { ...defaultProfile, type: 'ai_agent', name: 'Mega AI' })
assert(insight2.verdict.deathProb < 0.5 || insight2.deathReasons.length > 0, '高分低死亡或仍有诊断')
const failPaths = insightToFailurePaths(insight2.deathReasons)
assert(failPaths.every((p) => p.name.length > 0 && p.solution.length > 0), '失败路径字段完整')

// 3. 极端低分
console.log('\n3. 极端低分画像')
const low = createDefaultScores()
for (const g of Object.keys(low) as (keyof typeof low)[]) {
  for (const k of Object.keys(low[g])) {
    ;(low[g] as Record<string, number>)[k] = 15
  }
}
const insight3 = miniAggregate(low, cfg, defaultProfile)
assert(insight3.verdict.deathProb > 0.3, '低分死亡概率偏高')
assert(insight3.verdict.publishReady === false, '低分不建议发布')

// 4. 无 profile
console.log('\n4. 无作品画像')
const insight4 = miniAggregate(createDefaultScores(), cfg, null)
assert(insight4.artifactContext.typeLabel === '未指定', '无画像时类型未指定')

// 5. classifyOutcome 边界
console.log('\n5. classifyOutcome 边界')
const dead = classifyOutcome({
  currentUsers: 10, finalRetention: 0.05, viralBoost: 1, painFactor: 0.2,
  retainFactor: 0.2, distFactor: 0.3, diffFactor: 0.3, distRetentionGap: 0.1,
  externalDeathChance: 0.5, competitionIntensity: 80, legalRisk: 10,
  founderDependency: 30, clarityFactor: 0.4, luck: 0.9,
})
assert(dead === 'dead' || dead === 'low_alive', '极低用户判死或低活')

// 6. 回测概率和
console.log('\n6. 回测概率守恒')
const bt = runBacktest(BACKTEST_CASES[0], { runs: 100, periodDays: 180, granularity: 'week', mode: 'standard', scenarios: ['baseline'], strategies: ['original'], seed: 42 })
const sum = sumOutcome(bt.predicted)
assert(Math.abs(sum - 1) < 0.01, `概率和≈1 (实际 ${sum.toFixed(4)})`)
assert(bt.runs.length === 100, '回测 runs 数量正确')

// 7. 成功路径转换
console.log('\n7. 成功路径转换')
const sp = insightToSuccessPaths(insight1.successOpportunities)
assert(sp.length === insight1.successOpportunities.length, '成功路径条数一致')

// 8. AI 类型专属死因
console.log('\n8. AI Agent 竞品死因')
const aiProfile = { ...defaultProfile, type: 'ai_agent' as const, competitors: ['ChatGPT', 'Claude'] }
const aiScores = createDefaultScores()
aiScores.market.platformDependency = 75
aiScores.risk.copycatRisk = 80
const insightAI = miniAggregate(aiScores, cfg, aiProfile)
const hasApi = insightAI.deathReasons.some((d) => d.id === 'api_commoditization' || d.id === 'competition_shock')
assert(hasApi, 'AI 高平台依赖应触发商品化/竞争死因')

// 9. 完整聚合管线（与 Worker 一致）
console.log('\n9. buildSimulationResult 全链路')
setSeed(7)
const fullScores = createDefaultScores()
fullScores.market.audiencePain = 72
fullScores.retention.retentionPotential = 65
const fullRuns = []
const fullCfg: SimulationConfig = { runs: 150, periodDays: 90, granularity: 'week', mode: 'standard', scenarios: ['baseline'], strategies: ['original', 'retention_boost'], seed: 7 }
const compositeF = computeCompositeScore(fullScores)
for (let i = 0; i < fullCfg.runs; i++) fullRuns.push(simulateOneRun(compositeF, fullScores, fullCfg, {}))
setSeed(undefined)
const fullResult = await buildSimulationResult(fullRuns, fullCfg, fullScores, {}, defaultProfile)
assert(!!fullResult.productInsight, 'productInsight 已生成')
assert(fullResult.productInsight!.deathReasons.length > 0, '全链路死亡原因非空')
assert(fullResult.failurePaths.length > 0, 'failurePaths 来自诊断')
assert(fullResult.sensitivity.length >= 8, '敏感性分析完整')
const opSum = sumOutcome(fullResult.outcomeProbabilities)
assert(Math.abs(opSum - 1) < 0.02, `全链路概率和≈1 (${opSum.toFixed(4)})`)

// 10. v3 三档付费区门控 + 增强分析
console.log('\n10. v3 付费区门控与增强分析')
const v3Scores = createDefaultScores()
v3Scores.market.audiencePain = 70
v3Scores.retention.retentionPotential = 68
v3Scores.distribution.distributionPower = 60

async function runTier(mode: 'quick' | 'standard' | 'deep', runs: number, scenarios: SimulationConfig['scenarios']) {
  const cfg: SimulationConfig = { runs, periodDays: 90, granularity: 'week', mode, scenarios, strategies: ['original'], seed: 42 }
  setSeed(cfg.seed)
  const composite = computeCompositeScore(v3Scores)
  const rs = []
  for (let i = 0; i < cfg.runs; i++) rs.push(simulateOneRun(composite, v3Scores, cfg, {}, undefined, scenarios[i % scenarios.length]))
  setSeed(undefined)
  return buildSimulationResult(rs, cfg, v3Scores, {}, defaultProfile)
}

const basicResult = await runTier('quick', 250, ['baseline'])
assert(basicResult.advanced?.tier === 'basic', '快速模式产出基础区结果')
assert(basicResult.advanced?.pathBands === undefined, '基础区无路径带')
assert(basicResult.sensitivity.length === 0, '基础区无敏感性分析')
assert(basicResult.strategyComparison.length === 0, '基础区无策略对比')
assert((basicResult.productInsight?.optimizationStrategies.length ?? 0) === 0, '基础区诊断为摘要版')
const ci = basicResult.advanced!.deathProbCI
assert(ci.low <= basicResult.outcomeProbabilities.dead && basicResult.outcomeProbabilities.dead <= ci.high, 'Wilson CI 包含点估计')

const proResult = await runTier('standard', 250, ['baseline'])
assert(proResult.advanced?.tier === 'pro', '标准模式产出专业区结果')
const bands = proResult.advanced?.pathBands ?? []
assert(bands.length > 0, '专业区有路径带')
assert(bands.every((b) => b.p10 <= b.p25 && b.p25 <= b.p50 && b.p50 <= b.p75 && b.p75 <= b.p90), '路径带分位单调 p10≤p25≤p50≤p75≤p90')
const ms = proResult.advanced?.milestones ?? []
const userMs = ms.filter((m) => m.kind === 'users')
assert(userMs.length === 3 && userMs.every((m) => m.reachProbability >= 0 && m.reachProbability <= 1), '里程碑概率合法')
assert(userMs[0].reachProbability >= userMs[1].reachProbability && userMs[1].reachProbability >= userMs[2].reachProbability, '用户里程碑达成率随阈值递减')
assert(proResult.advanced?.survival === undefined, '专业区无生存分析')
assert(proResult.sensitivity.length >= 8, '专业区有敏感性分析')

const flagResult = await runTier('deep', 300, ['baseline', 'optimistic', 'pessimistic'])
assert(flagResult.advanced?.tier === 'flagship', '深度模式产出旗舰区结果')
const surv = flagResult.advanced?.survival
assert(!!surv && surv.curve.length > 0, '旗舰区有生存分析')
assert(!!surv && surv.curve.every((p, i) => i === 0 || surv.curve[i - 1].alive >= p.alive - 1e-9), '存活率曲线单调不增')
assert(!!surv && surv.crashProbByPhase.length === 4, '崩盘阶段共 4 段')
const sb = flagResult.advanced?.scenarioBreakdown ?? []
assert(sb.length === 3, '场景分解覆盖所选 3 场景')
assert(sb.reduce((a, s) => a + s.runs, 0) === 300, '场景分解世界线总数守恒')
const ltv = flagResult.advanced?.ltvPerUser
assert(!!ltv && ltv.p90 >= ltv.p50, 'LTV P90 ≥ P50')
const ext = flagResult.advanced?.extremePaths
assert(!!ext && ext.best.length > 0 && ext.worst.length > 0, '极端世界线路径非空')

// 10b. 机构级 ultra 档
const ultraResult = await runTier('ultra', 200, ['baseline'])
assert(ultraResult.advanced?.tier === 'institutional', '机构模式产出机构级结果')
assert(!!ultraResult.advanced?.survival && !!ultraResult.advanced?.pathBands && !!ultraResult.advanced?.ltvPerUser, '机构级解锁全部分析')
assert(ultraResult.ranking.hasBenchmarkData === true, '机构级含案例库对标')

// 11. seed 可复现性（v3 引擎）
console.log('\n11. seed 可复现性')
const repCfg: SimulationConfig = { runs: 50, periodDays: 90, granularity: 'week', mode: 'quick', scenarios: ['baseline'], strategies: ['original'], seed: 7 }
const repComposite = computeCompositeScore(v3Scores)
const seq = (): number[] => {
  setSeed(7)
  const out: number[] = []
  for (let i = 0; i < repCfg.runs; i++) out.push(simulateOneRun(repComposite, v3Scores, repCfg, {}).finalUsers)
  setSeed(undefined)
  return out
}
const runA = seq()
const runB = seq()
assert(runA.every((v, i) => v === runB[i]), '同 seed 两次模拟逐条一致')

console.log(`\n=== 结果: ${passed} passed, ${failed} failed ===`)
process.exit(failed > 0 ? 1 : 0)
