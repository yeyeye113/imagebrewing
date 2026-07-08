// ============================================================
// Utility helpers
// ============================================================

import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

/** 配置页 / 新建页等选项芯片统一样式 */
export function chipButtonClass(selected: boolean, className?: string) {
  return cn(
    'px-3 py-2 text-sm rounded-md border transition-colors cursor-pointer text-left',
    selected
      ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 border-gray-900 dark:border-gray-100'
      : 'bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600',
    className,
  )
}

/** Generate a short random ID */
export function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

/** Clamp a number between min and max */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

/** Format number with commas */
export function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return n.toFixed(0)
}

/** Format percentage */
export function formatPercent(n: number): string {
  return (n * 100).toFixed(1) + '%'
}

/** Quantile from sorted array */
export function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0
  const pos = (sorted.length - 1) * q
  const base = Math.floor(pos)
  const rest = pos - base
  if (sorted[base + 1] !== undefined) {
    return sorted[base] + rest * (sorted[base + 1] - sorted[base])
  }
  return sorted[base]
}

/** Normal random via Box-Muller */
export function normalRandom(mean = 0, stddev = 1): number {
  const u1 = Math.random()
  const u2 = Math.random()
  const z = Math.sqrt(-2 * Math.log(u1 || 0.0001)) * Math.cos(2 * Math.PI * u2)
  return mean + z * stddev
}

/** Artifact type display names */
export const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  software: '软件',
  app: 'App',
  game: '游戏',
  website: '网站',
  video: '视频',
  article: '文章',
  community: '社区',
  ai_agent: 'AI Agent',
  business_idea: '商业创意',
  open_source: '开源项目',
}

/** Stage display names */
export const STAGE_LABELS: Record<string, string> = {
  idea: '想法',
  prototype: '原型',
  demo: 'Demo',
  mvp: 'MVP',
  launched: '已发布',
  growth: '增长期',
  stagnant: '停滞期',
  decline: '衰退期',
}

/** Strategy display names */
export const STRATEGY_LABELS: Record<string, string> = {
  original: '原始版本',
  clarity_boost: '强化清晰度',
  distribution_boost: '强化传播性',
  retention_boost: '强化留存',
  monetization_boost: '强化商业化',
  quality_boost: '强化质量稳定性',
  community_boost: '强化社区',
}

/** Outcome display names */
export const OUTCOME_LABELS: Record<string, string> = {
  dead: '死亡 / 无效发布',
  low_alive: '低热度存活',
  niche_success: '小众成功',
  moderate_success: '中等成功',
  clear_success: '明显成功',
  blockbuster: '爆款 / 头部',
  long_compound: '长期复利型',
}

/** Scenario display names */
export const SCENARIO_LABELS: Record<string, string> = {
  baseline: '基准场景',
  optimistic: '乐观场景',
  pessimistic: '悲观场景',
  black_swan: '黑天鹅场景',
  long_compound: '长期复利场景',
  competitor_shock: '竞品冲击',
  platform_boost: '平台推荐',
  negative_event: '负面事件',
}

/** Mode display names */
export const MODE_LABELS: Record<string, string> = {
  quick: '快速模式 (1万次)',
  standard: '标准模式 (5万次)',
  deep: '深度模式 (10万次)',
}

