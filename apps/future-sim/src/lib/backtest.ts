// ============================================================
// Backtest Framework — Future Simulation Engine
// ============================================================
//
// Validates simulator predictions against known real-world outcomes.
// Takes pre_launch score profiles, runs the simulator, and compares
// predicted outcome distributions to actual historical results.
//

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type {
  SimulationConfig,
  OutcomeClass,
  OutcomeProbabilities,
} from '../types'
import { buildScoreProfileFromPreLaunch, type PreLaunchScores } from './score-builder.ts'

/** A single backtest case with known ground truth */
export interface BacktestCase {
  name: string
  description: string
  preLaunch: PreLaunchScores
  actualOutcome: OutcomeClass
  /** Optional real-world notes for qualitative evaluation */
  notes?: string
  /** 案例库品类（用于分品类准确度统计） */
  category?: string
  /** 作品形态（web_tool / ai_tool / small_saas 等） */
  artifactType?: string
}

/** Result of running the simulator on one case */
export interface BacktestRunResult {
  caseName: string
  predicted: OutcomeProbabilities
  mostLikelyOutcome: OutcomeClass
  actualOutcome: OutcomeClass
  /** Whether the actual outcome matches the most-likely predicted outcome */
  exactMatch: boolean
  /** Whether the actual outcome is within the top-2 predicted outcomes */
  topTwoMatch: boolean
  /** Whether the actual outcome's probability is above a threshold */
  probabilityOfActual: number
  /** Individual run results for deeper analysis */
  runs: RunResult[]
}

/** Aggregate accuracy metrics across all backtest cases */
export interface AccuracyMetrics {
  /** Percentage of cases where most-likely prediction matches actual */
  exactHitRate: number
  /** Percentage of cases where actual is in top-2 predicted outcomes */
  topTwoHitRate: number
  /** Average probability assigned to the actual outcome across all cases */
  averagePrecision: number
  /** Per-outcome-class accuracy breakdown */
  perClassAccuracy: Record<OutcomeClass, { total: number; hits: number; rate: number }>
  /** Confusion matrix: predicted vs actual */
  confusionMatrix: Record<OutcomeClass, Record<OutcomeClass, number>>
  /** Overall results */
  totalCases: number
  exactHits: number
  topTwoHits: number
}

import {
  computeCompositeScore,
  simulateOneRun,
  setSeed,
} from '../workers/simulator.ts'
import type { RunResult } from '../workers/simulator.ts'

export type { PreLaunchScores } from './score-builder.ts'
export { buildScoreProfileFromPreLaunch as buildScoreProfileForBenchmark } from './score-builder.ts'

// ---- Types ----

/** Default simulation config for backtesting (1000 runs, 180 days, weekly granularity) */
function defaultBacktestConfig(): SimulationConfig {
  return {
    runs: 1000,
    periodDays: 180,
    granularity: 'week',
    mode: 'standard',
    scenarios: ['baseline'],
    strategies: ['original'],
    seed: 42,
  }
}

/** Find the outcome class with the highest probability */
function mostLikelyOutcome(probs: OutcomeProbabilities): OutcomeClass {
  const entries: [OutcomeClass, number][] = [
    ['dead', probs.dead],
    ['low_alive', probs.lowAlive],
    ['niche_success', probs.nicheSuccess],
    ['moderate_success', probs.moderateSuccess],
    ['clear_success', probs.clearSuccess],
    ['blockbuster', probs.blockbuster],
    ['long_compound', probs.longCompound],
  ]
  entries.sort((a, b) => b[1] - a[1])
  return entries[0][0]
}

/** Map OutcomeClass to the key used in OutcomeProbabilities */
function outcomeToKey(cls: OutcomeClass): keyof OutcomeProbabilities {
  const map: Record<OutcomeClass, keyof OutcomeProbabilities> = {
    dead: 'dead',
    low_alive: 'lowAlive',
    niche_success: 'nicheSuccess',
    moderate_success: 'moderateSuccess',
    clear_success: 'clearSuccess',
    blockbuster: 'blockbuster',
    long_compound: 'longCompound',
  }
  return map[cls]
}

// ---- Core API ----

/**
 * Run a single backtest case through the simulator.
 * Executes `config.runs` Monte Carlo simulations and aggregates outcome probabilities.
 */
