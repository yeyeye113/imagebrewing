// ============================================================
// Future Simulation Engine — Type Definitions
// ============================================================

/** 作品类型 */
export type ArtifactType =
  | 'software'
  | 'app'
  | 'game'
  | 'website'
  | 'video'
  | 'article'
  | 'community'
  | 'ai_agent'
  | 'business_idea'
  | 'open_source'

/** 项目阶段 */
export type ProjectStage =
  | 'idea'
  | 'prototype'
  | 'demo'
  | 'mvp'
  | 'launched'
  | 'growth'
  | 'stagnant'
  | 'decline'

/** 模拟模式（quick/standard/deep/ultra 一一对应 基础/专业/旗舰/机构级 付费区） */
export type SimMode = 'quick' | 'standard' | 'deep' | 'ultra'

/** 时间粒度 */
export type TimeGranularity = 'day' | 'week' | 'month'

/** 模拟场景 */
export type SimScenario =
  | 'baseline'
  | 'optimistic'
  | 'pessimistic'
  | 'black_swan'
  | 'long_compound'
  | 'competitor_shock'
  | 'platform_boost'
  | 'negative_event'

/** 策略类型 */
export type StrategyType =
  | 'original'
  | 'clarity_boost'
  | 'distribution_boost'
  | 'retention_boost'
  | 'monetization_boost'
  | 'quality_boost'
  | 'community_boost'

/** 结果分类 */
export type OutcomeClass =
  | 'dead'
  | 'low_alive'
  | 'niche_success'
  | 'moderate_success'
  | 'clear_success'
  | 'blockbuster'
  | 'long_compound'

/** 作品本体变量 */
export interface ArtifactScores {
  quality: number
  originality: number
  clarity: number
  usability: number
  emotionalHook: number
  differentiation: number
  completeness: number
  reliability: number
  aestheticQuality: number
  problemSolutionFit: number
}

/** 市场变量 */
export interface MarketScores {
  marketSize: number
  audiencePain: number
  willingnessToPay: number
  trendFit: number
  timingScore: number
  competitionIntensity: number
  substitutionRisk: number
  platformDependency: number
  regulatoryRisk: number
  categoryGrowth: number
}

/** 传播变量 */
export interface DistributionScores {
  shareability: number
  viralityPotential: number
  storyValue: number
  socialProofPotential: number
  creatorReputation: number
  distributionPower: number
  communityPotential: number
  mediaFriendliness: number
  recommendationFit: number
  visualSpreadPower: number
}

/** 留存变量 */
export interface RetentionScores {
  activationRatePotential: number
  firstSessionValue: number
  retentionPotential: number
  habitPotential: number
  networkEffect: number
  switchingCost: number
  longTermValue: number
  updateVelocity: number
  feedbackLoopStrength: number
  communityLockIn: number
}

/** 商业变量 */
export interface BusinessScores {
  monetizationFit: number
  pricingPower: number
  arpuPotential: number
  conversionPotential: number
  upsellPotential: number
  enterprisePotential: number
  lowCostDistribution: number
  grossMarginPotential: number
  lifecycleValue: number
  revenueDiversity: number
}

/** 风险变量 */
export interface RiskScores {
  executionRisk: number
  technicalDebt: number
  churnRisk: number
  negativeFeedbackRisk: number
  copycatRisk: number
  scalabilityRisk: number
  maintenanceBurden: number
  legalRisk: number
  platformBanRisk: number
  founderDependency: number
}

/** 完整评分配置 */
export interface ScoreProfile {
  artifact: ArtifactScores
  market: MarketScores
  distribution: DistributionScores
  retention: RetentionScores
  business: BusinessScores
  risk: RiskScores
}

/** 当前已有数据 */
export interface ExistingData {
  exposure: number
  visitors: number
  users: number
  activeUsers: number
  revenue: number
  day1Retention: number
  day7Retention: number
  day30Retention: number
  shares: number
  comments: number
  saves: number
  rating: number
}

/** 作品信息 */
export interface ArtifactProfile {
  id: string
  name: string
  type: ArtifactType
  stage: ProjectStage
  description: string
  targetUsers: string
  coreFeatures: string[]
  coreSellingPoints: string[]
  competitors: string[]
  channelResources: string
  budget: string
  teamSize: number
  updateFrequency: string
  creatorInfluence: string
  existingData: ExistingData
  createdAt: string
  updatedAt: string
}

