// ============================================================
// File utilities — import/export functionality
// ============================================================

import type { ArtifactProfile, ScoreProfile, SimulationConfig, SimulationResult, ProjectRecord } from '@/types'

// 导出完整项目为 JSON 文件
export function exportProjectToJson(record: ProjectRecord): void {
  const data = JSON.stringify(record, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${record.profile.name}_项目备份_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// 从 JSON 文件导入项目
export async function importProjectFromJson(file: File): Promise<ProjectRecord | null> {
  try {
    const text = await file.text()
    const data = JSON.parse(text) as ProjectRecord

    // 验证必要字段
    if (!data.id || !data.profile || !data.profile.name) {
      throw new Error('Invalid project file format')
    }

    // 生成新 ID 以避免冲突
    const newId = crypto.randomUUID()
    return {
      ...data,
      id: newId,
      profile: {
        ...data.profile,
        id: newId,
        name: data.profile.name + ' (导入)',
      },
      updatedAt: new Date().toISOString(),
    }
  } catch (err) {
    console.error('[File] Failed to import project:', err)
    return null
  }
}

// 导出模拟结果为 CSV
export function exportResultToCsv(result: SimulationResult, projectName: string): void {
  const rows: string[] = []

  // 标题行
  rows.push('指标,数值')

  // 结果概率分布
  const op = result.outcomeProbabilities
  rows.push(`死亡概率,${(op.dead * 100).toFixed(1)}%`)
  rows.push(`低热度概率,${(op.lowAlive * 100).toFixed(1)}%`)
  rows.push(`小众成功概率,${(op.nicheSuccess * 100).toFixed(1)}%`)
  rows.push(`中等成功概率,${(op.moderateSuccess * 100).toFixed(1)}%`)
  rows.push(`明显成功概率,${(op.clearSuccess * 100).toFixed(1)}%`)
  rows.push(`爆款概率,${(op.blockbuster * 100).toFixed(1)}%`)
  rows.push(`长期复利概率,${(op.longCompound * 100).toFixed(1)}%`)

  // 排名
  const r = result.ranking
  rows.push(`超过中位数,${(r.aboveMedian * 100).toFixed(1)}%`)
  rows.push(`Top 30%,${(r.top30 * 100).toFixed(1)}%`)
  rows.push(`Top 20%,${(r.top20 * 100).toFixed(1)}%`)
  rows.push(`Top 10%,${(r.top10 * 100).toFixed(1)}%`)
  rows.push(`Top 5%,${(r.top5 * 100).toFixed(1)}%`)

  // 预测指标
  const f = result.forecast
  rows.push(`曝光 P10,${f.exposure.p10}`)
  rows.push(`曝光 P50,${f.exposure.p50}`)
  rows.push(`曝光 P90,${f.exposure.p90}`)
  rows.push(`用户数 P10,${f.users.p10}`)
  rows.push(`用户数 P50,${f.users.p50}`)
  rows.push(`用户数 P90,${f.users.p90}`)
  rows.push(`收入 P10,${f.revenue.p10}`)
  rows.push(`收入 P50,${f.revenue.p50}`)
  rows.push(`收入 P90,${f.revenue.p90}`)

  const csv = rows.join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${projectName}_模拟结果_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// Benchmark 数据格式
export interface BenchmarkData {
  version: string
  updatedAt: string
  categories: {
    [category: string]: {
      [variable: string]: {
        mean: number
        std: number
        p10: number
        p50: number
        p90: number
        sampleSize: number
      }
    }
  }
}

// 导入 Benchmark 数据
export async function importBenchmarkFromJson(file: File): Promise<BenchmarkData | null> {
  try {
    const text = await file.text()
    const data = JSON.parse(text) as BenchmarkData

    // 验证格式
    if (!data.version || !data.categories) {
      throw new Error('Invalid benchmark file format')
    }

    return data
  } catch (err) {
    console.error('[File] Failed to import benchmark:', err)
    return null
  }
}

// 导出 Benchmark 数据（用于分享）
export function exportBenchmarkToJson(benchmark: BenchmarkData): void {
  const data = JSON.stringify(benchmark, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `benchmark_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// 导出评分配置
export function exportScoresToJson(scores: ScoreProfile, projectName: string): void {
  const data = JSON.stringify(scores, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${projectName}_评分配置_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// 导入评分配置
export async function importScoresFromJson(file: File): Promise<ScoreProfile | null> {
  try {
    const text = await file.text()
    const data = JSON.parse(text) as ScoreProfile

    // 基础验证
    if (typeof data !== 'object' || data === null) {
      throw new Error('Invalid scores file format')
    }

    return data
  } catch (err) {
    console.error('[File] Failed to import scores:', err)
    return null
  }
}