export function runBacktest(
  testCase: BacktestCase,
  config?: SimulationConfig,
): BacktestRunResult {
  const cfg = config ?? defaultBacktestConfig()
  const scores = buildScoreProfileFromPreLaunch(testCase.preLaunch)
  const composite = computeCompositeScore(scores)

  setSeed(cfg.seed)
  // Run Monte Carlo simulations
  const runs: RunResult[] = []
  for (let i = 0; i < cfg.runs; i++) {
    runs.push(simulateOneRun(composite, scores, cfg, {}))
  }
  setSeed(undefined)

  // Aggregate outcome probabilities
  const counts: Record<OutcomeClass, number> = {
    dead: 0,
    low_alive: 0,
    niche_success: 0,
    moderate_success: 0,
    clear_success: 0,
    blockbuster: 0,
    long_compound: 0,
  }
  for (const r of runs) {
    counts[r.outcomeClass]++
  }

  const n = runs.length
  const predicted: OutcomeProbabilities = {
    dead: counts.dead / n,
    lowAlive: counts.low_alive / n,
    nicheSuccess: counts.niche_success / n,
    moderateSuccess: counts.moderate_success / n,
    clearSuccess: counts.clear_success / n,
    blockbuster: counts.blockbuster / n,
    longCompound: counts.long_compound / n,
  }

  const mlOutcome = mostLikelyOutcome(predicted)
  const actualKey = outcomeToKey(testCase.actualOutcome)
  const probOfActual = predicted[actualKey]

  // Top-2 check
  const entries: [OutcomeClass, number][] = [
    ['dead', predicted.dead],
    ['low_alive', predicted.lowAlive],
    ['niche_success', predicted.nicheSuccess],
    ['moderate_success', predicted.moderateSuccess],
    ['clear_success', predicted.clearSuccess],
    ['blockbuster', predicted.blockbuster],
    ['long_compound', predicted.longCompound],
  ]
  entries.sort((a, b) => b[1] - a[1])
  const topTwoClasses = new Set([entries[0][0], entries[1][0]])

  return {
    caseName: testCase.name,
    predicted,
    mostLikelyOutcome: mlOutcome,
    actualOutcome: testCase.actualOutcome,
    exactMatch: mlOutcome === testCase.actualOutcome,
    topTwoMatch: topTwoClasses.has(testCase.actualOutcome),
    probabilityOfActual: probOfActual,
    runs,
  }
}

/**
 * Calculate aggregate accuracy metrics across multiple backtest results.
 */
export function calculateAccuracy(results: BacktestRunResult[]): AccuracyMetrics {
  const outcomeClasses: OutcomeClass[] = [
    'dead', 'low_alive', 'niche_success', 'moderate_success',
    'clear_success', 'blockbuster', 'long_compound',
  ]

  let exactHits = 0
  let topTwoHits = 0
  let totalProbOfActual = 0

  // Per-class tracking
  const perClass: Record<OutcomeClass, { total: number; hits: number; rate: number }> = {} as any
  for (const cls of outcomeClasses) {
    perClass[cls] = { total: 0, hits: 0, rate: 0 }
  }

  // Confusion matrix
  const confusion: Record<OutcomeClass, Record<OutcomeClass, number>> = {} as any
  for (const actual of outcomeClasses) {
    confusion[actual] = {} as any
    for (const predicted of outcomeClasses) {
      confusion[actual][predicted] = 0
    }
  }

  for (const r of results) {
    if (r.exactMatch) exactHits++
    if (r.topTwoMatch) topTwoHits++
    totalProbOfActual += r.probabilityOfActual

    // Per-class
    perClass[r.actualOutcome].total++
    if (r.exactMatch) perClass[r.actualOutcome].hits++

    // Confusion matrix
    confusion[r.actualOutcome][r.mostLikelyOutcome]++
  }

  // Compute rates
  for (const cls of outcomeClasses) {
    const c = perClass[cls]
    c.rate = c.total > 0 ? c.hits / c.total : 0
  }

  const n = results.length || 1

  return {
    exactHitRate: exactHits / n,
    topTwoHitRate: topTwoHits / n,
    averagePrecision: totalProbOfActual / n,
    perClassAccuracy: perClass,
    confusionMatrix: confusion,
    totalCases: results.length,
    exactHits,
    topTwoHits,
  }
}

