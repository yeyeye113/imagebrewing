// ============================================================
// Monte Carlo Simulation Web Worker — 最强版 v3
// ============================================================
//
// v2 校准依据（2025-06-29 案例库洞察，全部保留）：
// - 痛点强度是最强预测变量 → pain_intensity 权重 ↑
// - 留存是长期复利的关键 → retention 权重 ↑
// - 分发弱不等于死亡 → distribution 权重 ↓
// - 高曝光低留存是最危险路径 → 添加留存衰减模型
// - 幂律分布：少数产品获得大部分曝光
// - 新鲜感衰减：热度后快速下降
//
// v3 强化（分类校准资产 classifyOutcome / WEIGHTS / SIM 保持不动）：
// - 相关随机因子：算法运气/时机/病毒机会经高斯 copula 相关（好运常叠加），
//   边际分布不变故校准不漂移，联合尾部更贴近真实世界
// - 周度季节性：获取增长按 7 天周期对称波动（均值≈1）
// - 病毒余震：爆款世界线在 14-45 天内小概率出现二次传播波
// - 流式路径聚合：分位路径带 P10-P90 以蓄水池采样计算，
//   10 万世界线不再全量持有路径 → 内存从 GB 级降至 MB 级
// - 新分析：里程碑达成概率 / 生存分析 / 场景分解 / Wilson 置信区间 /
//   LTV 近似 / 极端世界线（按付费区 simulation-tiers 裁剪输出）
//

import type { ScoreProfile, SimulationConfig, SimulationResult, OutcomeClass, PathDataPoint, SensitivityResult, StrategyResult, WarningIndicator, RankingStats, ForecastMetrics, RiskAnalysis, OutcomeProbabilities, SimScenario, StrategyType, ArtifactProfile, ProductInsightReport, SimulationProgress, AdvancedAnalytics, PathBandPoint, MilestoneStat, SurvivalAnalysis, ScenarioStat } from '../types'
import { computeBenchmarkRanking } from '../lib/benchmark.ts'
import { computeConfidence, computeDataCompleteness } from '../lib/completeness.ts'
import { buildProductInsightReport, insightToFailurePaths, insightToSuccessPaths } from '../lib/product-insight-report.ts'
import { buildDynamicOptimizationSuggestions } from '../lib/optimization-builder.ts'
import { getInsightTexts, getLabels, type Locale } from '../lib/i18n/index.ts'
import { getTierForMode } from '../lib/simulation-tiers.ts'
import { quantile, clamp } from '../lib/utils.ts'

// ---- 日志模块 ----
type LogLevel = 'debug' | 'info' | 'warn' | 'error'
type LogModule = 'engine' | 'worker' | 'simulation'

function workerLog(level: LogLevel, module: LogModule, message: string, meta?: Record<string, unknown>) {
  const entry = {
    level,
    module,
    message,
    meta,
    ts: Date.now(),
  }
  // 通过 postMessage 转发到主线程的日志系统
  self.postMessage({ type: 'log', entry })
}

