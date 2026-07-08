// ============================================================
// simulation-tiers — 付费区能力矩阵（单一事实来源）
// ============================================================
//
// 基础区 basic          = 快速模式 (1 万次)    免费（每日限额，超额 1 点）
// 专业区 pro            = 标准模式 (5 万次)    3 点 / Pro 会员
// 旗舰区 flagship       = 深度模式 (10 万次)   6 点 / Pro 会员
// 机构级 institutional  = 机构模式 (50 万次)   25 点 / Team 会员
//
// Worker 按矩阵裁剪计算量，UI 按矩阵渲染锁卡与升级引导，
// 定价页按矩阵生成能力对照表——三处共用，避免各写一份漂移。

import type { SimMode, SimTierId } from '@/types'

/** 各付费区解锁的引擎能力 */
export interface TierCapabilities {
  tier: SimTierId
  /** 对应模拟模式（能力区与模式一一对应） */
  mode: SimMode
  /** 蒙特卡洛世界线数量 */
  runs: number
  /** 敏感性分析（8 变量扰动） */
  sensitivity: boolean
  /** 策略对比模拟（7 策略） */
  strategies: boolean
  /** 分位路径带 P10-P90 */
  pathBands: boolean
  /** 里程碑达成概率（用户/收入） */
  milestones: boolean
  /** 生存分析（崩盘时间分布） */
  survival: boolean
  /** 场景分解（各场景死亡/成功率） */
  scenarioBreakdown: boolean
  /** LTV 与极端世界线 */
  ltvAndExtremes: boolean
  /** 产品诊断深度：摘要版 / 完整版 */
  insightLevel: 'summary' | 'full'
  /** Markdown 报告下载（复制所有档可用） */
  markdownDownload: boolean
  /** JSON 摘要导出 */
  jsonExport: boolean
  /** 案例库对标排名 */
  benchmark: boolean
  /** 多作品对比看板（Team / 机构级） */
  compareBoard: boolean
}

const TIERS: Record<SimTierId, TierCapabilities> = {
  basic: {
    tier: 'basic',
    mode: 'quick',
    runs: 10000,
    sensitivity: false,
    strategies: false,
    pathBands: false,
    milestones: false,
    survival: false,
    scenarioBreakdown: false,
    ltvAndExtremes: false,
    insightLevel: 'summary',
    markdownDownload: false,
    jsonExport: false,
    benchmark: false,
    compareBoard: false,
  },
  pro: {
    tier: 'pro',
    mode: 'standard',
    runs: 50000,
    sensitivity: true,
    strategies: true,
    pathBands: true,
    milestones: true,
    survival: false,
    scenarioBreakdown: false,
    ltvAndExtremes: false,
    insightLevel: 'full',
    markdownDownload: true,
    jsonExport: false,
    benchmark: false,
    compareBoard: false,
  },
  flagship: {
    tier: 'flagship',
    mode: 'deep',
    runs: 100000,
    sensitivity: true,
    strategies: true,
    pathBands: true,
    milestones: true,
    survival: true,
    scenarioBreakdown: true,
    ltvAndExtremes: true,
    insightLevel: 'full',
    markdownDownload: true,
    jsonExport: true,
    benchmark: true,
    compareBoard: false,
  },
  institutional: {
    tier: 'institutional',
    mode: 'ultra',
    runs: 500000,
    sensitivity: true,
    strategies: true,
    pathBands: true,
    milestones: true,
    survival: true,
    scenarioBreakdown: true,
    ltvAndExtremes: true,
    insightLevel: 'full',
    markdownDownload: true,
    jsonExport: true,
    benchmark: true,
    compareBoard: true,
  },
}

const MODE_TO_TIER: Record<SimMode, SimTierId> = {
  quick: 'basic',
  standard: 'pro',
  deep: 'flagship',
  ultra: 'institutional',
}

export function getTierForMode(mode: SimMode): TierCapabilities {
  return TIERS[MODE_TO_TIER[mode]]
}

export function getTier(tier: SimTierId): TierCapabilities {
  return TIERS[tier]
}

/** 定价页能力对照矩阵行（i18n 标签 key 由页面侧映射） */
export const TIER_MATRIX_FEATURES = [
  'runs',
  'sensitivity',
  'strategies',
  'pathBands',
  'milestones',
  'survival',
  'scenarioBreakdown',
  'ltvAndExtremes',
  'insightLevel',
  'markdownDownload',
  'jsonExport',
  'benchmark',
  'compareBoard',
] as const

export type TierMatrixFeature = (typeof TIER_MATRIX_FEATURES)[number]

export const TIER_ORDER: SimTierId[] = ['basic', 'pro', 'flagship', 'institutional']

/** 判断某能力在某档是否解锁（矩阵布尔字段通用取值） */
export function isFeatureUnlocked(tier: SimTierId, feature: TierMatrixFeature): boolean {
  const cap = TIERS[tier]
  if (feature === 'runs') return true
  if (feature === 'insightLevel') return cap.insightLevel === 'full'
  return cap[feature] === true
}