/** 模拟配置 */
export interface SimulationConfig {
  runs: number
  periodDays: number
  granularity: TimeGranularity
  mode: SimMode
  scenarios: SimScenario[]
  strategies: StrategyType[]
  /** 可选随机种子：设定后"同输入 → 同结果"可复现，用于回归对比/复跑校验；留空则非确定性 */
  seed?: number
}

/** 结果概率 */
export interface OutcomeProbabilities {
  dead: number
  lowAlive: number
  nicheSuccess: number
  moderateSuccess: number
  clearSuccess: number
  blockbuster: number
  longCompound: number
}

/** 排名统计 */
export interface RankingStats {
  aboveMedian: number
  top30: number
  top20: number
  top10: number
  top5: number
  top1: number
  expectedPercentile: number
  medianPercentile: number
  worst5Percentile: number
  best5Percentile: number
  hasBenchmarkData: boolean
}

/** 关键指标 */
export interface ForecastMetrics {
  exposure: { p10: number; p50: number; p90: number }
  users: { p10: number; p50: number; p90: number }
  activeUsers: { p10: number; p50: number; p90: number }
  retention: { p10: number; p50: number; p90: number }
  shares: { p10: number; p50: number; p90: number }
  revenue: { p10: number; p50: number; p90: number }
  reputation: { p10: number; p50: number; p90: number }
  growthInflectionDays: number
  shareSpreadCoefficient: number
}

/** 路径数据点 */
export interface PathDataPoint {
  day: number
  users: number
  activeUsers: number
  revenue: number
  exposure: number
  shares: number
}

/** 风险分析 */
export interface RiskAnalysis {
  topFailureReason: string
  mostLikelyCrashTime: string
  mostVulnerableVariable: string
  negativeEventTriggerProb: number
  competitorShockProb: number
  platformDependencyRisk: number
  updateInterruptionRisk: number
  technicalDebtDragRisk: number
}

/** 敏感性分析结果 */
export interface SensitivityResult {
  variable: string
  originalValue: number
  top10AfterIncrease: number
  top10AfterDecrease: number
  deathProbAfterIncrease: number
  deathProbAfterDecrease: number
  impactStrength: number
  optimizationPriority: number
}

/** 策略对比结果 */
export interface StrategyResult {
  strategy: StrategyType
  label: string
  deathProb: number
  top10Prob: number
  blockbusterProb: number
  medianUsers: number
  medianRevenue: number
  recommendationLevel: number
}

/** 路径分析（失败路径用 earlySignals/solution，成功路径用 keyVariables/howToImprove，故均为可选）*/
export interface PathAnalysis {
  name: string
  triggerCondition: string
  probability: number
  earlySignals?: string
  solution?: string
  keyVariables?: string
  howToImprove?: string
}

/** 预警指标 */
export interface WarningIndicator {
  metric: string
  healthyThreshold: string
  dangerThreshold: string
  description: string
}

/** 优化建议 */
export interface OptimizationSuggestion {
  priority: number
  title: string
  whyImportant: string
  impactOnSuccess: string
  impactOnFailure: string
  whatToChange: string
  howToVerify: string
  metricToWatch: string
}

/** 产品诊断报告（死亡原因 / 改进方案 / 策略推荐） */
export interface DeathReason {
  id: string
  title: string
  relevance: number
  severity: 'critical' | 'high' | 'medium'
  rootCause: string
  scoreEvidence: string[]
  earlySignals: string[]
  preventionActions: string[]
}

export interface ImprovementAction {
  rank: number
  title: string
  category: string
  urgency: 'immediate' | 'short_term' | 'long_term'
  whyNow: string
  concreteSteps: string[]
  expectedImpact: string
  metricsToWatch: string[]
  effort: 'low' | 'medium' | 'high'
}

export interface OptimizationStrategyPick {
  strategy: StrategyType
  label: string
  recommendationLevel: number
  rank: number
  whyRecommended: string
  deathProb: number
  top10Prob: number
  blockbusterProb: number
  medianUsers: number
  actionItems: string[]
  bestFor: string
}

/** 增长机会（与死亡原因对称） */
export interface SuccessOpportunity {
  id: string
  title: string
  probability: number
  triggerCondition: string
  keyActions: string[]
  metricsToWatch: string[]
}

/** 分阶段行动路线图 */
export interface ActionRoadmapPhase {
  phase: string
  timeframe: string
  goals: string[]
  tasks: string[]
}