/** 收集案例库各案例的中位用户数（benchmark 校准用） */
export function collectCaseUserMedians(
  cases: BacktestCase[],
  config: SimulationConfig,
): { name: string; outcome: OutcomeClass; medianUsers: number }[] {
  const medians: { name: string; outcome: OutcomeClass; medianUsers: number }[] = []

  for (const testCase of cases) {
    const scores = buildScoreProfileFromPreLaunch(testCase.preLaunch)
    const composite = computeCompositeScore(scores)
    const users: number[] = []

    setSeed(config.seed)
    for (let i = 0; i < config.runs; i++) {
      users.push(simulateOneRun(composite, scores, config, {}).finalUsers)
    }
    setSeed(undefined)

    users.sort((a, b) => a - b)
    const mid = users[Math.floor(users.length / 2)]
    medians.push({ name: testCase.name, outcome: testCase.actualOutcome, medianUsers: mid })
  }

  return medians
}

// ---- Hardcoded Test Cases (Real Products) ----

export const BACKTEST_CASES: BacktestCase[] = [
  {
    name: 'Lovable',
    description: 'AI-powered full-stack app builder — breakout success in 2024-2025',
    preLaunch: { clarity: 80, pain: 85, retention: 70, distribution: 65 },
    actualOutcome: 'clear_success',
    notes: 'Strong pain point (non-technical users wanting to build apps), high clarity of value prop, decent retention via project lock-in.',
  },
  {
    name: 'Photopea',
    description: 'Browser-based Photoshop alternative — long-term compound growth',
    preLaunch: { clarity: 80, pain: 80, retention: 80, distribution: 85 },
    actualOutcome: 'long_compound',
    notes: 'Solved real pain (free Photoshop in browser), extremely high retention (daily tool), organic distribution via SEO and word-of-mouth.',
  },
  {
    name: 'Marblism',
    description: 'AI-generated 3D characters — initial hype then decline',
    preLaunch: { clarity: 70, pain: 60, retention: 40, distribution: 75 },
    actualOutcome: 'dead',
    notes: 'High initial virality (distribution 75) but low retention (40) — novelty wore off, no sustained use case.',
  },
  {
    name: 'Google Stadia',
    description: 'Cloud gaming platform — launched 2019, shut down 2023',
    preLaunch: { clarity: 80, pain: 50, retention: 30, distribution: 90 },
    actualOutcome: 'dead',
    notes: 'High distribution (Google brand + marketing), decent clarity, but low pain (existing solutions worked) and very low retention.',
  },
  {
    name: 'Post Bridge',
    description: 'Social media scheduling tool — moderate steady success',
    preLaunch: { clarity: 70, pain: 75, retention: 60, distribution: 40 },
    actualOutcome: 'moderate_success',
    notes: 'Solid pain point for social media managers, good retention via workflow integration, limited virality but sustainable niche.',
  },
  {
    name: 'Cursor',
    description: 'AI-native code editor — breakout success 2024-2025',
    preLaunch: { clarity: 85, pain: 85, retention: 80, distribution: 70 },
    actualOutcome: 'clear_success',
    notes: '强痛点(AI 编程)、高清晰度、强留存(开发者日用)、口碑传播强。',
  },
  {
    name: 'Notion',
    description: 'All-in-one workspace — long-term compound growth',
    preLaunch: { clarity: 72, pain: 78, retention: 85, distribution: 68 },
    actualOutcome: 'long_compound',
    notes: '前期平淡后期复利，极强留存与模板社区生态，organic 增长为主。',
  },
  {
    name: 'Clubhouse',
    description: 'Audio social app — viral hype then sharp decline',
    preLaunch: { clarity: 70, pain: 45, retention: 35, distribution: 88 },
    actualOutcome: 'dead',
    notes: '极高初始传播(邀请制+名人)，但痛点弱、留存差，热度退去后崩塌。',
  },
  {
    name: 'Arc Browser',
    description: 'Reimagined browser — niche enthusiast traction',
    preLaunch: { clarity: 70, pain: 50, retention: 58, distribution: 55 },
    actualOutcome: 'moderate_success',
    notes: '设计驱动、核心用户喜爱，但切换成本与小众定位限制破圈。',
  },
  {
    name: 'ChatGPT',
    description: 'Conversational AI — fastest-growing consumer app in history',
    preLaunch: { clarity: 90, pain: 90, retention: 85, distribution: 90 },
    actualOutcome: 'blockbuster',
    notes: '极强痛点+清晰度+留存+病毒传播，史上最快破圈。',
  },
  {
    name: 'Figma',
    description: 'Collaborative design tool — clear scaling success',
    preLaunch: { clarity: 85, pain: 80, retention: 82, distribution: 72 },
    actualOutcome: 'clear_success',
    notes: '协作痛点强、浏览器即用、团队留存高，稳步规模化。',
  },
  {
    name: 'Quibi',
    description: 'Short-form video platform — high-budget failure',
    preLaunch: { clarity: 65, pain: 40, retention: 30, distribution: 90 },
    actualOutcome: 'dead',
    notes: '巨额营销(高分发)但痛点弱、留存差，半年关停。',
  },
  {
    name: 'Obsidian',
    description: 'Local-first knowledge base — slow-burn compound',
    preLaunch: { clarity: 72, pain: 68, retention: 88, distribution: 50 },
    actualOutcome: 'long_compound',
    notes: '极强留存与社区插件生态，分发弱但长期复利。',
  },
]

