// ============================================================
// 分品类 / 分形态 预测准确度统计
// ============================================================

import {
  BACKTEST_CASES,
  EXTRA_SUCCESS_CASES,
  loadExpansionCases,
  runBacktest,
  calculateAccuracy,
  type BacktestCase,
  type BacktestRunResult,
  type AccuracyMetrics,
} from './backtest.ts'
import { getHoldoutCases } from './holdout-backtest.ts'
import { loadLibraryCases } from './case-loader.ts'
import type { SimulationConfig } from '../types/index.ts'

/** 校准集核心案例的品类元数据（无 jsonl 来源时手工标注） */
const CORE_META: Record<string, { category: string; artifactType: string }> = {
  Lovable: { category: 'AI App Builder', artifactType: 'ai_tool' },
  Photopea: { category: 'Design Tool', artifactType: 'web_tool' },
  Marblism: { category: 'AI 3D Characters', artifactType: 'ai_tool' },
  'Google Stadia': { category: 'Cloud Gaming', artifactType: 'web_tool' },
  'Post Bridge': { category: 'Content Repurposing', artifactType: 'small_saas' },
  Cursor: { category: 'AI Code Editor', artifactType: 'ai_tool' },
  Notion: { category: 'Productivity Workspace', artifactType: 'web_tool' },
  Clubhouse: { category: 'Audio Social', artifactType: 'app' },
  'Arc Browser': { category: 'Innovative Browser', artifactType: 'web_tool' },
  ChatGPT: { category: 'Conversational AI', artifactType: 'ai_tool' },
  Figma: { category: 'Collaborative Design', artifactType: 'web_tool' },
  Quibi: { category: 'Short-form Streaming', artifactType: 'web_tool' },
  Obsidian: { category: 'Knowledge Management', artifactType: 'app' },
}

export interface GroupAccuracyRow {
  groupKey: string
  total: number
  exactHits: number
  exactRate: number
  topTwoHits: number
  topTwoRate: number
  avgProbActual: number
  misses: string[]
}

export interface CategoryAccuracyReport {
  byArtifactType: GroupAccuracyRow[]
  byCategory: GroupAccuracyRow[]
  byOutcomeActual: GroupAccuracyRow[]
  overall: AccuracyMetrics
  datasetLabel: string
}

function attachMeta(testCase: BacktestCase): BacktestCase {
  if (testCase.category && testCase.artifactType) return testCase
  const lib = loadLibraryCases().find((c) => c.name === testCase.name)
  const core = CORE_META[testCase.name]
  return {
    ...testCase,
    category: testCase.category ?? lib?.category ?? core?.category ?? '未分类',
    artifactType: testCase.artifactType ?? lib?.artifactType ?? core?.artifactType ?? 'unknown',
  }
}

function groupResults(
  cases: BacktestCase[],
  results: BacktestRunResult[],
  pickKey: (c: BacktestCase) => string,
): GroupAccuracyRow[] {
  const map = new Map<string, { cases: BacktestCase[]; results: BacktestRunResult[] }>()

  for (let i = 0; i < cases.length; i++) {
    const key = pickKey(cases[i])
    const bucket = map.get(key) ?? { cases: [], results: [] }
    bucket.cases.push(cases[i])
    bucket.results.push(results[i])
    map.set(key, bucket)
  }

  const rows: GroupAccuracyRow[] = []
  for (const [groupKey, bucket] of map) {
    const acc = calculateAccuracy(bucket.results)
    const misses = bucket.results
      .filter((r) => !r.exactMatch)
      .map((r) => `${r.caseName}(${r.mostLikelyOutcome}→${r.actualOutcome})`)

    rows.push({
      groupKey,
      total: bucket.results.length,
      exactHits: acc.exactHits,
      exactRate: acc.exactHitRate,
      topTwoHits: acc.topTwoHits,
      topTwoRate: acc.topTwoHitRate,
      avgProbActual: acc.averagePrecision,
      misses,
    })
  }

  rows.sort((a, b) => b.total - a.total || a.groupKey.localeCompare(b.groupKey))
  return rows
}

function runCases(cases: BacktestCase[], config?: SimulationConfig) {
  const enriched = cases.map(attachMeta)
  const results = enriched.map((c) => runBacktest(c, config))
  return { cases: enriched, results, accuracy: calculateAccuracy(results) }
}

export function buildCalibratedCases(): BacktestCase[] {
  return [
    ...BACKTEST_CASES,
    ...loadExpansionCases(),
    ...EXTRA_SUCCESS_CASES,
  ].map(attachMeta)
}

export function buildExpandedHoldoutCases(): BacktestCase[] {
  return getHoldoutCases().map(attachMeta)
}

export function runCategoryAccuracyReport(
  dataset: 'calibrated' | 'holdout' | 'all',
  config?: SimulationConfig,
): CategoryAccuracyReport {
  const calibrated = buildCalibratedCases()
  const holdout = buildExpandedHoldoutCases()

  let cases: BacktestCase[]
  let label: string
  if (dataset === 'calibrated') {
    cases = calibrated
    label = `校准集 (${cases.length} 例)`
  } else if (dataset === 'holdout') {
    cases = holdout
    label = `Holdout 验证集 (${cases.length} 例)`
  } else {
    cases = [...calibrated, ...holdout]
    label = `全量 (${cases.length} 例 = 校准 ${calibrated.length} + Holdout ${holdout.length})`
  }

  const { results, accuracy } = runCases(cases, config)

  return {
    datasetLabel: label,
    overall: accuracy,
    byArtifactType: groupResults(cases, results, (c) => c.artifactType ?? 'unknown'),
    byCategory: groupResults(cases, results, (c) => c.category ?? '未分类'),
    byOutcomeActual: groupResults(cases, results, (c) => c.actualOutcome),
  }
}

export function formatCategoryReport(report: CategoryAccuracyReport): string {
  const fmt = (rows: GroupAccuracyRow[], title: string) => {
    const lines = [
      `### ${title}`,
      '',
      '| 分组 | 样本 | Exact | Top-2 | 均 P(actual) | 漏判 |',
      '|------|------|-------|-------|--------------|------|',
    ]
    for (const r of rows) {
      const miss = r.misses.length ? r.misses.join('; ') : '—'
      lines.push(
        `| ${r.groupKey} | ${r.total} | ${(r.exactRate * 100).toFixed(0)}% (${r.exactHits}/${r.total}) | ${(r.topTwoRate * 100).toFixed(0)}% | ${(r.avgProbActual * 100).toFixed(1)}% | ${miss} |`,
      )
    }
    return lines.join('\n')
  }

  const o = report.overall
  return [
    `## ${report.datasetLabel}`,
    '',
    `**整体 Exact**: ${(o.exactHitRate * 100).toFixed(1)}% (${o.exactHits}/${o.totalCases})`,
    `**Top-2**: ${(o.topTwoHitRate * 100).toFixed(1)}% · **均 P(actual)**: ${(o.averagePrecision * 100).toFixed(1)}%`,
    '',
    fmt(report.byArtifactType, '按作品形态 (artifact_type)'),
    '',
    fmt(report.byCategory, '按品类 (category)'),
    '',
    fmt(report.byOutcomeActual, '按真实结局 (actual outcome)'),
  ].join('\n')
}