export interface ProductInsightReport {
  diagnosisSummary: string
  artifactContext: {
    type: string
    typeLabel: string
    stage: string
    stageLabel: string
  }
  verdict: {
    publishReady: boolean
    headline: string
    mostLikelyOutcome: string
    deathProb: number
    successProb: number
    confidenceNote: string
  }
  scoreDiagnosis: {
    strengths: string[]
    weaknesses: string[]
    structuralRisks: string[]
  }
  deathReasons: DeathReason[]
  successOpportunities: SuccessOpportunity[]
  improvementPlan: ImprovementAction[]
  optimizationStrategies: OptimizationStrategyPick[]
  actionRoadmap: ActionRoadmapPhase[]
}

// ============================================================
// v3 增强分析（按付费区解锁）
// ============================================================

/** 付费能力分区：基础区(quick) / 专业区(standard) / 旗舰区(deep) / 机构级(ultra) */
export type SimTierId = 'basic' | 'pro' | 'flagship' | 'institutional'

/** 分位路径带数据点：跨全部世界线的同日分位数 */
export interface PathBandPoint {
  day: number
  p10: number
  p25: number
  p50: number
  p75: number
  p90: number
  /** 累计收入中位与高位 */
  revenueP50: number
  revenueP90: number
}

/** 里程碑达成统计 */
export interface MilestoneStat {
  kind: 'users' | 'revenue'
  threshold: number
  /** 模拟周期内达成的世界线比例 */
  reachProbability: number
  /** 达成世界线的中位达成天数（无人达成为 null） */
  medianDay: number | null
}

/** 生存分析：死亡世界线的崩盘时间分布 */
export interface SurvivalAnalysis {
  /** 存活率曲线（未崩盘世界线比例随时间） */
  curve: { day: number; alive: number }[]
  /** 死亡世界线的中位崩盘日（无死亡为 null） */
  medianCrashDay: number | null
  /** 各阶段崩盘概率（相对全部世界线） */
  crashProbByPhase: { phase: string; prob: number }[]
}

/** 单场景结果分解 */
export interface ScenarioStat {
  scenario: SimScenario
  runs: number
  deathProb: number
  /** 明显成功 + 爆款 + 长期复利 */
  successProb: number
  medianUsers: number
}

/** v3 增强分析块：旧结果无此字段；内部字段按产出时的付费区裁剪 */
export interface AdvancedAnalytics {
  tier: SimTierId
  /** 死亡概率 Wilson 95% 置信区间（模拟次数越多越窄） */
  deathProbCI: { low: number; high: number }
  /** 专业区+：分位路径带 */
  pathBands?: PathBandPoint[]
  /** 专业区+：里程碑达成概率 */
  milestones?: MilestoneStat[]
  /** 旗舰区：生存分析 */
  survival?: SurvivalAnalysis
  /** 旗舰区：场景分解 */
  scenarioBreakdown?: ScenarioStat[]
  /** 旗舰区：期内单用户累计价值（LTV 近似） */
  ltvPerUser?: { p50: number; p90: number }
  /** 旗舰区：最佳 / 最差代表世界线路径 */
  extremePaths?: { best: PathDataPoint[]; worst: PathDataPoint[] }
}

/** 模拟结果 */
export interface SimulationResult {
  id: string
  artifactId: string
  config: SimulationConfig
  outcomeProbabilities: OutcomeProbabilities
  ranking: RankingStats
  forecast: ForecastMetrics
  pathData: PathDataPoint[]
  riskAnalysis: RiskAnalysis
  sensitivity: SensitivityResult[]
  strategyComparison: StrategyResult[]
  failurePaths: PathAnalysis[]
  successPaths: PathAnalysis[]
  warningIndicators: WarningIndicator[]
  optimizationSuggestions: OptimizationSuggestion[]
  /** 结构化产品诊断：死亡原因、改进方案、策略推荐（旧结果可能缺失，需重新模拟） */
  productInsight?: ProductInsightReport
  /** v3 增强分析（旧结果缺失；字段按产出档位裁剪） */
  advanced?: AdvancedAnalytics
  coreJudgment: {
    mostLikelyOutcome: string
    biggestOpportunity: string
    biggestRisk: string
    worthInvesting: boolean
    topOptimizationDirection: string
  }
  confidence: number
  dataCompleteness: number
  createdAt: string
  /** 生成报告叙事时的界面语言（旧结果缺失视为 zh-CN）；切语言时据此判断是否需重建叙事 */
  locale?: string
}

/** 模拟进度 */
export interface SimulationProgress {
  stage: 'params' | 'simulating' | 'stats' | 'sensitivity' | 'strategies' | 'report'
  completedRuns: number
  totalRuns: number
  currentStats: {
    deathProb: number
    top10Prob: number
    blockbusterProb: number
    medianUsers: number
  }
}
