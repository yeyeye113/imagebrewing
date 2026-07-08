// ============================================================
// 预测原因报告 — 逐案解释「为什么判成这个结局」
// ============================================================

import type { OutcomeClass } from '../types'
import { type RunResult } from '../workers/simulator.ts'
import {
  buildScoreProfileFromPreLaunch,
  type PreLaunchScores,
} from './score-builder.ts'
import type { BacktestCase, BacktestRunResult } from './backtest.ts'

const OUTCOME_LABEL: Record<OutcomeClass, string> = {
  dead: '死亡',
  low_alive: '低热量存活',
  niche_success: '利基成功',
  moderate_success: '中等成功',
  clear_success: '明显成功',
  blockbuster: '爆款',
  long_compound: '长期复利',
}

function nf(n: number, d = 0): string {
  return n.toLocaleString('zh-CN', { maximumFractionDigits: d })
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

function median(nums: number[]): number {
  if (nums.length === 0) return 0
  const s = [...nums].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

export interface ScoreSignals {
  clarity: number
  pain: number
  retention: number
  distribution: number
  distRetentionGap: number
  isHypeProduct: boolean
  isOpenSourceSurvival: boolean
  isMegaFit: boolean
  isRetentionLed: boolean
  competitionIntensity: number
  platformDependency: number
  legalRisk: number
  externalDeathChance: number
}

export function deriveScoreSignals(pre: PreLaunchScores): ScoreSignals {
  const scores = buildScoreProfileFromPreLaunch(pre)
  const pain = pre.pain / 100
  const rf = pre.retention / 100
  const df = pre.distribution / 100
  const gap = Math.max(0, df - rf - 0.1)
  const megaFit = pain > 0.85 && df > 0.85 && rf > 0.72
  const retentionLed = !megaFit && rf >= 0.72 && rf > df + 0.14 && pain >= 0.65

  const externalDeathChance = Math.min(
    1,
    (scores.market.platformDependency / 100) * 0.3 +
      (scores.risk.legalRisk / 100) * 0.25 +
      (scores.risk.founderDependency / 100) * 0.2 +
      (scores.risk.copycatRisk / 100) * 0.15 +
      (scores.market.competitionIntensity / 100) * 0.1,
  )

  return {
    clarity: pre.clarity,
    pain: pre.pain,
    retention: pre.retention,
    distribution: pre.distribution,
    distRetentionGap: gap,
    isHypeProduct: df > 0.72 && rf < 0.48 && df - rf > 0.38,
    isOpenSourceSurvival: df >= 0.68 && rf >= 42 && rf < 52 && pre.pain >= 48 && pre.pain < 66,
    isMegaFit: megaFit,
    isRetentionLed: retentionLed,
    competitionIntensity: scores.market.competitionIntensity,
    platformDependency: scores.market.platformDependency,
    legalRisk: scores.risk.legalRisk,
    externalDeathChance,
  }
}

/** 根据分数特征推断最可能触发的分类规则（定性，非逐行 debug） */
export function inferDominantReasons(
  signals: ScoreSignals,
  actual: OutcomeClass,
): string[] {
  const reasons: string[] = []
  const { pain, retention, distribution, distRetentionGap } = signals
  const rf = retention / 100
  const df = distribution / 100

  if (pain < 30 && rf < 28) {
    reasons.push('极弱痛点 + 极低留存 → AI 硬件/伪需求类产品，优先按形态判死或低活')
  }
  if (signals.isOpenSourceSurvival) {
    reasons.push('高分发 + 中等留存 + 痛点适中 → 开源/社区有用户但难商业化，归类「低热量存活」')
  }
  if (signals.isHypeProduct) {
    reasons.push(
      `分发(${distribution}) 显著高于留存(${retention})，落差 ${pct(distRetentionGap)} → 模拟启用 hype 衰减：前期曝光大、后期流失加速`,
    )
  }
  if (df >= 0.68 && rf < 0.50 && pain < 0.70 && distRetentionGap >= 0.20 && !signals.isHypeProduct) {
    reasons.push(
      `分发(${distribution}) 高于留存(${retention})，落差 ${pct(distRetentionGap)} → 新奇热度退去后难维持（Marblism 类 AI 尝鲜）`,
    )
  }
  if (df >= 0.75 && rf < 0.58 && pain >= 65) {
    reasons.push('高分发低留存 SaaS → 易被大厂/API 替代，规模难升「明显成功」')
  }
  if (pain >= 45 && pain < 58 && rf >= 65 && df < 0.62) {
    reasons.push('高互动低变现（娱乐/角色 AI）→ 留存尚可但痛点弱，维持低活')
  }
  if (signals.isMegaFit) {
    reasons.push('超强痛点×分发×留存组合 → 具备爆款候选特征')
  }
  if (signals.isRetentionLed) {
    reasons.push('留存显著高于分发 → 长期复利路径（Notion/Obsidian 类）')
  }
  if (pain >= 72 && df >= 36 && df < 48 && rf >= 54 && rf < 70) {
    reasons.push('强痛点 + 分发受限 → 服务化 SaaS 中等成功（Post Bridge 类）')
  }
  if (pain >= 45 && pain < 58 && df < 0.58 && rf >= 0.45 && rf < 0.62) {
    reasons.push('痛点中等 + 浏览器/工具类分发受限 → 核心用户喜爱但难破圈（Arc 类中等成功）')
  }
  if (pain >= 42 && pain < 52 && df >= 42 && df < 55 && rf >= 48 && rf < 58) {
    reasons.push('弱痛点 + 中等分发/留存 → No-Code 试水产品，易落在「低活」与「死亡」边界（Loomin 类）')
  }
  if (competitionHighDeath(signals)) {
    reasons.push(`红海竞争(${signals.competitionIntensity}) + 硬件/大厂赛道特征 → 外部挤压判死`)
  }
  if (signals.legalRisk >= 55) {
    reasons.push(`监管/模式风险(legalRisk=${signals.legalRisk}) → 规模再大也可能崩塌`)
  }
  if (signals.platformDependency >= 68) {
    reasons.push(`平台依赖度高(${signals.platformDependency}) → 政策/上游一变即危`)
  }

  if (reasons.length === 0) {
    reasons.push('综合模拟终态用户数、留存曲线与竞争挤压后，由默认规模阶梯归类')
  }

  // 与实际结局对齐的一句话
  const actualHint: Record<OutcomeClass, string> = {
    dead: '历史结局为关停/破产：模型侧重分发-留存失衡、弱痛点或外部风险',
    low_alive: '历史结局为勉强存活：有用户或社区但商业模式薄弱',
    niche_success: '历史结局为利基赚钱：垂直场景 PMF 成立但规模有限',
    moderate_success: '历史结局为稳健中等规模：痛点成立但增长受分发或定位限制',
    clear_success: '历史结局为明显规模化成功',
    blockbuster: '历史结局为现象级破圈',
    long_compound: '历史结局为慢热复利型增长',
  }
  reasons.push(`【对照史实】${actualHint[actual]}`)

  return reasons
}

function competitionHighDeath(s: ScoreSignals): boolean {
  return s.competitionIntensity >= 72 && s.pain >= 58 && s.pain <= 72
}

export interface SimulationStats {
  medianUsers: number
  p10Users: number
  p90Users: number
  medianRetention: number
  outcomeCounts: Record<OutcomeClass, number>
}

export function summarizeRuns(runs: RunResult[]): SimulationStats {
  const users = runs.map((r) => r.finalUsers).sort((a, b) => a - b)
  const rets = runs.map((r) => r.retentionRate)
  const outcomeCounts: Record<OutcomeClass, number> = {
    dead: 0,
    low_alive: 0,
    niche_success: 0,
    moderate_success: 0,
    clear_success: 0,
    blockbuster: 0,
    long_compound: 0,
  }
  for (const r of runs) outcomeCounts[r.outcomeClass]++

  return {
    medianUsers: median(users),
    p10Users: users[Math.floor(users.length * 0.1)] ?? 0,
    p90Users: users[Math.floor(users.length * 0.9)] ?? 0,
    medianRetention: median(rets),
    outcomeCounts,
  }
}

export interface CaseReasonReport {
  name: string
  category?: string
  artifactType?: string
  actualOutcome: OutcomeClass
  predictedOutcome: OutcomeClass
  probabilityOfActual: number
  exactMatch: boolean
  confidenceTier: 'high' | 'medium' | 'low'
  scores: PreLaunchScores
  signals: ScoreSignals
  dominantReasons: string[]
  simulationStats: SimulationStats
  distributionText: string
  competingOutcomes: string
  uncertaintyNote?: string
  historicalNotes?: string
}

function confidenceTier(p: number): 'high' | 'medium' | 'low' {
  if (p >= 0.85) return 'high'
  if (p >= 0.75) return 'medium'
  return 'low'
}

function formatDistribution(stats: SimulationStats, total: number): string {
  const order: OutcomeClass[] = [
    'dead',
    'low_alive',
    'niche_success',
    'moderate_success',
    'clear_success',
    'blockbuster',
    'long_compound',
  ]
  return order
    .map((k) => `${OUTCOME_LABEL[k]} ${pct(stats.outcomeCounts[k] / total)}`)
    .join(' · ')
}

export function buildCaseReasonReport(
  testCase: BacktestCase,
  result: BacktestRunResult,
): CaseReasonReport {
  const signals = deriveScoreSignals(testCase.preLaunch)
  const stats = summarizeRuns(result.runs)
  const total = result.runs.length

  const distEntries = Object.entries(stats.outcomeCounts)
    .map(([k, v]) => [k as OutcomeClass, v / total] as const)
    .sort((a, b) => b[1] - a[1])

  const top2 = distEntries.slice(0, 2)
  const competing = top2
    .filter(([k]) => k !== result.actualOutcome)
    .map(([k, v]) => `${OUTCOME_LABEL[k]}(${pct(v)})`)
    .join('、')

  let uncertaintyNote: string | undefined
  if (result.probabilityOfActual < 0.85) {
    uncertaintyNote =
      `真实结局 P=${pct(result.probabilityOfActual)}，与次优结局 ${OUTCOME_LABEL[result.mostLikelyOutcome]} 接近。` +
      `模拟终态用户中位数 ${nf(stats.medianUsers)}（P10–P90: ${nf(stats.p10Users)}–${nf(stats.p90Users)}），` +
      `终局留存中位 ${pct(stats.medianRetention)}。` +
      (competing ? `主要竞争结局：${competing}。` : '') +
      (signals.isHypeProduct
        ? ' 高分发低留存使部分世界线仍冲到规模阶梯上的「明显成功」，拉低置信度。'
        : signals.distRetentionGap > 0.2
          ? ' 分发-留存落差使死亡/存活世界线并存。'
          : ' 分数处于多条分类规则边界，蒙特卡洛噪声导致分布分散。')
  }

  return {
    name: testCase.name,
    category: testCase.category,
    artifactType: testCase.artifactType,
    actualOutcome: testCase.actualOutcome,
    predictedOutcome: result.mostLikelyOutcome,
    probabilityOfActual: result.probabilityOfActual,
    exactMatch: result.exactMatch,
    confidenceTier: confidenceTier(result.probabilityOfActual),
    scores: testCase.preLaunch,
    signals,
    dominantReasons: inferDominantReasons(signals, testCase.actualOutcome),
    simulationStats: stats,
    distributionText: formatDistribution(stats, total),
    competingOutcomes: top2.map(([k, v]) => `${OUTCOME_LABEL[k]} ${pct(v)}`).join(' > '),
    uncertaintyNote,
    historicalNotes: testCase.notes,
  }
}

export function formatCaseReasonMarkdown(r: CaseReasonReport): string {
  const tierLabel = { high: '高', medium: '中', low: '低' }[r.confidenceTier]
  const lines = [
    `## ${r.name}`,
    '',
    `| 项 | 值 |`,
    `|---|---|`,
    `| 品类 | ${r.category ?? '—'} |`,
    `| 形态 | ${r.artifactType ?? '—'} |`,
    `| 预测 | **${OUTCOME_LABEL[r.predictedOutcome]}** |`,
    `| 史实 | ${OUTCOME_LABEL[r.actualOutcome]} |`,
    `| P(史实) | ${pct(r.probabilityOfActual)}（置信${tierLabel}） |`,
    `| Exact | ${r.exactMatch ? '✅' : '❌'} |`,
    '',
    '### 输入分数（pre_launch）',
    '',
    `- 清晰度 ${r.scores.clarity} · 痛点 ${r.scores.pain} · 留存 ${r.scores.retention} · 分发 ${r.scores.distribution}`,
    `- 推断竞争强度 ${r.signals.competitionIntensity} · 平台依赖 ${r.signals.platformDependency} · 法律风险 ${r.signals.legalRisk}`,
    `- 分发-留存落差 ${pct(r.signals.distRetentionGap)}${r.signals.isHypeProduct ? ' · **hype 产品**' : ''}${r.signals.isOpenSourceSurvival ? ' · **开源难变现**' : ''}`,
    '',
    '### 模拟终态（1000 runs × 180天）',
    '',
    `- 用户中位 ${nf(r.simulationStats.medianUsers)}（P10–P90: ${nf(r.simulationStats.p10Users)}–${nf(r.simulationStats.p90Users)}）`,
    `- 终局留存中位 ${pct(r.simulationStats.medianRetention)}`,
    `- 分布：${r.distributionText}`,
    '',
    '### 判定原因（引擎逻辑）',
    '',
    ...r.dominantReasons.map((x) => `- ${x}`),
  ]

  if (r.historicalNotes) {
    lines.push('', '### 史实备注', '', r.historicalNotes)
  }
  if (r.uncertaintyNote) {
    lines.push('', '### 不确定性说明', '', r.uncertaintyNote)
  }

  return lines.join('\n')
}

export function formatFullReasonReport(reports: CaseReasonReport[]): string {
  const exact = reports.filter((r) => r.exactMatch).length
  const avgP = reports.reduce((s, r) => s + r.probabilityOfActual, 0) / reports.length
  const low = reports.filter((r) => r.confidenceTier === 'low')

  const header = [
    '# Future-Sim 预测原因报告',
    '',
    `生成时间：${new Date().toISOString().slice(0, 10)}`,
    '',
    '## 总览',
    '',
    `| 指标 | 数值 |`,
    `|------|------|`,
    `| 案例数 | ${reports.length} |`,
    `| Exact 命中率 | ${pct(exact / reports.length)} (${exact}/${reports.length}) |`,
    `| 平均 P(史实) | ${pct(avgP)} |`,
    `| 低置信案例 (<75%) | ${low.length} |`,
    '',
  ]

  if (low.length > 0) {
    header.push('## 低置信案例速览', '')
    for (const r of low) {
      header.push(
        `- **${r.name}**：预测 ${OUTCOME_LABEL[r.predictedOutcome]}，史实 ${OUTCOME_LABEL[r.actualOutcome]}，P=${pct(r.probabilityOfActual)}`,
      )
    }
    header.push('')
  }

  header.push('---', '', '# 逐案详情', '')

  const body = reports
    .sort((a, b) => a.probabilityOfActual - b.probabilityOfActual)
    .map(formatCaseReasonMarkdown)
    .join('\n\n---\n\n')

  return header.join('\n') + body
}