// ---- Runner ----

/**
 * Run all hardcoded backtest cases and return results + accuracy metrics.
 */
export function runFullBacktest(config?: SimulationConfig): {
  results: BacktestRunResult[]
  accuracy: AccuracyMetrics
  summary: string
} {
  const results = BACKTEST_CASES.map((c) => runBacktest(c, config))
  const accuracy = calculateAccuracy(results)

  // Build human-readable summary
  const lines: string[] = [
    '=== Backtest Results ===',
    '',
  ]

  for (const r of results) {
    const match = r.exactMatch ? 'EXACT' : r.topTwoMatch ? 'TOP-2' : 'MISS'
    lines.push(
      `[${match}] ${r.caseName}`,
      `  Predicted: ${r.mostLikelyOutcome} (${(r.predicted[outcomeToKey(r.mostLikelyOutcome)] * 100).toFixed(1)}%)`,
      `  Actual:    ${r.actualOutcome} (prob=${(r.probabilityOfActual * 100).toFixed(1)}%)`,
      '',
    )
  }

  lines.push(
    '=== Accuracy ===',
    `  Exact hit rate:    ${(accuracy.exactHitRate * 100).toFixed(1)}% (${accuracy.exactHits}/${accuracy.totalCases})`,
    `  Top-2 hit rate:    ${(accuracy.topTwoHitRate * 100).toFixed(1)}% (${accuracy.topTwoHits}/${accuracy.totalCases})`,
    `  Average precision: ${(accuracy.averagePrecision * 100).toFixed(1)}%`,
    '',
    '=== Per-Class ===',
  )

  for (const [cls, data] of Object.entries(accuracy.perClassAccuracy)) {
    if (data.total > 0) {
      lines.push(`  ${cls}: ${data.hits}/${data.total} (${(data.rate * 100).toFixed(1)}%)`)
    }
  }

  lines.push(
    '',
    '=== Confusion Matrix (rows=actual, cols=predicted) ===',
  )

  const outcomeClasses: OutcomeClass[] = [
    'dead', 'low_alive', 'niche_success', 'moderate_success',
    'clear_success', 'blockbuster', 'long_compound',
  ]
  const header = ['actual\\pred', ...outcomeClasses].map((h) => h.padEnd(16)).join('')
  lines.push(header)
  for (const actual of outcomeClasses) {
    const row = outcomeClasses
      .map((pred) => String(accuracy.confusionMatrix[actual][pred]).padEnd(16))
      .join('')
    lines.push(`${actual.padEnd(16)}${row}`)
  }

  return {
    results,
    accuracy,
    summary: lines.join('\n'),
  }
}

// ---- Expansion cases (from cases/backtest/backtest_expansion.json) ----

const OUTCOME_ALIASES: Record<string, OutcomeClass> = {
  dead: 'dead',
  low_alive: 'low_alive',
  low_heat_survival: 'low_alive',
  niche_success: 'niche_success',
  moderate_success: 'moderate_success',
  clear_success: 'clear_success',
  blockbuster: 'blockbuster',
  long_compound: 'long_compound',
}