// ---- 可复现随机源 ----
// 默认用 Math.random；当 config.seed 给定时切换为 mulberry32(seed)，使
// "同一输入 + 同一 seed → 完全一致的世界线"，支持回归对比与复跑验证。
function mulberry32(seed: number): () => number {
  let s = seed >>> 0
  return function () {
    s = (s + 0x6d2b79f5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

let rng: () => number = Math.random

/** 设定随机源：传入 seed 则结果可复现，传 undefined 回退非确定性 Math.random。 */
export function setSeed(seed?: number): void {
  rng = seed === undefined ? Math.random : mulberry32(seed)
}

// ---- Math helpers ----

function normalRandom(mean = 0, stddev = 1): number {
  const u1 = rng()
  const u2 = rng()
  const z = Math.sqrt(-2 * Math.log(u1 || 0.0001)) * Math.cos(2 * Math.PI * u2)
  return mean + z * stddev
}

function avg(arr: number[]): number {
  return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0
}

/** 让出事件循环：单线程 Worker 借此在敏感性/策略等长任务中接收 cancel 消息并上报阶段 */
function yieldToLoop(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

/** 幂律随机数（由给定均匀数驱动）：模拟曝光的长尾分布，供相关运气因子复用同一分布形状 */
function powerLawFromUniform(u: number, min: number, max: number, alpha = 2.5): number {
  const value = min * Math.pow(1 - u, -1 / (alpha - 1))
  return value > max ? max : value
}

/** 标准正态 CDF（Abramowitz-Stegun 近似，误差 < 7.5e-8） */
function normCdf(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z))
  const d = 0.3989423 * Math.exp(-z * z / 2)
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
  return z > 0 ? 1 - p : p
}

// ---- 相关运气因子（高斯 copula） ----
// 现实中"运气"并非独立：踩中时机的产品更易被算法推荐、也更易触发病毒传播。
// 用共享潜在因子生成相关标准正态，再经 normCdf 转均匀数驱动各运气变量——
// 边际分布与 v2 完全一致（不动校准），仅联合分布尾部相关。
// 相关强度经回测校准：过高会使规模分布两尾变肥、扰动 classifyOutcome
// 的规模阈值边界案例（如 Post Bridge），0.22 在「联合尾部真实」与
// 「校准不漂移」间取得平衡（回测门禁：不低于 v2 基线）
const LUCK_RHO = 0.22

interface LuckDraw {
  /** 驱动平台算法运气的均匀数（进幂律反演） */
  algorithmU: number
  /** 时机运气的相关标准正态（直接用 z，保持正态边际） */
  timingZ: number
  /** 驱动病毒传播机会的均匀数 */
  viralU: number
}

function correlatedLuck(): LuckDraw {
  // 单因子结构：z_i = √ρ·common + √(1-ρ)·idiosyncratic
  const common = normalRandom(0, 1)
  const load = Math.sqrt(LUCK_RHO)
  const resid = Math.sqrt(1 - LUCK_RHO)
  const timingZ = load * common + resid * normalRandom(0, 1)
  return {
    algorithmU: normCdf(load * common + resid * normalRandom(0, 1)),
    timingZ,
    viralU: normCdf(load * common + resid * normalRandom(0, 1)),
  }
}

/** 二项比例的 Wilson 95% 置信区间（模拟次数越多区间越窄） */
function wilsonCI(p: number, n: number): { low: number; high: number } {
  if (n <= 0) return { low: 0, high: 1 }
  const z = 1.96
  const z2 = z * z
  const denom = 1 + z2 / n
  const center = (p + z2 / (2 * n)) / denom
  const margin = (z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
  return { low: clamp(center - margin, 0, 1), high: clamp(center + margin, 0, 1) }
}

// ---- 校准后的权重（基于案例库洞察） ----

const WEIGHTS = {
  // 权重分配：痛点↑(0.18), 留存↑(0.22), 分发↓(0.12)
  product: 0.20,    // 作品本体
  market: 0.18,     // 市场（含痛点强度）
  distribution: 0.12, // 传播（降低）
  retention: 0.22,  // 留存（提高）
  business: 0.13,   // 商业化
  risk: 0.15,       // 风险（提高）
}

// 模拟核心系数：具名化原先散落在 simulateOneRun 中的魔法数字（数值与校准版保持一致，仅提升可读/可调）
const SIM = {
  baseExposureScale: 8000,  // 初始曝光基数
  exposurePerUser: 2.5,     // 每用户带来的曝光倍数
  organicGrowthRate: 0.015, // 有机增长日系数
  wordOfMouthRate: 0.0008,  // 口碑增长系数
  churnDailyScale: 0.005,   // 流失日系数
  revenuePerActive: 0.008,  // 活跃用户日收入系数
  arpuBase: 0.4,            // ARPU 基数
  shareRate: 0.008,         // 分享数系数
} as const

// ---- 分数标准化 ----

function normalizeScore(score: number): number {
  return score / 100
}

// ---- Weighted composite scores ----

export function computeCompositeScore(scores: ScoreProfile): {
  productScore: number
  marketScore: number
  distributionScore: number
  retentionScore: number
  businessScore: number
  riskScore: number
  overall: number
  // 细分指标
  clarityScore: number
  painScore: number
  differentiationScore: number
} {
  const a = scores.artifact
  const productScore = avg([a.quality, a.originality, a.clarity, a.usability, a.emotionalHook, a.differentiation, a.completeness, a.reliability, a.aestheticQuality, a.problemSolutionFit])

  const m = scores.market
  const marketScore = avg([m.marketSize, m.audiencePain, m.willingnessToPay, m.trendFit, m.timingScore, (100 - m.competitionIntensity), (100 - m.substitutionRisk), (100 - m.platformDependency), (100 - m.regulatoryRisk), m.categoryGrowth])

  const d = scores.distribution
  const distributionScore = avg([d.shareability, d.viralityPotential, d.storyValue, d.socialProofPotential, d.creatorReputation, d.distributionPower, d.communityPotential, d.mediaFriendliness, d.recommendationFit, d.visualSpreadPower])

  const r = scores.retention
  const retentionScore = avg([r.activationRatePotential, r.firstSessionValue, r.retentionPotential, r.habitPotential, r.networkEffect, r.switchingCost, r.longTermValue, r.updateVelocity, r.feedbackLoopStrength, r.communityLockIn])

  const b = scores.business
  const businessScore = avg([b.monetizationFit, b.pricingPower, b.arpuPotential, b.conversionPotential, b.upsellPotential, b.enterprisePotential, b.lowCostDistribution, b.grossMarginPotential, b.lifecycleValue, b.revenueDiversity])

  const risk = scores.risk
  const riskScore = 100 - avg([risk.executionRisk, risk.technicalDebt, risk.churnRisk, risk.negativeFeedbackRisk, risk.copycatRisk, risk.scalabilityRisk, risk.maintenanceBurden, risk.legalRisk, risk.platformBanRisk, risk.founderDependency])

  // 细分指标
  const clarityScore = a.clarity
  const painScore = m.audiencePain
  const differentiationScore = a.differentiation

  const overall =
    productScore * WEIGHTS.product +
    marketScore * WEIGHTS.market +
    distributionScore * WEIGHTS.distribution +
    retentionScore * WEIGHTS.retention +
    businessScore * WEIGHTS.business +
    riskScore * WEIGHTS.risk

  return { productScore, marketScore, distributionScore, retentionScore, businessScore, riskScore, overall, clarityScore, painScore, differentiationScore }
}

// ---- 留存曲线模型 ----
// 基于真实产品留存曲线：D1→D7→D30 指数衰减

function retentionCurve(d1: number, days: number): number {
  // 两段式衰减：D1-D7 快速衰减，D7-D180 缓慢衰减
  // 校准依据：真实产品 D7≈D1*0.5, D30≈D1*0.3, D180≈D1*0.15
  if (days <= 7) {
    return d1 * Math.pow(days / 1, -0.3)  // 快速衰减
  }
  // D7 之后衰减变慢
  const d7 = d1 * Math.pow(7, -0.3)
  return d7 * Math.pow(days / 7, -0.12)  // 缓慢衰减
}

// ---- 竞争挤压效应 ----

function competitionSqueeze(
  competitionPressure: number,  // 0-100
  differentiation: number,      // 0-100
  day: number,
): number {
  const base = competitionPressure / 100
  const diffBuffer = differentiation / 100 * 0.6
  const squeeze = Math.max(0, base - diffBuffer)
  const severity = competitionPressure >= 75 ? 0.72 : competitionPressure >= 60 ? 0.58 : 0.5
  return 1 - squeeze * Math.min(1, day / 180) * severity
}

// ---- 新鲜感衰减 ----

function fatigueFactor(day: number, viralBoost: number): number {
  // 爆款有更强的新鲜感衰减
  if (viralBoost <= 1) return 1
  const halfLife = viralBoost > 5 ? 14 : 30 // 爆款衰减更快
  return Math.max(0.3, Math.exp(-day / halfLife * 0.5))
}

// ---- 场景扰动修正 ----
// 让 config.scenarios 真正生效：不同场景改变随机扰动分布（平台运气 / 病毒 / 负面 / 市场噪音）
interface ScenarioModifier {
  algorithmLuckMult: number
  viralChanceBoost: number
  negChanceBoost: number
  marketNoiseMult: number
}

const BASELINE_MOD: ScenarioModifier = { algorithmLuckMult: 1, viralChanceBoost: 0, negChanceBoost: 0, marketNoiseMult: 1 }

function scenarioModifier(scenario: SimScenario): ScenarioModifier {
  switch (scenario) {
    case 'optimistic': return { algorithmLuckMult: 1.3, viralChanceBoost: 0.05, negChanceBoost: -0.03, marketNoiseMult: 1.1 }
    case 'pessimistic': return { algorithmLuckMult: 0.75, viralChanceBoost: -0.03, negChanceBoost: 0.05, marketNoiseMult: 0.95 }
    case 'black_swan': return { algorithmLuckMult: 1.0, viralChanceBoost: 0.03, negChanceBoost: 0.08, marketNoiseMult: 1.3 }
    case 'platform_boost': return { algorithmLuckMult: 1.6, viralChanceBoost: 0.08, negChanceBoost: 0, marketNoiseMult: 1.0 }
    case 'competitor_shock': return { algorithmLuckMult: 0.8, viralChanceBoost: -0.02, negChanceBoost: 0.06, marketNoiseMult: 1.0 }
    case 'negative_event': return { algorithmLuckMult: 0.9, viralChanceBoost: 0, negChanceBoost: 0.12, marketNoiseMult: 1.0 }
    case 'long_compound': return { algorithmLuckMult: 0.95, viralChanceBoost: -0.02, negChanceBoost: -0.02, marketNoiseMult: 0.9 }
    case 'baseline':
    default: return BASELINE_MOD
  }
}

// ---- 单次模拟 ----

// 里程碑阈值（用户数 / 累计收入）：与 MilestoneStat 输出一一对应
export const USER_MILESTONES = [1000, 10000, 100000] as const
export const REVENUE_MILESTONES = [1000, 10000, 100000] as const

export interface RunResult {
  outcomeClass: OutcomeClass
  finalUsers: number
  finalRevenue: number
  finalActiveUsers: number
  peakExposure: number
  retentionRate: number
  pathData: PathDataPoint[]
  /** 本世界线所属场景（场景分解用） */
  scenario: SimScenario
  /** 首次崩盘日：用户规模跌破生存线的第一天（未崩盘为 null） */
  crashDay: number | null
  /** 用户里程碑首达日（对应 USER_MILESTONES，未达为 null） */
  userMilestoneDays: (number | null)[]
  /** 收入里程碑首达日（对应 REVENUE_MILESTONES，未达为 null） */
  revenueMilestoneDays: (number | null)[]
}

// ---- 结果分类 ----

export interface ClassifyInput {
  currentUsers: number
  finalRetention: number
  viralBoost: number
  painFactor: number
  retainFactor: number
  distFactor: number
  diffFactor: number
  distRetentionGap: number
  externalDeathChance: number
  competitionIntensity: number
  legalRisk: number
  founderDependency: number
  clarityFactor: number
  luck: number
}

/**
 * 分层结果分类（去过拟合重构版 v5）
 *
 * 替代原 40+ 条按具体产品名硬编码的窄区间（那是导致回测虚假 100%、验证集数据泄漏的根因）。
 * 四层设计，全部使用可泛化的维度规则，不含任何案例名：
 *   A. 外部结构性死亡——监管/合规、红海碾压、外部风险实现（与规模无关的致命因素）
 *   B. 规模死亡 / 低活——由模拟终态用户规模驱动，蒙特卡洛在此真正生效
 *   C. hype 崩塌——分发远超留存、撑不住流量
 *   D. 成功谱系——由留存主导度 + 规模 + 三维强度细分：长期复利/明显成功/爆款/利基/中等
 *
 * 注：niche_success / low_alive / moderate_success 三类在结构特征空间高度重叠
 * （数据实测：相同 rf/df/pain 对应不同真实结局），这是命中率的天然上限；
 * 此处给出最可能类别，剩余不确定性由蒙特卡洛的用户/留存/病毒随机分布体现。
 */
export function classifyOutcome(input: ClassifyInput): OutcomeClass {
  const {
    currentUsers: u, finalRetention: ret, viralBoost: viral,
    painFactor: pain, retainFactor: rf, distFactor: df,
    externalDeathChance: extDeath,
    competitionIntensity: comp, legalRisk, luck,
  } = input

  // ===== Layer A：外部结构性死亡（覆盖任意规模，靠维度而非案例名）=====
  // 监管 / 合规 / 重资产崩塌：法律风险本身即致命
  if (legalRisk >= 52) return 'dead'
  // 红海碾压：极高竞争 + 无留存护城河 + 分发未强势碾压（阈值 73：成功案例竞争强度实测 ≤70）
  // df ≤ rf+0.20 排除"分发驱动的弱幸存者"（强分发能拖住而非猝死 → 低活而非死亡）
  if (comp >= 73 && rf < 0.62 && df <= rf + 0.20) return 'dead'
  // 外部风险实现（平台依赖 / 被复制 / 竞争的概率性死亡）
  if (extDeath > 0.5 && luck < extDeath) return 'dead'

  // ===== Layer B：规模死亡 / 低活（终态驱动）=====
  if (u < 30) return 'dead'
  if (u < 200) {
    if (ret < 0.15 || (pain < 0.5 && rf < 0.45)) return 'dead'
    // 强痛点小规模服务型：初期规模小但需求真实（分发受限的中等成功邻域）
    if (pain >= 0.62 && rf >= 0.42 && df < 0.6) return 'moderate_success'
    return 'low_alive'
  }

  // ===== Layer C：hype 崩塌（分发远超留存、留存撑不住）=====
  if (df - rf >= 0.22 && rf < 0.5 && ret < 0.23) {
    return u >= 4000 ? 'low_alive' : 'dead'
  }

  // ===== Layer D：成功谱系（u ≥ 200 且结构未崩）=====
  // 留存主导复利：留存高 + 分发不高（慢热但极黏，靠口碑/SEO 长尾而非渠道爆发）
  if (rf >= 0.66 && df <= 0.62 && ret >= 0.22) return 'long_compound'

  const big = u >= 8000
  // 爆款：极强三维 + 病毒或超大规模
  if (big && pain >= 0.85 && df >= 0.72 && rf >= 0.6 && (viral > 2 || u >= 60000)) return 'blockbuster'
  // 明显成功：中高留存 + 中高分发 + 强痛点 + 已规模化
  if (big && rf >= 0.56 && df >= 0.5 && pain >= 0.78) return 'clear_success'

  // 强痛点区：利基成功 vs 低活（分发明显超留存 → 拉新易留存难 → 低活）
  if (pain >= 0.74 && (rf >= 0.5 || df >= 0.55)) {
    if (df >= rf + 0.12) return 'low_alive'
    return 'niche_success'
  }
  // 中强痛点 + 中留存 → 中等成功
  if (pain >= 0.6 && rf >= 0.45) return 'moderate_success'
  // 高留存小圈层 → 利基
  if (rf >= 0.55 && ret >= 0.2) return 'niche_success'
  return 'low_alive'
}

export function simulateOneRun(
  composite: ReturnType<typeof computeCompositeScore>,
  scores: ScoreProfile,
  config: SimulationConfig,
  strategyBoosts: Record<string, number>,
  scenarioMod: ScenarioModifier = BASELINE_MOD,
  scenario: SimScenario = 'baseline',
  /** 敏感性/策略等内部大批量模拟不需要路径，传 false 省去数组构建 */
  collectPath: boolean = true,
): RunResult {
  const noise = () => normalRandom(0, 1)
  const luck = () => rng()

  // 基础参数
  let qualityFactor = normalizeScore(composite.productScore)
  let marketFactor = normalizeScore(composite.marketScore)
  let distFactor = normalizeScore(composite.distributionScore)
  let retainFactor = normalizeScore(composite.retentionScore)
  let bizFactor = normalizeScore(composite.businessScore)
  let riskFactor = normalizeScore(composite.riskScore)

  // 细分参数
  let clarityFactor = normalizeScore(composite.clarityScore)
  const painFactor = normalizeScore(composite.painScore)
  const diffFactor = normalizeScore(composite.differentiationScore)

  // 应用策略加成
  if (strategyBoosts.clarity_boost) clarityFactor = clamp(clarityFactor + strategyBoosts.clarity_boost * 0.08, 0, 1)
  if (strategyBoosts.distribution_boost) distFactor = clamp(distFactor + strategyBoosts.distribution_boost * 0.08, 0, 1)  // 降低加成
  if (strategyBoosts.retention_boost) retainFactor = clamp(retainFactor + strategyBoosts.retention_boost * 0.12, 0, 1)  // 提高加成
  if (strategyBoosts.monetization_boost) bizFactor = clamp(bizFactor + strategyBoosts.monetization_boost * 0.10, 0, 1)
  if (strategyBoosts.quality_boost) qualityFactor = clamp(qualityFactor + strategyBoosts.quality_boost * 0.10, 0, 1)
  if (strategyBoosts.community_boost) retainFactor = clamp(retainFactor + strategyBoosts.community_boost * 0.10, 0, 1)  // 提高加成

  // ---- 随机因素（v3：相关运气因子，边际分布与 v2 一致） ----

  const luckDraw = correlatedLuck()
  // 平台算法运气：幂律分布，少数幸运（受场景修正）
  const algorithmLuck = powerLawFromUniform(luckDraw.algorithmU, 0.5, 3, 2.5) * scenarioMod.algorithmLuckMult
  // 时机运气：正态分布（相关正态 z 直接进原公式，边际不变）
  const timingLuck = clamp(1 + luckDraw.timingZ * 0.25, 0.3, 2)
  // 市场噪音（受场景修正；保持独立——宏观噪音与个体运气无关）
  const marketNoise = clamp((1 + noise() * 0.15) * scenarioMod.marketNoiseMult, 0.5, 1.8)
  // 创作者持续性：Beta 分布偏向中等
  const creatorConsistency = clamp(0.4 + luck() * 0.4 + noise() * 0.1, 0, 1)
  // 病毒传播机会：极其稀有（场景可提升/抑制；与算法/时机运气正相关）
  // 超强痛点+分发产品更易触发病毒传播（ChatGPT 类）
  const megaFitBoost = painFactor > 0.85 && distFactor > 0.85 ? 0.10 : painFactor > 0.75 && distFactor > 0.75 ? 0.04 : 0
  const viralChance = clamp(luckDraw.viralU + scenarioMod.viralChanceBoost + megaFitBoost, 0, 1)
  const negativeChance = clamp(luck() + scenarioMod.negChanceBoost, 0, 1)

  // 病毒传播：极其稀有但影响巨大
  const viralBoost = viralChance > 0.97 ? 10 + luck() * 20 : viralChance > 0.9 ? 3 + luck() * 7 : viralChance > 0.8 ? 1.5 + luck() * 1.5 : 1

  // ---- 分发-留存失衡惩罚 ----
  // 案例校准：Stadia 分发 90 但留存 30 → 应该判死
  // 当分发远高于留存时，说明产品撑不住流量
  const distRetentionGap = Math.max(0, distFactor - retainFactor - 0.1)
  const distRetentionPenalty = 1 - distRetentionGap * 0.9
  // 高分发低留存：热度退去后增长乏力、流失加速（Clubhouse / Stadia 类；需显著分发-留存落差）
  const hypeProduct = distFactor > 0.72 && retainFactor < 0.48 && distFactor - retainFactor > 0.38

  // 市场容量上限：痛点×留存决定规模天花板；红海竞争压低天花板
  const compPenalty = clamp(
    1 - (scores.market.competitionIntensity / 100) * 0.14 * (1 - diffFactor * 0.45),
    0.72,
    1,
  )
  const fitMultiplier = clamp((0.2 + painFactor * 0.45 + retainFactor * 0.38) * compPenalty, 0.15, 1.15)
  const marketCapacity = SIM.baseExposureScale * (1 + marketFactor * 9) * (0.5 + distFactor * 2) * fitMultiplier

  // 低分发产品初始曝光受限（PH-only / 无独立渠道）
  const lowDistExposure = distFactor < 0.42 ? 0.35 + distFactor * 0.85 : 1

  // ---- 初始曝光（幂律分布） ----
  const baseExposure = qualityFactor * distFactor * marketFactor * algorithmLuck * timingLuck * SIM.baseExposureScale * lowDistExposure * distRetentionPenalty
  const initialExposure = baseExposure * viralBoost * marketNoise

  // ---- 访客转化 ----
  // 清晰度影响点击率，痛点影响转化率
  const clickThroughRate = clamp(clarityFactor * 0.12 + distFactor * 0.08 + painFactor * 0.05 + noise() * 0.02, 0.005, 0.25)
  const visitors = initialExposure * clickThroughRate

  const conversionRate = clamp(clarityFactor * 0.25 + painFactor * 0.15 + qualityFactor * 0.1 + (1 - riskFactor) * 0.05 + noise() * 0.03, 0.01, 0.45)
  const initialUsers = visitors * conversionRate

  // ---- 留存曲线 ----
  // D1 留存：基于产品品质 + 清晰度 + 痛点
  const d1Retention = clamp(retainFactor * 0.45 + qualityFactor * 0.2 + clarityFactor * 0.15 + painFactor * 0.2 + noise() * 0.05, 0.05, 0.85)

  // ---- 模拟 ----
  const pathData: PathDataPoint[] = []
  let currentUsers = initialUsers
  let totalRevenue = 0
  let peakExposure = initialExposure
  let activeUsers = initialUsers * d1Retention

  // ---- 统一按天积分 ----
  // 修复原先 day/week/month 因 ×stepDays 与"按步累积"导致结果不一致的问题：
  // 内部始终以 1 天为步长推进 periodDays 天，granularity 仅决定采样输出频率，
  // 故三种粒度的最终状态(currentUsers/finalRetention/outcomeClass)完全一致。
  const sampleEvery = config.granularity === 'day' ? 1 : config.granularity === 'week' ? 7 : 30
  // 负面事件原为"每步"扣减，按天积分后步数增多，按天摊薄（以 7 天为参照）以保持整体冲击量级
  const negDailyScale = 1 / 7

  // ---- v3 遥测与扰动状态 ----
  // 周度季节性：对称正弦（均值≈1），相位随机避免所有世界线同步波动
  const seasonPhase = rng() * 7
  // 病毒余震：爆款世界线在 14-45 天内可能出现一次二次传播小高峰
  const aftershockDay = viralBoost > 3 && rng() < 0.35 ? 14 + Math.floor(rng() * 31) : -1
  let peakUsers = currentUsers
  let crashDay: number | null = null
  const userMilestoneDays: (number | null)[] = USER_MILESTONES.map(() => null)
  const revenueMilestoneDays: (number | null)[] = REVENUE_MILESTONES.map(() => null)

  for (let day = 1; day <= config.periodDays; day++) {
    // ---- 增长（按天）----
    // 有机增长：基于分发能力和创作者持续性
    const organicGrowth = distFactor * SIM.organicGrowthRate * algorithmLuck * creatorConsistency
    // 口碑增长：基于留存和分享
    // 口碑增长：高留存日用工具（Photopea/Obsidian）口碑复利更强
    const habitMultiplier = retainFactor > 0.75 ? 1.35 : retainFactor > 0.6 ? 1.1 : 1
    const wordOfMouth = activeUsers * retainFactor * SIM.wordOfMouthRate * diffFactor * habitMultiplier
    // 竞争挤压
    const squeeze = competitionSqueeze(scores.market.competitionIntensity, scores.artifact.differentiation, day)
    // 新鲜感衰减
    const fatigue = fatigueFactor(day, viralBoost)
    // logistic 增长空间：越接近市场容量增长越慢，根治"口碑正反馈超指数溢出"
    const growthRoom = Math.max(0, 1 - currentUsers / marketCapacity)
    const hypeFade = hypeProduct ? clamp(1 - Math.max(0, day - 21) * 0.0045, 0.22, 1) : 1
    // 周度季节性（±6%，对称不改均值）
    const seasonal = 1 + 0.06 * Math.sin((2 * Math.PI * (day + seasonPhase)) / 7)
    const newUsersStep = (organicGrowth + wordOfMouth) * currentUsers * squeeze * fatigue * growthRoom * hypeFade * seasonal

    // ---- 流失（按天）----
    const currentRetention = retentionCurve(d1Retention, day)
    const churnRate = clamp(1 - currentRetention, 0, 0.6) * (1 + riskFactor * 0.003)
    const hypeChurn = hypeProduct ? (1 - hypeFade) * 0.18 : 0
    const churnedUsers = currentUsers * (churnRate * SIM.churnDailyScale + hypeChurn)

    // ---- 负面事件（按天摊薄）----
    const negEventImpact = (negativeChance > 0.97 ? 0.4 : negativeChance > 0.9 ? 0.15 : negativeChance > 0.8 ? 0.05 : 0) * negDailyScale

    // ---- 更新状态 ----
    currentUsers = clamp(currentUsers + newUsersStep - churnedUsers - currentUsers * negEventImpact, 0, marketCapacity)

    // ---- 病毒余震（一次性二次传播波）----
    if (day === aftershockDay) {
      const aftershockGain = currentUsers * clamp(0.12 * (viralBoost / 10), 0.02, 0.35) * rng()
      currentUsers = clamp(currentUsers + aftershockGain * growthRoom, 0, marketCapacity)
    }

    activeUsers = currentUsers * currentRetention

    // ---- 收入（按天）----
    const arpu = bizFactor * SIM.arpuBase + noise() * 0.08
    const stepRevenue = activeUsers * arpu * SIM.revenuePerActive
    totalRevenue += Math.max(0, stepRevenue)

    // ---- 曝光 ----
    const stepExposure = currentUsers * distFactor * viralBoost * SIM.exposurePerUser * fatigue
    peakExposure = Math.max(peakExposure, stepExposure)

    // ---- v3 遥测：峰值 / 崩盘 / 里程碑 ----
    peakUsers = Math.max(peakUsers, currentUsers)
    if (crashDay === null && day >= 7 && (currentUsers < 30 || (peakUsers > 150 && currentUsers < peakUsers * 0.12))) {
      crashDay = day
    }
    for (let mi = 0; mi < USER_MILESTONES.length; mi++) {
      if (userMilestoneDays[mi] === null && currentUsers >= USER_MILESTONES[mi]) userMilestoneDays[mi] = day
    }
    for (let mi = 0; mi < REVENUE_MILESTONES.length; mi++) {
      if (revenueMilestoneDays[mi] === null && totalRevenue >= REVENUE_MILESTONES[mi]) revenueMilestoneDays[mi] = day
    }

    // ---- 采样输出路径（前 7 天逐日，之后按 granularity 采样）----
    if (collectPath && (day <= 7 || day % sampleEvery === 0 || day === config.periodDays)) {
      pathData.push({ day, users: Math.round(currentUsers), activeUsers: Math.round(activeUsers), revenue: Math.round(totalRevenue), exposure: Math.round(stepExposure), shares: Math.round(currentUsers * distFactor * SIM.shareRate) })
    }
  }

  const finalRetention = clamp(retentionCurve(d1Retention, config.periodDays), 0, 1)

  // ---- 外部风险因子 ----
  // 校准依据：WeWork/Zenefits/Jawbone/Vine/CodeWhisperer 等外部因素死亡
  const externalRiskFactor = clamp(
    (scores.market.platformDependency / 100) * 0.3 +
    (scores.risk.legalRisk / 100) * 0.25 +
    (scores.risk.founderDependency / 100) * 0.2 +
    (scores.risk.copycatRisk / 100) * 0.15 +
    (scores.market.competitionIntensity / 100) * 0.1,
    0, 1
  )
  // 外部事件概率：高风险 + 低差异化 = 更容易被外部因素杀死
  const externalDeathChance = externalRiskFactor * (1 - diffFactor * 0.5)

  // ---- 结果分类（校准版 v4 — 提取为独立函数便于回测调优） ----
  const outcomeClass = classifyOutcome({
    currentUsers,
    finalRetention,
    viralBoost,
    painFactor: normalizeScore(scores.market.audiencePain),
    // 口径修正：分类用与模拟动力学一致的"聚合分"（原用单字段 retentionPotential/distributionPower，两者口径不一致）
    retainFactor: normalizeScore(composite.retentionScore),
    distFactor: normalizeScore(composite.distributionScore),
    diffFactor,
    distRetentionGap,
    externalDeathChance,
    competitionIntensity: scores.market.competitionIntensity,
    legalRisk: scores.risk.legalRisk,
    founderDependency: scores.risk.founderDependency,
    clarityFactor: normalizeScore(scores.artifact.clarity),
    luck: luck(),
  })

  return {
    outcomeClass,
    finalUsers: Math.round(currentUsers),
    finalRevenue: Math.round(totalRevenue),
    finalActiveUsers: Math.round(activeUsers),
    peakExposure: Math.round(peakExposure),
    retentionRate: finalRetention,
    pathData,
    scenario,
    // 分类为死亡但期内未触发崩盘线的，视为期末才失效
    crashDay: outcomeClass === 'dead' ? (crashDay ?? config.periodDays) : crashDay,
    userMilestoneDays,
    revenueMilestoneDays,
  }
}

// ---- 流式路径聚合器（v3） ----
//
// 目的：10 万世界线 × 上百采样点的全量路径持有是内存黑洞（GB 级）。
// 聚合器边跑边吸收每条路径：均值用累计和、分位数用蓄水池采样（每采样日
// 上限 RESERVOIR_CAP 条），并顺手锁定最佳/最差极端世界线——主 runs 数组
// 随后即可剥离 pathData，整体内存降到 MB 级。
//
// 注意：蓄水池的替换抽签用独立 PRNG（不是模拟主 rng），否则会打乱种子
// 序列、破坏「同 seed 同结果」的可复现性。

const RESERVOIR_CAP = 2048

export class PathAggregator {
  private days: number[] = []
  private dayIndex = new Map<number, number>()
  private usersRes: number[][] = []
  private revenueRes: number[][] = []
  private usersSum: number[] = []
  private activeSum: number[] = []
  private revenueSum: number[] = []
  private exposureSum: number[] = []
  private sharesSum: number[] = []
  private counts: number[] = []
  private bestUsers = -1
  private bestPath: PathDataPoint[] = []
  private worstUsers = Number.POSITIVE_INFINITY
  private worstPath: PathDataPoint[] = []
  /** 蓄水池专用独立随机源（与模拟主 rng 隔离） */
  private pick: () => number

  constructor(seed?: number) {
    this.pick = mulberry32((seed ?? 0x5f3759df) ^ 0x9e3779b9)
  }

  static fromRuns(runs: RunResult[], seed?: number): PathAggregator {
    const agg = new PathAggregator(seed)
    for (const r of runs) agg.add(r)
    return agg
  }

  add(run: RunResult): void {
    const path = run.pathData
    if (path.length > 0) {
      if (run.finalUsers > this.bestUsers) {
        this.bestUsers = run.finalUsers
        this.bestPath = path
      }
      if (run.finalUsers < this.worstUsers) {
        this.worstUsers = run.finalUsers
        this.worstPath = path
      }
    }
    for (const p of path) {
      let idx = this.dayIndex.get(p.day)
      if (idx === undefined) {
        idx = this.days.length
        this.days.push(p.day)
        this.dayIndex.set(p.day, idx)
        this.usersRes.push([])
        this.revenueRes.push([])
        this.usersSum.push(0)
        this.activeSum.push(0)
        this.revenueSum.push(0)
        this.exposureSum.push(0)
        this.sharesSum.push(0)
        this.counts.push(0)
      }
      this.usersSum[idx] += p.users
      this.activeSum[idx] += p.activeUsers
      this.revenueSum[idx] += p.revenue
      this.exposureSum[idx] += p.exposure
      this.sharesSum[idx] += p.shares
      const c = this.counts[idx]
      if (c < RESERVOIR_CAP) {
        this.usersRes[idx].push(p.users)
        this.revenueRes[idx].push(p.revenue)
      } else {
        // Algorithm R：以 CAP/(c+1) 概率替换池内随机一条，保证均匀采样
        const j = Math.floor(this.pick() * (c + 1))
        if (j < RESERVOIR_CAP) {
          this.usersRes[idx][j] = p.users
          this.revenueRes[idx][j] = p.revenue
        }
      }
      this.counts[idx]++
    }
  }

  /** 均值路径（替代旧的全量 avgPath 计算） */
  meanPath(): PathDataPoint[] {
    return this.days.map((day, i) => {
      const n = this.counts[i] || 1
      return {
        day,
        users: Math.round(this.usersSum[i] / n),
        activeUsers: Math.round(this.activeSum[i] / n),
        revenue: Math.round(this.revenueSum[i] / n),
        exposure: Math.round(this.exposureSum[i] / n),
        shares: Math.round(this.sharesSum[i] / n),
      }
    })
  }

  /** 分位路径带：P10/P25/P50/P75/P90 用户 + 收入 P50/P90 */
  bands(): PathBandPoint[] {
    return this.days.map((day, i) => {
      const users = [...this.usersRes[i]].sort((a, b) => a - b)
      const revenue = [...this.revenueRes[i]].sort((a, b) => a - b)
      return {
        day,
        p10: Math.round(quantile(users, 0.1)),
        p25: Math.round(quantile(users, 0.25)),
        p50: Math.round(quantile(users, 0.5)),
        p75: Math.round(quantile(users, 0.75)),
        p90: Math.round(quantile(users, 0.9)),
        revenueP50: Math.round(quantile(revenue, 0.5)),
        revenueP90: Math.round(quantile(revenue, 0.9)),
      }
    })
  }

  extremePaths(): { best: PathDataPoint[]; worst: PathDataPoint[] } {
    return { best: this.bestPath, worst: this.worstPath }
  }

  sampleDays(): number[] {
    return [...this.days]
  }

  /** 序列化为可 postMessage 的纯数据（分片子 Worker → 协调 Worker） */
  serialize(): AggregatorState {
    return {
      days: this.days,
      usersRes: this.usersRes,
      revenueRes: this.revenueRes,
      usersSum: this.usersSum,
      activeSum: this.activeSum,
      revenueSum: this.revenueSum,
      exposureSum: this.exposureSum,
      sharesSum: this.sharesSum,
      counts: this.counts,
      bestUsers: this.bestUsers,
      bestPath: this.bestPath,
      worstUsers: this.worstUsers,
      worstPath: this.worstPath,
    }
  }

  /**
   * 归并另一分片的聚合状态：累计和直接相加；蓄水池按占比混合
   * （两片均为均匀样本，按池大小截断合并仍近似均匀，分位估计误差可忽略）。
   */
  merge(state: AggregatorState): void {
    for (let i = 0; i < state.days.length; i++) {
      const day = state.days[i]
      let idx = this.dayIndex.get(day)
      if (idx === undefined) {
        idx = this.days.length
        this.days.push(day)
        this.dayIndex.set(day, idx)
        this.usersRes.push([])
        this.revenueRes.push([])
        this.usersSum.push(0)
        this.activeSum.push(0)
        this.revenueSum.push(0)
        this.exposureSum.push(0)
        this.sharesSum.push(0)
        this.counts.push(0)
      }
      this.usersSum[idx] += state.usersSum[i]
      this.activeSum[idx] += state.activeSum[i]
      this.revenueSum[idx] += state.revenueSum[i]
      this.exposureSum[idx] += state.exposureSum[i]
      this.sharesSum[idx] += state.sharesSum[i]
      // 蓄水池混合：交错采样两池并截断到容量（保持近似均匀）
      const mine = this.usersRes[idx]
      const theirs = state.usersRes[i]
      const mineRev = this.revenueRes[idx]
      const theirsRev = state.revenueRes[i]
      if (mine.length + theirs.length <= RESERVOIR_CAP) {
        this.usersRes[idx] = mine.concat(theirs)
        this.revenueRes[idx] = mineRev.concat(theirsRev)
      } else {
        // 按两池真实样本量占比抽取，避免小片主导
        const total = this.counts[idx] + state.counts[i]
        const takeMine = Math.round((this.counts[idx] / total) * RESERVOIR_CAP)
        const takeTheirs = RESERVOIR_CAP - takeMine
        const pickEvery = (arr: number[], n: number): number[] => {
          if (n >= arr.length) return arr.slice()
          const out: number[] = []
          const step = arr.length / n
          for (let k = 0; k < n; k++) out.push(arr[Math.floor(k * step)])
          return out
        }
        this.usersRes[idx] = pickEvery(mine, takeMine).concat(pickEvery(theirs, takeTheirs))
        this.revenueRes[idx] = pickEvery(mineRev, takeMine).concat(pickEvery(theirsRev, takeTheirs))
      }
      this.counts[idx] += state.counts[i]
    }
    if (state.bestUsers > this.bestUsers && state.bestPath.length > 0) {
      this.bestUsers = state.bestUsers
      this.bestPath = state.bestPath
    }
    if (state.worstUsers < this.worstUsers && state.worstPath.length > 0) {
      this.worstUsers = state.worstUsers
      this.worstPath = state.worstPath
    }
  }
}

/** PathAggregator 的可传输状态 */
export interface AggregatorState {
  days: number[]
  usersRes: number[][]
  revenueRes: number[][]
  usersSum: number[]
  activeSum: number[]
  revenueSum: number[]
  exposureSum: number[]
  sharesSum: number[]
  counts: number[]
  bestUsers: number
  bestPath: PathDataPoint[]
  worstUsers: number
  worstPath: PathDataPoint[]
}

// ---- v3 分析计算 ----

/** 里程碑达成统计：达成率 + 达成者中位天数 */
function computeMilestones(runs: RunResult[]): MilestoneStat[] {
  const n = runs.length || 1
  const out: MilestoneStat[] = []
  const collect = (kind: 'users' | 'revenue', thresholds: readonly number[], pickDays: (r: RunResult) => (number | null)[]) => {
    thresholds.forEach((threshold, i) => {
      const days: number[] = []
      for (const r of runs) {
        const d = pickDays(r)[i]
        if (d !== null && d !== undefined) days.push(d)
      }
      days.sort((a, b) => a - b)
      out.push({
        kind,
        threshold,
        reachProbability: days.length / n,
        medianDay: days.length > 0 ? Math.round(quantile(days, 0.5)) : null,
      })
    })
  }
  collect('users', USER_MILESTONES, (r) => r.userMilestoneDays)
  collect('revenue', REVENUE_MILESTONES, (r) => r.revenueMilestoneDays)
  return out
}

/** 生存分析：存活率曲线 + 中位崩盘日 + 阶段崩盘概率 */
function computeSurvival(runs: RunResult[], sampleDays: number[], periodDays: number): SurvivalAnalysis {
  const n = runs.length || 1
  const crashDays = runs
    .filter((r) => r.crashDay !== null)
    .map((r) => r.crashDay as number)
    .sort((a, b) => a - b)

  // 二分：crashDay ≤ day 的世界线数量
  const crashedBy = (day: number): number => {
    let lo = 0
    let hi = crashDays.length
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (crashDays[mid] <= day) lo = mid + 1
      else hi = mid
    }
    return lo
  }

  const days = sampleDays.length > 0 ? sampleDays : [periodDays]
  const curve = days.map((day) => ({ day, alive: clamp(1 - crashedBy(day) / n, 0, 1) }))

  const phases: { phase: string; from: number; to: number }[] = [
    { phase: 'd0_7', from: 0, to: 7 },
    { phase: 'd8_30', from: 8, to: 30 },
    { phase: 'd31_90', from: 31, to: 90 },
    { phase: 'd91_plus', from: 91, to: Number.POSITIVE_INFINITY },
  ]
  const crashProbByPhase = phases.map(({ phase, from, to }) => ({
    phase,
    prob: crashDays.filter((d) => d >= from && d <= to).length / n,
  }))

  return {
    curve,
    medianCrashDay: crashDays.length > 0 ? Math.round(quantile(crashDays, 0.5)) : null,
    crashProbByPhase,
  }
}

/** 场景分解：各场景的死亡率 / 成功率 / 中位用户 */
function computeScenarioBreakdown(runs: RunResult[]): ScenarioStat[] {
  const groups = new Map<SimScenario, RunResult[]>()
  for (const r of runs) {
    const g = groups.get(r.scenario)
    if (g) g.push(r)
    else groups.set(r.scenario, [r])
  }
  const out: ScenarioStat[] = []
  for (const [scenario, group] of groups) {
    const n = group.length || 1
    let dead = 0
    let success = 0
    const users: number[] = []
    for (const r of group) {
      if (r.outcomeClass === 'dead') dead++
      if (r.outcomeClass === 'clear_success' || r.outcomeClass === 'blockbuster' || r.outcomeClass === 'long_compound') success++
      users.push(r.finalUsers)
    }
    users.sort((a, b) => a - b)
    out.push({
      scenario,
      runs: group.length,
      deathProb: dead / n,
      successProb: success / n,
      medianUsers: Math.round(quantile(users, 0.5)),
    })
  }
  return out.sort((a, b) => b.runs - a.runs)
}

/** LTV 近似：规模可观世界线的「累计收入 / 用户」分位 */
function computeLtvPerUser(runs: RunResult[]): { p50: number; p90: number } {
  const ratios = runs
    .filter((r) => r.finalUsers >= 30)
    .map((r) => r.finalRevenue / r.finalUsers)
    .sort((a, b) => a - b)
  if (ratios.length === 0) return { p50: 0, p90: 0 }
  return {
    p50: Math.round(quantile(ratios, 0.5) * 100) / 100,
    p90: Math.round(quantile(ratios, 0.9) * 100) / 100,
  }
}

/** 摘要版诊断裁剪（基础区）：保留判决与首要死因，隐藏完整改进方案 */
function trimInsightToSummary(insight: ProductInsightReport): ProductInsightReport {
  return {
    ...insight,
    deathReasons: insight.deathReasons.slice(0, 2),
    successOpportunities: insight.successOpportunities.slice(0, 1),
    improvementPlan: insight.improvementPlan.slice(0, 1),
    optimizationStrategies: [],
    actionRoadmap: [],
  }
}

// ---- Monte Carlo Engine ----

/** 分片 seed 派生：同 seed + 同分片布局 → 全局可复现；未设 seed 则各片非确定 */
export function deriveShardSeed(seed: number | undefined, shardIndex: number): number | undefined {
  if (seed === undefined) return undefined
  return (seed + shardIndex * 2654435761) >>> 0
}

/**
 * 跑一个连续分片（供并行子 Worker 与协调者复用）。
 * startIdx 用于场景轮转的全局对齐：第 k 条世界线无论落在哪个分片，
 * 分配到的场景与单线程版完全一致。
 */
export function runShard(
  scores: ScoreProfile,
  config: SimulationConfig,
  strategyBoosts: Record<string, number>,
  startIdx: number,
  count: number,
  shardIndex: number,
  onProgress?: (done: number) => void,
): { runs: RunResult[]; aggState: AggregatorState } {
  setSeed(deriveShardSeed(config.seed, shardIndex))
  const composite = computeCompositeScore(scores)
  const scenarios: SimScenario[] = config.scenarios.length > 0 ? config.scenarios : ['baseline']
  const mods = scenarios.map(scenarioModifier)
  const aggregator = new PathAggregator(deriveShardSeed(config.seed, shardIndex))
  const runs: RunResult[] = []

  for (let i = 0; i < count; i++) {
    const which = (startIdx + i) % mods.length
    const run = simulateOneRun(composite, scores, config, strategyBoosts, mods[which], scenarios[which])
    aggregator.add(run)
    run.pathData = EMPTY_PATH
    runs.push(run)
    if (onProgress && (i + 1) % 2000 === 0) onProgress(i + 1)
  }
  setSeed(undefined)
  return { runs, aggState: aggregator.serialize() }
}

// 并行分片布局：片数固定（与机器核数解耦），保证同 seed 跨机器可复现；
// Worker 池大小按硬件自适应，只影响速度不影响结果。
const SHARD_COUNT = 8
const PARALLEL_MIN_RUNS = 50000

/** 并行主模拟：把世界线均分为固定分片，交给子 Worker 池执行后归并 */
async function runSimulationParallel(
  scores: ScoreProfile,
  config: SimulationConfig,
  strategyBoosts: Record<string, number>,
  onProgress: (completed: number, partial: RunResult[]) => void,
): Promise<{ runs: RunResult[]; aggregator: PathAggregator }> {
  const poolSize = Math.min(SHARD_COUNT, Math.max(1, ((navigator?.hardwareConcurrency ?? 4) | 0) - 1))
  const base = Math.floor(config.runs / SHARD_COUNT)
  const shards = Array.from({ length: SHARD_COUNT }, (_, i) => ({
    shardIndex: i,
    startIdx: i * base,
    count: i === SHARD_COUNT - 1 ? config.runs - base * (SHARD_COUNT - 1) : base,
  }))

  const allRuns: RunResult[] = []
  const aggregator = new PathAggregator(config.seed)
  const progressByShard = new Array<number>(SHARD_COUNT).fill(0)
  const workers: Worker[] = []
  let nextShard = 0
  let doneShards = 0

  const reportProgress = () => {
    const total = progressByShard.reduce((a, b) => a + b, 0)
    onProgress(Math.min(total, config.runs), allRuns)
  }

  await new Promise<void>((resolve, reject) => {
    const launchNext = (worker: Worker) => {
      if (cancelled || nextShard >= shards.length) {
        worker.terminate()
        return
      }
      const shard = shards[nextShard++]
      worker.postMessage({ type: 'shard', scores, config, strategyBoosts, ...shard })
    }

    const spawn = () => {
      const worker = new Worker(new URL('./shard-worker.ts', import.meta.url), { type: 'module' })
      workers.push(worker)
      worker.onmessage = (e: MessageEvent) => {
        const msg = e.data
        if (msg.type === 'shard_progress') {
          progressByShard[msg.shardIndex] = msg.done
          reportProgress()
        } else if (msg.type === 'shard_done') {
          progressByShard[msg.shardIndex] = msg.runs.length
          for (const r of msg.runs) allRuns.push(r)
          aggregator.merge(msg.aggState)
          doneShards++
          reportProgress()
          if (doneShards === shards.length || cancelled) resolve()
          else launchNext(worker)
        }
      }
      worker.onerror = (err) => reject(err)
      launchNext(worker)
    }

    for (let i = 0; i < poolSize; i++) spawn()
  }).finally(() => {
    for (const w of workers) w.terminate()
  })

  return { runs: allRuns, aggregator }
}

async function runSimulation(
  scores: ScoreProfile,
  config: SimulationConfig,
  strategyBoosts: Record<string, number>,
  onProgress: (completed: number, partial: RunResult[]) => void,
): Promise<{ runs: RunResult[]; aggregator: PathAggregator }> {
  // 按 config.seed 初始化随机源：设定后整个模拟（含后续敏感性/策略）可复现
  setSeed(config.seed)
  const composite = computeCompositeScore(scores)
  const results: RunResult[] = []
  const aggregator = new PathAggregator(config.seed)
  const batchSize = 500

  // 让 config.scenarios 真正生效：在所选场景间轮流分配每条世界线
  const scenarios: SimScenario[] = config.scenarios.length > 0 ? config.scenarios : ['baseline']
  const mods = scenarios.map(scenarioModifier)
  let scenarioIdx = 0

  for (let i = 0; i < config.runs; i += batchSize) {
    if (cancelled) break  // 响应取消：单线程 worker 必须在批间让出，才能收到 cancel 消息
    const end = Math.min(i + batchSize, config.runs)
    for (let j = i; j < end; j++) {
      const which = scenarioIdx % mods.length
      const run = simulateOneRun(composite, scores, config, strategyBoosts, mods[which], scenarios[which])
      // 路径立即流入聚合器后剥离，避免十万级路径数组常驻内存
      aggregator.add(run)
      run.pathData = EMPTY_PATH
      results.push(run)
      scenarioIdx++
    }
    onProgress(end, results)
    // 让出事件循环，使 worker 能处理这期间到达的 cancel 消息
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
  }

  return { runs: results, aggregator }
}

/** 剥离后共享的空路径（只读使用） */
const EMPTY_PATH: PathDataPoint[] = []

// ---- 敏感性分析（确定性，无随机） ----

async function computeSensitivity(
  scores: ScoreProfile,
  config: SimulationConfig,
  shouldCancel?: () => boolean,
): Promise<SensitivityResult[]> {
  const keyVariables = [
    { var: 'audiencePain', group: 'market' as const },
    { var: 'clarity', group: 'artifact' as const },
    { var: 'shareability', group: 'distribution' as const },
    { var: 'retentionPotential', group: 'retention' as const },
    { var: 'distributionPower', group: 'distribution' as const },
    { var: 'differentiation', group: 'artifact' as const },
    { var: 'monetizationFit', group: 'business' as const },
    { var: 'technicalDebt', group: 'risk' as const },
  ]

  const n = 1500

  // 基线分布 → 统一"成功阈值"(P90 用户数)，作为所有变量对比的同一把尺，
  // 避免旧实现用各自分布 P90 自比较导致差值恒约 0、以及概率×10000 的量纲错误。
  const baseComposite = computeCompositeScore(scores)
  const baseRuns: RunResult[] = []
  for (let i = 0; i < n; i++) baseRuns.push(simulateOneRun(baseComposite, scores, config, {}, BASELINE_MOD, 'baseline', false))
  const successThreshold = quantile(baseRuns.map(r => r.finalUsers).sort((a, b) => a - b), 0.9)

  const successRate = (runs: RunResult[]) => runs.filter(r => r.finalUsers > successThreshold).length / n
  const deathRate = (runs: RunResult[]) => runs.filter(r => r.outcomeClass === 'dead').length / n

  // 逐变量串行推进；每算完一个变量让出事件循环，使 Worker 能响应 cancel（不改变随机序列 → 结果与同步版一致）
  const raw: SensitivityResult[] = []
  for (const { var: v, group } of keyVariables) {
    if (shouldCancel?.()) break
    const origValue = (scores[group] as unknown as Record<string, number>)[v] ?? 50

    // 扰动幅度对齐 PROMPT：相对 ±20%（而非旧的绝对 ±15 分），更贴合"敏感性"语义。
    // 兜底最小绝对步长 ±5 分：纯相对扰动在原值≈0 时步长趋零（0×1.2=0），
    // 会让低分变量的敏感度恒为 0、系统性漏报最需要补的短板。
    const upScores = structuredClone(scores)
    ;(upScores[group] as unknown as Record<string, number>)[v] = clamp(Math.max(origValue * 1.2, origValue + 5), 0, 100)
    const upRuns: RunResult[] = []
    for (let i = 0; i < n; i++) upRuns.push(simulateOneRun(computeCompositeScore(upScores), upScores, config, {}, BASELINE_MOD, 'baseline', false))

    const downScores = structuredClone(scores)
    ;(downScores[group] as unknown as Record<string, number>)[v] = clamp(Math.min(origValue * 0.8, origValue - 5), 0, 100)
    const downRuns: RunResult[] = []
    for (let i = 0; i < n; i++) downRuns.push(simulateOneRun(computeCompositeScore(downScores), downScores, config, {}, BASELINE_MOD, 'baseline', false))

    const upTop = successRate(upRuns)
    const downTop = successRate(downRuns)
    const upDeath = deathRate(upRuns)
    const downDeath = deathRate(downRuns)

    // 影响强度 = |成功率变化| 与 |死亡率变化| 的均值 (统一阈值，量纲一致)
    const impactStrength = clamp(Math.abs(upTop - downTop) * 0.5 + Math.abs(upDeath - downDeath) * 0.5, 0, 1)

    raw.push({
      variable: v,
      originalValue: origValue,
      top10AfterIncrease: clamp(upTop, 0, 1),
      top10AfterDecrease: clamp(downTop, 0, 1),
      deathProbAfterIncrease: upDeath,
      deathProbAfterDecrease: downDeath,
      impactStrength,
      optimizationPriority: 0,
    })
    await yieldToLoop()
  }
  return raw.sort((a, b) => b.impactStrength - a.impactStrength)
    .map((s, i) => ({ ...s, optimizationPriority: i + 1 }))
}

// ---- 策略对比（确定性，无随机） ----

async function simulateStrategies(
  scores: ScoreProfile,
  config: SimulationConfig,
  shouldCancel?: () => boolean,
): Promise<StrategyResult[]> {
  const allStrategies = [
    { key: 'original', label: '原始版本', boosts: {} as Record<string, number> },
    { key: 'clarity_boost', label: '强化清晰度', boosts: { clarity_boost: 1 } },
    { key: 'distribution_boost', label: '强化传播性', boosts: { distribution_boost: 1 } },
    { key: 'retention_boost', label: '强化留存', boosts: { retention_boost: 1 } },
    { key: 'monetization_boost', label: '强化商业化', boosts: { monetization_boost: 1 } },
    { key: 'quality_boost', label: '强化质量稳定性', boosts: { quality_boost: 1 } },
    { key: 'community_boost', label: '强化社区', boosts: { community_boost: 1 } },
  ]

  // 让 config.strategies 真正生效：只对比用户勾选的策略，且始终保留 original 作基准
  const selectedKeys: StrategyType[] = config.strategies.length > 0 ? config.strategies : allStrategies.map((s) => s.key as StrategyType)
  const strategies = allStrategies.filter((s) => s.key === 'original' || selectedKeys.includes(s.key as StrategyType))

  const n = 3000

  // 逐策略串行推进；每算完一个策略让出事件循环以响应 cancel（不改变随机序列）
  const out: StrategyResult[] = []
  for (const s of strategies) {
    if (shouldCancel?.()) break
    const composite = computeCompositeScore(scores)
    const runs: RunResult[] = []
    for (let i = 0; i < n; i++) {
      runs.push(simulateOneRun(composite, scores, config, s.boosts, BASELINE_MOD, 'baseline', false))
    }
    const counts = { dead: 0, top10: 0, blockbuster: 0 }
    const usersArr: number[] = []
    const revArr: number[] = []
    const usersSorted = runs.map(r => r.finalUsers).sort((a, b) => a - b)
    const p90Threshold = quantile(usersSorted, 0.9)
    for (const r of runs) {
      if (r.outcomeClass === 'dead') counts.dead++
      if (r.finalUsers > p90Threshold) counts.top10++
      if (r.outcomeClass === 'blockbuster') counts.blockbuster++
      usersArr.push(r.finalUsers)
      revArr.push(r.finalRevenue)
    }
    const sorted = [...usersArr].sort((a, b) => a - b)
    const revSorted = [...revArr].sort((a, b) => a - b)

    const deathPenalty = counts.dead / n
    const successBonus = (counts.top10 / n + counts.blockbuster / n) / 2
    const recommendation = clamp(Math.round((1 - deathPenalty) * 3 + successBonus * 2), 1, 5)

    out.push({
      strategy: s.key as any,
      label: s.label,
      deathProb: counts.dead / n,
      top10Prob: counts.top10 / n,
      blockbusterProb: counts.blockbuster / n,
      medianUsers: Math.round(quantile(sorted, 0.5)),
      medianRevenue: Math.round(quantile(revSorted, 0.5)),
      recommendationLevel: recommendation,
    })
    await yieldToLoop()
  }
  return out
}

// ---- Aggregate results ----

/** 聚合模拟结果（供测试与回测工具复用） */
export async function buildSimulationResult(
  runs: RunResult[],
  config: SimulationConfig,
  scores: ScoreProfile,
  strategyBoosts: Record<string, number>,
  profile?: ArtifactProfile | null,
  locale: Locale = 'zh-CN',
): Promise<SimulationResult> {
  return aggregateResults(runs, config, scores, strategyBoosts, profile, locale)
}

async function aggregateResults(
  runs: RunResult[],
  config: SimulationConfig,
  scores: ScoreProfile,
  strategyBoosts: Record<string, number>,
  profile?: ArtifactProfile | null,
  locale: Locale = 'zh-CN',
  onStage?: (stage: SimulationProgress['stage']) => void,
  shouldCancel?: () => boolean,
  aggregator?: PathAggregator,
): Promise<SimulationResult> {
  onStage?.('stats')
  const txt = getInsightTexts(locale)
  const composite = computeCompositeScore(scores)
  // 付费区能力矩阵：决定本次结果包含哪些分析块
  const tier = getTierForMode(config.mode)
  // 外部调用（测试/回测）没有流式聚合器时，就地从 runs 构建
  const agg = aggregator ?? PathAggregator.fromRuns(runs, config.seed)

  // Outcome probabilities
  const counts: Record<OutcomeClass, number> = {
    dead: 0, low_alive: 0, niche_success: 0, moderate_success: 0,
    clear_success: 0, blockbuster: 0, long_compound: 0,
  }
  for (const r of runs) counts[r.outcomeClass]++
  const n = runs.length

  const outcomeProbabilities: OutcomeProbabilities = {
    dead: counts.dead / n,
    lowAlive: counts.low_alive / n,
    nicheSuccess: counts.niche_success / n,
    moderateSuccess: counts.moderate_success / n,
    clearSuccess: counts.clear_success / n,
    blockbuster: counts.blockbuster / n,
    longCompound: counts.long_compound / n,
  }

  // Ranking
  const usersSorted = runs.map((r) => r.finalUsers).sort((a, b) => a - b)
  const medianUsers = quantile(usersSorted, 0.5)
  // 期望排名百分位：原实现为 O(n²)（每个 run 再全量扫一遍），10 万 runs 时达百亿次运算。
  // 数学上"分位均值"对任意分布都≈0.5，用闭式 (n+1)/(2n) 等价替代，降到 O(1)。
  const expectedPctl = n > 0 ? (n + 1) / (2 * n) : 0

  // 排名率：旗舰区用案例库 benchmark 对标；其余档位用结果分布内部估算
  const benchmarkRanking = computeBenchmarkRanking(medianUsers)
  const op = outcomeProbabilities
  const successProb = op.clearSuccess + op.blockbuster + op.longCompound
  const decentProb = op.nicheSuccess + op.moderateSuccess + successProb
  const fallbackRanking: RankingStats = {
    aboveMedian: clamp(1 - op.dead - op.lowAlive, 0, 0.98),
    top30: clamp(decentProb, 0, 0.95),
    top20: clamp(successProb + op.moderateSuccess * 0.5, 0, 0.92),
    top10: clamp(successProb, 0, 0.85),
    top5: clamp(op.blockbuster + op.clearSuccess * 0.4, 0, 0.70),
    top1: clamp(op.blockbuster * 0.6, 0, 0.45),
    expectedPercentile: clamp(expectedPctl, 0, 1),
    medianPercentile: clamp(expectedPctl, 0, 1),
    worst5Percentile: clamp(quantile(usersSorted, 0.05) / (medianUsers || 1), 0, 1),
    best5Percentile: clamp(quantile(usersSorted, 0.95) / (medianUsers || 1), 0.5, 5),
    hasBenchmarkData: false,
  }
  const ranking: RankingStats = tier.benchmark && benchmarkRanking.hasBenchmarkData ? benchmarkRanking : fallbackRanking

  // Forecast
  const usersP10 = quantile(usersSorted, 0.1)
  const usersP90 = quantile(usersSorted, 0.9)
  const activeP = runs.map((r) => r.finalActiveUsers).sort((a, b) => a - b)
  const revP = runs.map((r) => r.finalRevenue).sort((a, b) => a - b)
  const retP = runs.map((r) => r.retentionRate).sort((a, b) => a - b)
  const expP = runs.map((r) => r.peakExposure).sort((a, b) => a - b)
  // 分享数：与 pathData 同口径（用户 × 分发因子 × 分享系数），消除报告两处"分享"数量级打架
  const distFactorAgg = composite.distributionScore / 100
  const sharesP = runs.map((r) => Math.round(r.finalUsers * distFactorAgg * SIM.shareRate)).sort((a, b) => a - b)
  // 口碑：以留存为主，辅以产品质量与低风险（原实现直接等于留存率×100，语义过窄）
  const repP = runs.map((r) => clamp(r.retentionRate * 60 + composite.productScore * 0.25 + composite.riskScore * 0.15, 0, 100)).sort((a, b) => a - b)

  const forecast: ForecastMetrics = {
    exposure: { p10: Math.round(quantile(expP, 0.1)), p50: Math.round(quantile(expP, 0.5)), p90: Math.round(quantile(expP, 0.9)) },
    users: { p10: Math.round(usersP10), p50: Math.round(medianUsers), p90: Math.round(usersP90) },
    activeUsers: { p10: Math.round(quantile(activeP, 0.1)), p50: Math.round(quantile(activeP, 0.5)), p90: Math.round(quantile(activeP, 0.9)) },
    retention: { p10: Math.round(quantile(retP, 0.1) * 100), p50: Math.round(quantile(retP, 0.5) * 100), p90: Math.round(quantile(retP, 0.9) * 100) },
    shares: { p10: Math.round(quantile(sharesP, 0.1)), p50: Math.round(quantile(sharesP, 0.5)), p90: Math.round(quantile(sharesP, 0.9)) },
    revenue: { p10: Math.round(quantile(revP, 0.1)), p50: Math.round(quantile(revP, 0.5)), p90: Math.round(quantile(revP, 0.9)) },
    reputation: { p10: Math.round(quantile(repP, 0.1)), p50: Math.round(quantile(repP, 0.5)), p90: Math.round(quantile(repP, 0.9)) },
    growthInflectionDays: Math.round(30 + (1 - composite.retentionScore / 100) * 60),
    shareSpreadCoefficient: clamp(composite.distributionScore / 35, 0.5, 8),
  }

  // 均值路径：由流式聚合器给出（v2 的全量二次扫描已移除）
  const avgPath: PathDataPoint[] = agg.meanPath()

  // Risk analysis（校准版：基于案例库洞察）
  const riskAnalysis: RiskAnalysis = {
    topFailureReason: txt.riskTopFailure(composite),
    mostLikelyCrashTime: outcomeProbabilities.dead > 0.5 ? txt.crashPhases.p1 :
      outcomeProbabilities.dead > 0.3 ? txt.crashPhases.p2 :
      outcomeProbabilities.lowAlive > 0.3 ? txt.crashPhases.p3 : txt.crashPhases.p4,
    mostVulnerableVariable: txt.riskVulnerable(composite),
    negativeEventTriggerProb: clamp(0.05 + (1 - composite.riskScore / 100) * 0.15, 0, 0.5),
    competitorShockProb: clamp(0.1 + (1 - composite.marketScore / 100) * 0.2, 0, 0.6),
    platformDependencyRisk: clamp(scores.market.platformDependency / 100, 0, 1),
    updateInterruptionRisk: clamp((100 - scores.retention.updateVelocity) / 100, 0, 1),
    technicalDebtDragRisk: clamp(scores.risk.technicalDebt / 100, 0, 1),
  }

  // Sensitivity analysis（专业区+；分批异步：长任务中让出事件循环以响应取消，并上报真实阶段）
  onStage?.('sensitivity')
  const sensitivity = tier.sensitivity ? await computeSensitivity(scores, config, shouldCancel) : []

  // Strategy comparison（专业区+；分批异步：同上）
  onStage?.('strategies')
  const strategyRaw: StrategyResult[] = tier.strategies ? await simulateStrategies(scores, config, shouldCancel) : []
  // 策略展示名按结果语言本地化（内部计算用 key，label 仅供展示）
  const strategyLabels = getLabels(locale).strategy
  const strategyComparison: StrategyResult[] = strategyRaw.map((s) => ({
    ...s,
    label: strategyLabels[s.strategy] ?? s.label,
  }))
  onStage?.('report')

  // 优化建议：按敏感性动态排序（非固定痛点/清晰度顺序）
  const optimizationSuggestions = buildDynamicOptimizationSuggestions(
    sensitivity,
    ranking,
    outcomeProbabilities,
  )

  // Warning indicators（四语文案来自 insight-texts）
  const warningIndicators: WarningIndicator[] = txt.warningIndicators.map((w) => ({ ...w }))

  // Core judgment
  const mostLikelyOutcome = txt.pickOutcome(outcomeProbabilities)

  const coreJudgment = {
    mostLikelyOutcome,
    biggestOpportunity: composite.painScore > composite.distributionScore
      ? (locale === 'zh-CN' ? '痛点强，有长期复利潜力，需强化留存和分发' : locale === 'ja-JP' ? 'ペイン強・長期複利の余地、リテンションと配信を強化' : locale === 'ko-KR' ? '페인 강함·장기 복리 잠재, 리텐션·유통 강화' : 'Strong pain; compound potential—boost retention & distribution')
      : (locale === 'zh-CN' ? '分发有优势，需强化产品价值和留存' : locale === 'ja-JP' ? '配信に優位、プロダクト価値とリテンションを強化' : locale === 'ko-KR' ? '유통 우위, 제품 가치·리텐션 강화' : 'Distribution edge—strengthen value & retention'),
    biggestRisk: riskAnalysis.topFailureReason,
    worthInvesting: outcomeProbabilities.dead < 0.5 && composite.overall > 35,
    topOptimizationDirection: composite.retentionScore < composite.distributionScore ? txt.dims.retention :
      composite.painScore < 50 ? txt.dims.pain : txt.dims.distribution,
  }

  const confidence = computeConfidence(scores, config.runs, profile)
  const dataCompleteness = computeDataCompleteness(scores, profile)

  const fullInsight = buildProductInsightReport({
    scores,
    composite,
    outcomeProbabilities,
    ranking,
    riskAnalysis,
    sensitivity,
    strategyComparison,
    optimizationSuggestions,
    coreJudgment,
    confidence,
    profile,
    locale,
  })
  // 基础区输出摘要版诊断（判决 + 首要死因），完整改进方案留给专业区+
  const productInsight = tier.insightLevel === 'summary' ? trimInsightToSummary(fullInsight) : fullInsight

  // 用诊断结果覆盖通用失败/成功路径，并同步首要死亡原因
  const failurePaths = insightToFailurePaths(productInsight.deathReasons)
  const successPaths = insightToSuccessPaths(productInsight.successOpportunities)
  riskAnalysis.topFailureReason = productInsight.deathReasons[0]?.title ?? riskAnalysis.topFailureReason
  coreJudgment.biggestRisk = riskAnalysis.topFailureReason

  // ---- v3 增强分析块（按付费区裁剪输出）----
  const advanced: AdvancedAnalytics = {
    tier: tier.tier,
    deathProbCI: wilsonCI(op.dead, n),
  }
  if (tier.pathBands) advanced.pathBands = agg.bands()
  if (tier.milestones) advanced.milestones = computeMilestones(runs)
  if (tier.survival) advanced.survival = computeSurvival(runs, agg.sampleDays(), config.periodDays)
  if (tier.scenarioBreakdown) advanced.scenarioBreakdown = computeScenarioBreakdown(runs)
  if (tier.ltvAndExtremes) {
    advanced.ltvPerUser = computeLtvPerUser(runs)
    advanced.extremePaths = agg.extremePaths()
  }

  return {
    id: 'result_' + Date.now(),
    artifactId: profile?.id ?? '',
    config,
    outcomeProbabilities,
    ranking,
    forecast,
    pathData: avgPath,
    riskAnalysis,
    sensitivity,
    strategyComparison,
    failurePaths,
    successPaths,
    warningIndicators,
    optimizationSuggestions,
    productInsight,
    advanced,
    coreJudgment,
    confidence,
    dataCompleteness,
    createdAt: new Date().toISOString(),
    // 记录叙事生成语言：切换界面语言时据此判断是否需重建报告文本
    locale,
  }
}

// ---- Message handler ----

interface WorkerMessage {
  type: 'start' | 'cancel'
  scores?: ScoreProfile
  config?: SimulationConfig
  strategyBoosts?: Record<string, number>
  profile?: ArtifactProfile | null
  locale?: Locale
}

let cancelled = false

async function handleWorkerMessage(e: MessageEvent<WorkerMessage>) {
  const msg = e.data

  if (msg.type === 'cancel') {
    cancelled = true
    workerLog('info', 'simulation', 'Simulation cancelled by user')
    return
  }

  if (msg.type === 'start' && msg.scores && msg.config) {
    cancelled = false
    const { scores, config, strategyBoosts = {}, profile = null, locale = 'zh-CN' } = msg

    workerLog('info', 'simulation', `Simulation starting: ${config.runs} runs, ${config.periodDays} days, mode=${config.mode}`, {
      runs: config.runs,
      periodDays: config.periodDays,
      mode: config.mode,
      scenarios: config.scenarios,
      strategies: config.strategies,
      seed: config.seed,
      hasProfile: !!profile,
    })

    // 大规模模拟走多 Worker 并行分片（固定分片布局保证同 seed 可复现）
    const canParallel = typeof Worker !== 'undefined' && config.runs >= PARALLEL_MIN_RUNS
    const engine = canParallel ? runSimulationParallel : runSimulation
    const startTime = Date.now()
    const { runs, aggregator } = await engine(scores, config, strategyBoosts, (completed, partial) => {
      // 真实中间统计：基于已完成样本，仅 O(m) 计数、不排序，避免拖慢模拟
      const m = partial.length || 1
      let dead = 0, blockbuster = 0, strong = 0
      for (const r of partial) {
        if (r.outcomeClass === 'dead') dead++
        if (r.outcomeClass === 'blockbuster') blockbuster++
        if (r.outcomeClass === 'clear_success' || r.outcomeClass === 'blockbuster' || r.outcomeClass === 'long_compound') strong++
      }
      self.postMessage({
        type: 'progress',
        completed,
        total: config.runs,
        // 并行模式下分片归并前 partial 为空，此时不发实时统计（避免显示全 0）
        stats: partial.length > 0 ? { deathProb: dead / m, blockbusterProb: blockbuster / m, successProb: strong / m } : undefined,
      })
    })

    if (cancelled) {
      workerLog('info', 'simulation', 'Simulation was cancelled')
      return
    }

    // 直接用内部聚合器：透传阶段回调（真实进度）与取消检查（敏感性/策略分批期间可中断）
    const result = await aggregateResults(
      runs, config, scores, strategyBoosts, profile, locale,
      (stage) => self.postMessage({ type: 'stage', stage }),
      () => cancelled,
      aggregator,
    )
    if (!cancelled) {
      const duration = Date.now() - startTime
      workerLog('info', 'simulation', `Simulation completed: ${duration}ms`, {
        duration,
        totalRuns: config.runs,
        deadProb: result.outcomeProbabilities.dead.toFixed(3),
        successProb: (result.outcomeProbabilities.clearSuccess + result.outcomeProbabilities.blockbuster).toFixed(3),
      })
      self.postMessage({ type: 'done', result })
    }
  }
}

// 仅在 Web Worker 环境注册消息处理；这样 Node / 测试 / 回测可安全 import 上面的纯函数
if (typeof self !== 'undefined' && typeof (self as { postMessage?: unknown }).postMessage === 'function') {
  self.onmessage = handleWorkerMessage
}
