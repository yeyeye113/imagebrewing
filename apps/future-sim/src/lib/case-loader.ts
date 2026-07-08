// ============================================================
// 从 cases/*.jsonl 加载结构化案例 → 回测用例
// ============================================================

import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { OutcomeClass } from '../types/index.ts'
import type { BacktestCase } from './backtest.ts'
import type { PreLaunchScores } from './score-builder.ts'

const OUTCOME_MAP: Record<string, OutcomeClass> = {
  dead: 'dead',
  abandoned: 'dead',
  monetization_failed: 'dead',
  low_heat_survival: 'low_alive',
  low_alive: 'low_alive',
  low_exposure_survival: 'low_alive',
  niche_success: 'niche_success',
  moderate_success: 'moderate_success',
  clear_success: 'clear_success',
  breakout: 'blockbuster',
  blockbuster: 'blockbuster',
  long_compound: 'long_compound',
}

interface StructuredCaseRow {
  name: string
  case_id?: string
  artifact_type?: string
  category?: string
  final_outcome: string
  path_type?: string[] | string
  confidence?: number
  notes?: string
  stages?: {
    pre_launch?: {
      state?: Record<string, { score?: number }>
    }
  }
}

function normalizeName(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, ' ')
}

function mapOutcome(raw: string, pathType?: string[] | string): OutcomeClass {
  const key = raw.toLowerCase().replace(/\s+/g, '_')
  if (OUTCOME_MAP[key]) return OUTCOME_MAP[key]

  const paths = Array.isArray(pathType) ? pathType : pathType ? [pathType] : []
  if (paths.some((p) => p.includes('long_compound') || p.includes('skill_compound'))) return 'long_compound'
  if (paths.some((p) => p.includes('breakout'))) return 'blockbuster'
  if (paths.some((p) => p.includes('niche'))) return 'niche_success'
  if (paths.some((p) => p.includes('low_exposure'))) return 'dead'

  return 'moderate_success'
}

function extractPreLaunch(state?: Record<string, { score?: number } | null>): PreLaunchScores | null {
  if (!state) return null
  const clarity = state.clarity?.score
  let pain = state.pain_intensity?.score
  let retention = state.retention_design?.score
  const distribution = state.distribution_power?.score
  if (clarity === undefined || distribution === undefined) return null

  // 部分案例库条目 pain/retention 为 null，用相邻维度保守推断
  if (pain === undefined || pain === null) {
    const q = state.quality?.score
    pain = q !== undefined && q !== null ? Math.round(q * 0.95) : 55
  }
  if (retention === undefined || retention === null) {
    const m = state.monetization_fit?.score
    retention = m !== undefined && m !== null ? Math.round(m * 0.85) : 50
  }

  const pre: PreLaunchScores = {
    clarity: clarity!,
    pain: pain!,
    retention: retention!,
    distribution: distribution!,
  }

  if (state.competition_pressure?.score !== undefined) {
    pre.competitionPressure = state.competition_pressure.score
  }
  if (state.differentiation?.score !== undefined) {
    pre.differentiation = state.differentiation.score
  }

  return pre
}

export function parseStructuredCaseRow(row: StructuredCaseRow): BacktestCase | null {
  const preLaunch = extractPreLaunch(row.stages?.pre_launch?.state)
  if (!preLaunch) return null

  const pathLabel = Array.isArray(row.path_type) ? row.path_type.join(', ') : (row.path_type ?? '')

  return {
    name: row.name,
    description: pathLabel,
    preLaunch,
    actualOutcome: mapOutcome(row.final_outcome, row.path_type),
    notes: row.notes,
    category: row.category,
    artifactType: row.artifact_type,
  }
}

export function loadJsonlCases(filePath: string): BacktestCase[] {
  const text = readFileSync(filePath, 'utf8')
  const cases: BacktestCase[] = []

  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    try {
      const row = JSON.parse(trimmed) as StructuredCaseRow
      const c = parseStructuredCaseRow(row)
      if (c) cases.push(c)
    } catch {
      // 跳过非结构化行
    }
  }

  return cases
}

/** 加载 cases/ 下所有结构化 jsonl（part2、part3 等） */
export function loadLibraryCases(): BacktestCase[] {
  const dir = join(dirname(fileURLToPath(import.meta.url)), '../../cases')
  const files = readdirSync(dir).filter((f) => f.endsWith('.jsonl'))
  const all: BacktestCase[] = []

  for (const file of files) {
    all.push(...loadJsonlCases(join(dir, file)))
  }

  return dedupeCasesByName(all)
}

export function dedupeCasesByName(cases: BacktestCase[]): BacktestCase[] {
  const seen = new Set<string>()
  return cases.filter((c) => {
    const key = normalizeName(c.name)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

/** 排除已校准案例，得到 holdout 验证集 */
export function buildHoldoutCases(calibratedNames: string[]): BacktestCase[] {
  const calibrated = new Set(calibratedNames.map(normalizeName))
  return loadLibraryCases().filter((c) => !calibrated.has(normalizeName(c.name)))
}