/** 额外成功案例（结构化案例库提炼，不与 expansion.json 重复） */
export const EXTRA_SUCCESS_CASES: BacktestCase[] = [
  {
    name: 'Draftss',
    description: 'Productized design service — 7-figure ARR',
    preLaunch: { clarity: 75, pain: 80, retention: 70, distribution: 55 },
    actualOutcome: 'clear_success',
    notes: '服务产品化路径，强痛点 + 订阅模式。',
  },
  {
    name: 'vidIQ',
    description: 'YouTube growth tool — niche compound',
    preLaunch: { clarity: 75, pain: 80, retention: 72, distribution: 60 },
    actualOutcome: 'niche_success',
    notes: 'Chrome 商店 + 创作者社区，PH 渠道无效。',
  },
]

export function loadExpansionCases(): BacktestCase[] {
  const dir = dirname(fileURLToPath(import.meta.url))
  const raw = JSON.parse(
    readFileSync(join(dir, '../../cases/backtest/backtest_expansion.json'), 'utf8'),
  ) as Array<{
    name: string
    pre_launch: PreLaunchScores
    actual_outcome: string
    notes?: string
    path_type?: string
  }>

  const coreNames = new Set(BACKTEST_CASES.map((c) => c.name))

  return raw
    .filter((c) => !coreNames.has(c.name))
    .map((c) => ({
      name: c.name,
      description: c.path_type ?? '',
      preLaunch: c.pre_launch,
      actualOutcome: OUTCOME_ALIASES[c.actual_outcome] ?? 'dead',
      notes: c.notes,
    }))
}

/** 核心 13 案例 + 扩展库（去重） */
function dedupeCasesByName(cases: BacktestCase[]): BacktestCase[] {
  const seen = new Set<string>()
  return cases.filter((c) => {
    if (seen.has(c.name)) return false
    seen.add(c.name)
    return true
  })
}

export function getAllBacktestCases(): BacktestCase[] {
  return dedupeCasesByName([...BACKTEST_CASES, ...loadExpansionCases(), ...EXTRA_SUCCESS_CASES])
}

export function runExtendedBacktest(config?: SimulationConfig): {
  results: BacktestRunResult[]
  accuracy: AccuracyMetrics
  summary: string
  coreAccuracy: AccuracyMetrics
  expansionAccuracy: AccuracyMetrics
} {
  const coreResults = BACKTEST_CASES.map((c) => runBacktest(c, config))
  const expansionOnly = dedupeCasesByName([...loadExpansionCases(), ...EXTRA_SUCCESS_CASES])
  const expansionResults = expansionOnly.map((c) => runBacktest(c, config))
  const allResults = [...coreResults, ...expansionResults]

  const coreAccuracy = calculateAccuracy(coreResults)
  const expansionAccuracy = calculateAccuracy(expansionResults)
  const accuracy = calculateAccuracy(allResults)

  const lines: string[] = [
    '=== Extended Backtest Results ===',
    '',
    `Core cases (${BACKTEST_CASES.length}): exact ${(coreAccuracy.exactHitRate * 100).toFixed(1)}%`,
    `Expansion cases (${expansionOnly.length}): exact ${(expansionAccuracy.exactHitRate * 100).toFixed(1)}%`,
    `Combined (${allResults.length}): exact ${(accuracy.exactHitRate * 100).toFixed(1)}%`,
    '',
    '=== Expansion Case Details ===',
    '',
  ]

  for (const r of expansionResults) {
    const tag = r.exactMatch ? 'HIT' : r.topTwoMatch ? 'TOP-2' : 'MISS'
    lines.push(
      `[${tag}] ${r.caseName}`,
      `  Predicted: ${r.mostLikelyOutcome} (${(r.predicted[outcomeToKey(r.mostLikelyOutcome)] * 100).toFixed(1)}%)`,
      `  Actual:    ${r.actualOutcome} (prob=${(r.probabilityOfActual * 100).toFixed(1)}%)`,
      '',
    )
  }

  lines.push(
    '=== Core Cases ===',
    '',
    runFullBacktest(config).summary,
  )

  return {
    results: allResults,
    accuracy,
    summary: lines.join('\n'),
    coreAccuracy,
    expansionAccuracy,
  }
}