/** Variable descriptions */
export const VARIABLE_DESCRIPTIONS: Record<string, string> = {
  quality: '整体质量',
  originality: '新颖度',
  clarity: '用户是否一眼看懂',
  usability: '易用性',
  emotionalHook: '情绪钩子 / 爽点 / 记忆点',
  differentiation: '差异化',
  completeness: '完成度',
  reliability: '稳定性',
  aestheticQuality: '审美质量',
  problemSolutionFit: '问题解决匹配度',
  marketSize: '市场空间',
  audiencePain: '用户痛点强度',
  willingnessToPay: '付费意愿',
  trendFit: '趋势匹配度',
  timingScore: '时机成熟度',
  competitionIntensity: '竞争强度',
  substitutionRisk: '替代风险',
  platformDependency: '平台依赖度',
  regulatoryRisk: '政策 / 平台规则风险',
  categoryGrowth: '品类增长速度',
  shareability: '可分享性',
  viralityPotential: '病毒传播潜力',
  storyValue: '故事性',
  socialProofPotential: '社会证明潜力',
  creatorReputation: '创作者影响力',
  distributionPower: '渠道能力',
  communityPotential: '社区潜力',
  mediaFriendliness: '媒体友好度',
  recommendationFit: '平台推荐适配度',
  visualSpreadPower: '视觉传播力',
  activationRatePotential: '激活潜力',
  firstSessionValue: '首次体验价值',
  retentionPotential: '留存潜力',
  habitPotential: '习惯形成潜力',
  networkEffect: '网络效应',
  switchingCost: '迁移成本',
  longTermValue: '长期价值',
  updateVelocity: '迭代能力',
  feedbackLoopStrength: '反馈闭环强度',
  communityLockIn: '社区锁定能力',
  monetizationFit: '变现适配度',
  pricingPower: '定价能力',
  arpuPotential: '单用户价值潜力',
  conversionPotential: '转化潜力',
  upsellPotential: '增购潜力',
  enterprisePotential: '企业客户潜力',
  lowCostDistribution: '低成本获客能力',
  grossMarginPotential: '毛利潜力',
  lifecycleValue: '生命周期价值',
  revenueDiversity: '收入来源多样性',
  executionRisk: '执行风险',
  technicalDebt: '技术债',
  churnRisk: '流失风险',
  negativeFeedbackRisk: '负面反馈风险',
  copycatRisk: '被复制风险',
  scalabilityRisk: '扩展风险',
  maintenanceBurden: '维护负担',
  legalRisk: '法律风险',
  platformBanRisk: '平台封禁 / 降权风险',
  founderDependency: '对创作者本人依赖度',
}

/** Variable Chinese names */
export const VARIABLE_NAMES: Record<string, string> = {
  quality: '质量', originality: '新颖度', clarity: '清晰度', usability: '易用性',
  emotionalHook: '情绪钩子', differentiation: '差异化', completeness: '完成度',
  reliability: '稳定性', aestheticQuality: '审美质量', problemSolutionFit: '问题匹配度',
  marketSize: '市场空间', audiencePain: '痛点强度', willingnessToPay: '付费意愿',
  trendFit: '趋势匹配', timingScore: '时机成熟度', competitionIntensity: '竞争强度',
  substitutionRisk: '替代风险', platformDependency: '平台依赖', regulatoryRisk: '政策风险',
  categoryGrowth: '品类增长', shareability: '可分享性', viralityPotential: '病毒传播',
  storyValue: '故事性', socialProofPotential: '社会证明', creatorReputation: '创作者影响力',
  distributionPower: '渠道能力', communityPotential: '社区潜力', mediaFriendliness: '媒体友好',
  recommendationFit: '推荐适配', visualSpreadPower: '视觉传播力',
  activationRatePotential: '激活潜力', firstSessionValue: '首次体验', retentionPotential: '留存潜力',
  habitPotential: '习惯形成', networkEffect: '网络效应', switchingCost: '迁移成本',
  longTermValue: '长期价值', updateVelocity: '迭代能力', feedbackLoopStrength: '反馈闭环',
  communityLockIn: '社区锁定', monetizationFit: '变现适配', pricingPower: '定价能力',
  arpuPotential: '单用户价值', conversionPotential: '转化潜力', upsellPotential: '增购潜力',
  enterprisePotential: '企业潜力', lowCostDistribution: '低成本获客', grossMarginPotential: '毛利潜力',
  lifecycleValue: '生命周期价值', revenueDiversity: '收入多样性', executionRisk: '执行风险',
  technicalDebt: '技术债', churnRisk: '流失风险', negativeFeedbackRisk: '负面反馈风险',
  copycatRisk: '被复制风险', scalabilityRisk: '扩展风险', maintenanceBurden: '维护负担',
  legalRisk: '法律风险', platformBanRisk: '平台封禁风险', founderDependency: '创始人依赖',
}
