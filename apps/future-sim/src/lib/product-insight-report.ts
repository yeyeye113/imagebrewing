// ============================================================
// 产品诊断报告 — 死亡原因 / 改进方案 / 优化策略（面向用户交付）
// ============================================================

import type {
  ScoreProfile,
  OutcomeProbabilities,
  SensitivityResult,
  StrategyResult,
  RiskAnalysis,
  RankingStats,
  ArtifactProfile,
  OptimizationSuggestion,
  DeathReason,
  ImprovementAction,
  OptimizationStrategyPick,
  ProductInsightReport,
  SuccessOpportunity,
  ActionRoadmapPhase,
  PathAnalysis,
  ArtifactType,
} from '../types'
import { ARTIFACT_TYPE_LABELS } from './utils.ts'
import { getLabels, getInsightTexts, type Locale } from './i18n/index.ts'
import { getInsightNarrative, type InsightNarrative } from './i18n/insight-narrative.ts'

interface CompositeLike {
  painScore: number
  retentionScore: number
  distributionScore: number
  clarityScore: number
  marketScore: number
  riskScore: number
  businessScore: number
  productScore: number
  overall: number
}

// 注：策略行动/适用场景文案已迁移至 i18n（getInsightTexts().strategyActions / strategyBestFor），
// 由 buildStrategyPicks 按 locale 取用，此处不再保留单语副本。

/** 按作品类型追加死亡原因话术与专属风险 */
const ARTIFACT_DEATH_EXTRAS: Partial<Record<ArtifactType, Partial<Record<string, string[]>>>> = {
  ai_agent: {
    platform_risk: ['避免纯 API wrapper：建立自有数据飞轮或垂直工作流', '关注上游模型降价/开放带来的商品化'],
    weak_pain: ['对比免费通用 AI：证明「为什么必须用你这个」', '用可量化 ROI（省时/省钱）做付费理由'],
    competition_shock: ['大厂免费版上线前完成细分场景壁垒'],
  },
  open_source: {
    monetization_failure: ['设计开源核心 + 商业版/托管/企业支持', '明确许可证与贡献者协议'],
    platform_risk: ['降低对单一云/API 的硬依赖', '建设可自部署版本'],
  },
  software: {
    retention_collapse: ['嵌入日常工作流（快捷键、导入导出、协作）', '提供迁移工具降低切换成本'],
    distribution_failure: ['深耕垂直行业社区与集成市场（插件/扩展）'],
  },
  app: {
    retention_collapse: ['优化推送策略与本地离线体验', '申请关键系统权限前说明价值'],
    hype_mismatch: ['应用商店评分与留存联动运营，避免买量虚火'],
  },
  community: {
    distribution_failure: ['冷启动：邀请 20 位种子 KOL 共建话题', '设计发帖/回复的正反馈回路'],
    retention_collapse: ['建立版主体系与内容节奏（每日话题/周报）'],
  },
  business_idea: {
    weak_pain: ['先做烟雾测试/预售/等候名单，再投入研发', '用 LOI（意向书）验证付费意愿'],
  },
  game: {
    retention_collapse: ['核心循环 3 分钟内可体验完整乐趣', '赛季/社交绑定提升回访'],
    monetization_failure: ['验证 ARPDAU 与付费点是否破坏核心体验'],
  },
  website: {
    distribution_failure: ['SEO 长尾词矩阵 + 结构化内容更新', '与其他站点互换推荐位'],
  },
}

function applyArtifactDeathOverlays(
  reasons: DeathReason[],
  artifactType?: ArtifactType,
  typeLabels?: Record<string, string>,
  typicalRiskFmt?: (label: string) => string,
): DeathReason[] {
  if (!artifactType) return reasons
  const extras = ARTIFACT_DEATH_EXTRAS[artifactType]
  if (!extras) return reasons
  const maps = typeLabels ?? ARTIFACT_TYPE_LABELS
  const fmt = typicalRiskFmt ?? ((l) => `（${l} 典型风险）`)

  return reasons.map((r) => {
    const add = extras[r.id]
    if (!add?.length) return r
    return {
      ...r,
      preventionActions: [...r.preventionActions, ...add],
      rootCause: r.rootCause + fmt(maps[artifactType] ?? artifactType),
    }
  })
}

function appendAiCommoditization(
  reasons: DeathReason[],
  scores: ScoreProfile,
  artifactType?: ArtifactType,
  op?: OutcomeProbabilities,
  locale: Locale = 'zh-CN',
): DeathReason[] {
  if (artifactType !== 'ai_agent' && scores.market.platformDependency < 65) return reasons
  if (artifactType !== 'ai_agent' && scores.risk.copycatRisk < 70) return reasons
  if (reasons.some((r) => r.id === 'api_commoditization')) return reasons

  const n = getInsightNarrative(locale)
  const deathCluster = (op?.dead ?? 0.3) + (op?.lowAlive ?? 0) * 0.3
  reasons.push({
    id: 'api_commoditization',
    title: n.aiCommoditization.title,
    relevance: clamp((scores.market.platformDependency / 100) * (0.5 + deathCluster), 0.15, 0.85),
    severity: scores.market.platformDependency >= 75 ? 'critical' : 'high',
    rootCause: n.aiCommoditization.rootCause,
    scoreEvidence: [
      n.platformScore(scores.market.platformDependency, scores.risk.platformBanRisk),
      `${locale === 'zh-CN' ? '被复制风险' : locale === 'ja-JP' ? '模倣リスク' : locale === 'ko-KR' ? '모방 리스크' : 'Copy risk'} ${scores.risk.copycatRisk}/100`,
    ],
    earlySignals: n.aiCommoditization.earlySignals,
    preventionActions: n.aiCommoditization.preventionActions,
  })
  return reasons.sort((a, b) => b.relevance - a.relevance).slice(0, 6)
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

/** 概率展示软化：极低但语义上"接近零"的概率显示为 <1%，避免叙事里出现
    「可以放心发布」与「成功概率 0.0%」同屏自相矛盾的观感 */
function pctSoft(n: number): string {
  if (n > 0 && n < 0.01) return '<1%'
  if (n === 0) return '<1%'
  return pct(n)
}

function scoreLabel(v: number): string {
  if (v >= 75) return '强'
  if (v >= 55) return '中'
  if (v >= 35) return '偏弱'
  return '弱'
}

function pickWeakest(
  composite: CompositeLike,
  dims?: { pain: string; clarity: string; retention: string; distribution: string },
): { key: string; score: number; label: string } {
  const d = dims ?? { pain: '痛点强度', clarity: '清晰度', retention: '留存能力', distribution: '分发能力' }
  const items = [
    { key: 'pain', score: composite.painScore, label: d.pain },
    { key: 'clarity', score: composite.clarityScore, label: d.clarity },
    { key: 'retention', score: composite.retentionScore, label: d.retention },
    { key: 'distribution', score: composite.distributionScore, label: d.distribution },
  ]
  items.sort((a, b) => a.score - b.score)
  return items[0]
}

function buildDeathReasons(
  locale: Locale,
  scores: ScoreProfile,
  composite: CompositeLike,
  op: OutcomeProbabilities,
  risk: RiskAnalysis,
  artifactType?: ArtifactType,
  profile?: ArtifactProfile | null,
  scoreLabelFn: (v: number) => string = scoreLabel,
  artifactLabels?: Record<string, string>,
  typicalRiskFmt?: (label: string) => string,
): DeathReason[] {
  const n = getInsightNarrative(locale)
  const reasons: DeathReason[] = []
  const dist = scores.distribution.distributionPower
  const ret = scores.retention.retentionPotential
  const pain = scores.market.audiencePain
  const gap = Math.max(0, dist - ret - 10)
  const deathCluster = op.dead + op.lowAlive * 0.35

  const push = (r: Omit<DeathReason, 'relevance'> & { baseWeight: number }) => {
    const relevance = clamp(r.baseWeight * (0.4 + deathCluster * 0.6), 0.05, 0.98)
    reasons.push({ ...r, relevance })
  }

  if (pain < 45) {
    push({
      id: 'weak_pain',
      title: n.weakPain.title,
      baseWeight: (45 - pain) / 45,
      severity: pain < 30 ? 'critical' : 'high',
      rootCause: n.weakPain.rootCause,
      scoreEvidence: [
        n.painFit(pain, scoreLabelFn(pain), scores.artifact.problemSolutionFit),
        `${locale === 'zh-CN' ? '问题-方案匹配' : locale === 'ja-JP' ? '課題-解決適合' : locale === 'ko-KR' ? '문제-솔루션 적합' : 'Problem-solution fit'} ${scores.artifact.problemSolutionFit}/100`,
      ],
      earlySignals: n.weakPain.earlySignals,
      preventionActions: n.weakPain.preventionActions,
    })
  }

  if (gap >= 20) {
    push({
      id: 'hype_mismatch',
      title: n.hypeMismatch.title,
      baseWeight: gap / 50,
      severity: gap >= 35 ? 'critical' : 'high',
      rootCause: n.hypeMismatch.rootCause,
      scoreEvidence: [n.distVsRet(dist, ret, gap, risk.mostLikelyCrashTime), n.crashWindow(risk.mostLikelyCrashTime)],
      earlySignals: n.hypeMismatch.earlySignals,
      preventionActions: n.hypeMismatch.preventionActions,
    })
  }

  if (ret < 45) {
    push({
      id: 'retention_collapse',
      title: n.retentionCollapse.title,
      baseWeight: (50 - ret) / 50,
      severity: ret < 32 ? 'critical' : 'high',
      rootCause: n.retentionCollapse.rootCause,
      scoreEvidence: [
        n.retentionScore(ret, scores.retention.habitPotential, scores.retention.firstSessionValue),
        `${locale === 'zh-CN' ? '习惯形成' : locale === 'ja-JP' ? '習慣形成' : locale === 'ko-KR' ? '습관 형성' : 'Habit'} ${scores.retention.habitPotential}/100`,
        `${locale === 'zh-CN' ? '首次体验' : locale === 'ja-JP' ? '初回体験' : locale === 'ko-KR' ? '첫 경험' : 'First session'} ${scores.retention.firstSessionValue}/100`,
      ],
      earlySignals: n.retentionCollapse.earlySignals,
      preventionActions: n.retentionCollapse.preventionActions,
    })
  }

  if (dist < 40) {
    push({
      id: 'distribution_failure',
      title: n.distributionFailure.title,
      baseWeight: (45 - dist) / 45,
      severity: dist < 28 ? 'critical' : 'medium',
      rootCause: n.distributionFailure.rootCause,
      scoreEvidence: [
        n.channelScore(dist, scores.distribution.shareability),
        `${locale === 'zh-CN' ? '可分享性' : locale === 'ja-JP' ? '共有可能性' : locale === 'ko-KR' ? '공유성' : 'Shareability'} ${scores.distribution.shareability}/100`,
      ],
      earlySignals: n.distributionFailure.earlySignals,
      preventionActions: n.distributionFailure.preventionActions,
    })
  }

  if (scores.market.competitionIntensity >= 68 || scores.risk.copycatRisk >= 65 || (profile?.competitors?.length ?? 0) >= 2) {
    push({
      id: 'competition_shock',
      title: n.competitionShock.title,
      baseWeight: Math.max((scores.market.competitionIntensity - 55) / 45, (profile?.competitors?.length ?? 0) >= 2 ? 0.45 : 0),
      severity: scores.market.competitionIntensity >= 80 ? 'critical' : 'high',
      rootCause: n.competitionShock.rootCause,
      scoreEvidence: [
        n.competitionScore(scores.market.competitionIntensity, scores.artifact.differentiation, scores.market.substitutionRisk),
        `${locale === 'zh-CN' ? '差异化' : locale === 'ja-JP' ? '差別化' : locale === 'ko-KR' ? '차별화' : 'Differentiation'} ${scores.artifact.differentiation}/100`,
        `${locale === 'zh-CN' ? '替代风险' : locale === 'ja-JP' ? '代替リスク' : locale === 'ko-KR' ? '대체 리스크' : 'Substitution'} ${scores.market.substitutionRisk}/100`,
        ...(profile?.competitors?.length ? [n.knownCompetitors(profile.competitors.slice(0, 4).join(locale === 'zh-CN' ? '、' : ', '))] : []),
      ],
      earlySignals: n.competitionShock.earlySignals,
      preventionActions: n.competitionShock.preventionActions,
    })
  }

  if (scores.market.platformDependency >= 60 || risk.platformDependencyRisk >= 0.55) {
    push({
      id: 'platform_risk',
      title: n.platformRiskBlock.title,
      baseWeight: scores.market.platformDependency / 100,
      severity: scores.market.platformDependency >= 75 ? 'critical' : 'medium',
      rootCause: n.platformRiskBlock.rootCause,
      scoreEvidence: [
        n.platformScore(scores.market.platformDependency, scores.risk.platformBanRisk),
        `${locale === 'zh-CN' ? '封禁风险' : locale === 'ja-JP' ? 'BANリスク' : locale === 'ko-KR' ? '차단 리스크' : 'Ban risk'} ${scores.risk.platformBanRisk}/100`,
      ],
      earlySignals: n.platformRiskBlock.earlySignals,
      preventionActions: n.platformRiskBlock.preventionActions,
    })
  }

  if (composite.businessScore < 45 || scores.business.monetizationFit < 45) {
    push({
      id: 'monetization_failure',
      title: n.monetizationFailure.title,
      baseWeight: 0.35 + op.moderateSuccess * 0.2,
      severity: 'medium',
      rootCause: n.monetizationFailure.rootCause,
      scoreEvidence: [
        n.monetizationScore(scores.business.monetizationFit, scores.market.willingnessToPay),
        `${locale === 'zh-CN' ? '付费意愿' : locale === 'ja-JP' ? '支払意欲' : locale === 'ko-KR' ? '결제 의향' : 'Willingness to pay'} ${scores.market.willingnessToPay}/100`,
      ],
      earlySignals: n.monetizationFailure.earlySignals,
      preventionActions: n.monetizationFailure.preventionActions,
    })
  }

  if (scores.risk.legalRisk >= 50 || scores.market.regulatoryRisk >= 50) {
    push({
      id: 'regulatory',
      title: n.regulatory.title,
      baseWeight: Math.max(scores.risk.legalRisk, scores.market.regulatoryRisk) / 100,
      severity: 'critical',
      rootCause: n.regulatory.rootCause,
      scoreEvidence: [
        n.legalScore(scores.risk.legalRisk, scores.market.regulatoryRisk),
        `${locale === 'zh-CN' ? '政策风险' : locale === 'ja-JP' ? '政策リスク' : locale === 'ko-KR' ? '정책 리스크' : 'Regulatory risk'} ${scores.market.regulatoryRisk}/100`,
      ],
      earlySignals: n.regulatory.earlySignals,
      preventionActions: n.regulatory.preventionActions,
    })
  }

  if (reasons.length === 0) {
    reasons.push({
      id: 'general_competition',
      title: risk.topFailureReason,
      relevance: clamp(op.dead + 0.15, 0.2, 0.75),
      severity: op.dead > 0.4 ? 'high' : 'medium',
      rootCause: n.generalRoot,
      scoreEvidence: [
        n.generalEvidence(risk.mostVulnerableVariable, Math.round(composite.overall)),
        `${locale === 'zh-CN' ? '综合分' : locale === 'ja-JP' ? '総合スコア' : locale === 'ko-KR' ? '종합 점수' : 'Overall'} ${Math.round(composite.overall)}/100`,
      ],
      earlySignals: n.generalEarly,
      preventionActions: n.generalPrevent,
    })
  }

  let result = reasons.sort((a, b) => b.relevance - a.relevance)
  result = appendAiCommoditization(result, scores, artifactType, op, locale)
  result = applyArtifactDeathOverlays(result, artifactType, artifactLabels, typicalRiskFmt)
  return result.slice(0, 6)
}

/** 模板占位符填充：{key} → vars[key] */
function fillTpl(tpl: string, vars: Record<string, string | number>): string {
  return tpl.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''))
}

function buildImprovementPlan(
  sensitivity: SensitivityResult[],
  suggestions: OptimizationSuggestion[],
  weakest: { label: string },
  baselineDeathProb: number,
  narr: InsightNarrative,
  variableNames: Record<string, string>,
): ImprovementAction[] {
  const topSens = [...sensitivity].sort((a, b) => a.optimizationPriority - b.optimizationPriority).slice(0, 5)
  const actions: ImprovementAction[] = []

  for (let i = 0; i < topSens.length; i++) {
    const s = topSens[i]
    const varLabel = variableNames[s.variable] ?? s.variable
    const hint = narr.improveSteps[s.variable] ?? {
      steps: [fillTpl(narr.improveFallbackStep, { variable: varLabel, value: s.originalValue })],
      metrics: narr.improveFallbackMetrics,
      effort: 'medium' as const,
    }
    const sug = suggestions[i] ?? suggestions.find((x) => x.priority === i + 1)
    const deathGainPp = ((baselineDeathProb - s.deathProbAfterIncrease) * 100).toFixed(1)
    const top10GainPp = ((s.top10AfterIncrease - s.top10AfterDecrease) * 100).toFixed(1)

    actions.push({
      rank: i + 1,
      title: sug?.title ?? fillTpl(narr.improveFallbackTitle, { variable: varLabel }),
      category: s.variable,
      urgency: i === 0 ? 'immediate' : i < 3 ? 'short_term' : 'long_term',
      whyNow:
        i === 0
          ? fillTpl(narr.improveWhyNowTop, { label: weakest.label, rank: s.optimizationPriority })
          : fillTpl(narr.improveWhyNowRank, { rank: s.optimizationPriority, impact: (s.impactStrength * 100).toFixed(0) }),
      concreteSteps: sug?.whatToChange ? [sug.whatToChange, ...hint.steps.slice(0, 2)] : hint.steps,
      expectedImpact: fillTpl(narr.improveExpectedImpact, {
        death: (s.deathProbAfterIncrease * 100).toFixed(1),
        base: (baselineDeathProb * 100).toFixed(1),
        dir: Number(deathGainPp) >= 0 ? narr.dirDown : narr.dirUp,
        pp: Math.abs(Number(deathGainPp)),
        topPp: top10GainPp,
      }),
      metricsToWatch: sug?.metricToWatch ? [sug.metricToWatch, ...hint.metrics] : hint.metrics,
      effort: hint.effort,
    })
  }

  return actions
}

function buildStrategyPicks(
  strategies: StrategyResult[],
  composite: CompositeLike,
  txt: ReturnType<typeof getInsightTexts>,
  narr: InsightNarrative,
): OptimizationStrategyPick[] {
  const sorted = [...strategies].sort((a, b) => {
    if (b.recommendationLevel !== a.recommendationLevel) return b.recommendationLevel - a.recommendationLevel
    return a.deathProb - b.deathProb
  })

  const weakest = pickWeakest(composite, txt.dims)

  return sorted.slice(0, 5).map((s, i) => {
    const key = s.strategy
    let why = fillTpl(narr.whyBase, { stars: '⭐'.repeat(s.recommendationLevel), death: pct(s.deathProb), top10: pct(s.top10Prob) })
    if (key === 'clarity_boost' && composite.clarityScore < 60) why += narr.whyClarityWeak
    if (key === 'retention_boost' && composite.retentionScore < composite.distributionScore) why += narr.whyRetentionShort
    if (key === 'distribution_boost' && composite.distributionScore < 50) why += narr.whyNeedAcquisition
    if (key === 'monetization_boost' && composite.businessScore < 50) why += narr.whyNeedMonetization
    if (i === 0) why += fillTpl(narr.whyWeakestDim, { label: weakest.label })

    return {
      strategy: key,
      label: s.label,
      recommendationLevel: s.recommendationLevel,
      rank: i + 1,
      whyRecommended: why,
      deathProb: s.deathProb,
      top10Prob: s.top10Prob,
      blockbusterProb: s.blockbusterProb,
      medianUsers: s.medianUsers,
      actionItems: txt.strategyActions[key] ?? txt.strategyActions.original,
      bestFor: txt.strategyBestFor[key] ?? txt.generic,
    }
  })
}

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v))
}

function buildSuccessOpportunities(
  locale: Locale,
  scores: ScoreProfile,
  composite: CompositeLike,
  op: OutcomeProbabilities,
): SuccessOpportunity[] {
  const n = getInsightNarrative(locale)
  const ops: SuccessOpportunity[] = []
  const pushFrom = (id: keyof typeof n.successOpportunities, probability: number) => {
    const t = n.successOpportunities[id]
    ops.push({
      id,
      title: t.title,
      probability,
      triggerCondition: t.trigger,
      keyActions: t.actions,
      metricsToWatch: t.metrics,
    })
  }

  if (op.longCompound > 0.08 || composite.retentionScore >= 65) pushFrom('compound_growth', op.longCompound)
  if (op.nicheSuccess > 0.08 || (composite.painScore >= 60 && composite.distributionScore < 60)) pushFrom('niche_breakthrough', op.nicheSuccess)
  if (op.moderateSuccess > 0.1) pushFrom('steady_saas', op.moderateSuccess)
  if (op.blockbuster > 0.05 || (composite.painScore >= 80 && composite.distributionScore >= 75)) pushFrom('viral_breakout', op.blockbuster)
  if (op.clearSuccess > 0.1) pushFrom('clear_scale', op.clearSuccess)

  if (ops.length === 0) pushFrom('survival_pivot', op.lowAlive)

  return ops.sort((a, b) => b.probability - a.probability).slice(0, 5)
}

/** 行动路线图阶段文案（四语；此前硬编码中文导致英/日/韩界面残留中文） */
const ROADMAP_TEXTS: Record<Locale, {
  phases: [string, string, string]
  timeframes: [string, string, string]
  goalsConsolidate: string
  goalsDerisk: string
  goalsShort: string[]
  goalsLong: string[]
}> = {
  'zh-CN': {
    phases: ['第一阶段', '第二阶段', '第三阶段'],
    timeframes: ['0–2 周', '2–8 周', '2–3 个月'],
    goalsConsolidate: '巩固优势、验证增长假设',
    goalsDerisk: '降低死亡风险、验证核心 PMF',
    goalsShort: ['提升留存与转化', '跑通主获客渠道'],
    goalsLong: ['规模化可复制增长', '建立竞争壁垒'],
  },
  'en-US': {
    phases: ['Phase 1', 'Phase 2', 'Phase 3'],
    timeframes: ['0–2 weeks', '2–8 weeks', '2–3 months'],
    goalsConsolidate: 'Consolidate strengths, validate growth hypotheses',
    goalsDerisk: 'Reduce death risk, validate core PMF',
    goalsShort: ['Improve retention & conversion', 'Prove the main acquisition channel'],
    goalsLong: ['Scale repeatable growth', 'Build competitive moats'],
  },
  'ja-JP': {
    phases: ['第1フェーズ', '第2フェーズ', '第3フェーズ'],
    timeframes: ['0–2週', '2–8週', '2–3ヶ月'],
    goalsConsolidate: '強みを固め、成長仮説を検証',
    goalsDerisk: '死亡リスクを下げ、コアPMFを検証',
    goalsShort: ['リテンションと転換を改善', '主要獲得チャネルを確立'],
    goalsLong: ['再現可能な成長をスケール', '競争優位を構築'],
  },
  'ko-KR': {
    phases: ['1단계', '2단계', '3단계'],
    timeframes: ['0–2주', '2–8주', '2–3개월'],
    goalsConsolidate: '강점 강화·성장 가설 검증',
    goalsDerisk: '사망 리스크 감소·핵심 PMF 검증',
    goalsShort: ['리텐션·전환 개선', '주요 획득 채널 확보'],
    goalsLong: ['반복 가능한 성장 확장', '경쟁 우위 구축'],
  },
}

function buildActionRoadmap(
  plan: ImprovementAction[],
  verdict: ProductInsightReport['verdict'],
  locale: Locale = 'zh-CN',
): ActionRoadmapPhase[] {
  const t = ROADMAP_TEXTS[locale] ?? ROADMAP_TEXTS['zh-CN']
  const immediate = plan.filter((p) => p.urgency === 'immediate')
  const short = plan.filter((p) => p.urgency === 'short_term')
  const long = plan.filter((p) => p.urgency === 'long_term')

  const phases: ActionRoadmapPhase[] = []

  if (immediate.length > 0) {
    phases.push({
      phase: t.phases[0],
      timeframe: t.timeframes[0],
      goals: verdict.publishReady ? [t.goalsConsolidate] : [t.goalsDerisk],
      tasks: immediate.flatMap((p) => p.concreteSteps.slice(0, 2)),
    })
  }
  if (short.length > 0) {
    phases.push({
      phase: t.phases[1],
      timeframe: t.timeframes[1],
      goals: t.goalsShort,
      tasks: short.flatMap((p) => p.concreteSteps.slice(0, 2)),
    })
  }
  if (long.length > 0) {
    phases.push({
      phase: t.phases[2],
      timeframe: t.timeframes[2],
      goals: t.goalsLong,
      tasks: long.flatMap((p) => p.concreteSteps.slice(0, 2)),
    })
  }

  return phases
}

/** 将诊断死亡原因转为报告用失败路径 */
export function insightToFailurePaths(deathReasons: DeathReason[]): PathAnalysis[] {
  return deathReasons.map((d) => ({
    name: d.title,
    triggerCondition: d.rootCause,
    probability: d.relevance,
    earlySignals: d.earlySignals.join('；'),
    solution: d.preventionActions.join('；'),
  }))
}

/** 将增长机会转为报告用成功路径 */
export function insightToSuccessPaths(opportunities: SuccessOpportunity[]): PathAnalysis[] {
  return opportunities.map((o) => ({
    name: o.title,
    triggerCondition: o.triggerCondition,
    probability: o.probability,
    keyVariables: o.id,
    howToImprove: o.keyActions.join('；'),
  }))
}

export function buildProductInsightReport(input: {
  scores: ScoreProfile
  composite: CompositeLike
  outcomeProbabilities: OutcomeProbabilities
  ranking: RankingStats
  riskAnalysis: RiskAnalysis
  sensitivity: SensitivityResult[]
  strategyComparison: StrategyResult[]
  optimizationSuggestions: OptimizationSuggestion[]
  coreJudgment: {
    mostLikelyOutcome: string
    worthInvesting: boolean
    biggestRisk: string
    topOptimizationDirection: string
  }
  confidence: number
  profile?: ArtifactProfile | null
  locale?: Locale
}): ProductInsightReport {
  const locale = input.locale ?? 'zh-CN'
  const txt = getInsightTexts(locale)
  const labelMaps = getLabels(locale)
  const narr = getInsightNarrative(locale)
  const {
    scores, composite, outcomeProbabilities: op, riskAnalysis, sensitivity,
    strategyComparison, optimizationSuggestions, coreJudgment, confidence, profile,
  } = input

  const weakest = pickWeakest(composite, txt.dims)
  const successProb = op.clearSuccess + op.blockbuster + op.longCompound + op.moderateSuccess * 0.5
  const artifactType = profile?.type
  const deathReasons = buildDeathReasons(
    locale,
    scores, composite, op, riskAnalysis, artifactType, profile,
    txt.scoreLabel, labelMaps.artifactType, txt.artifactTypicalRisk,
  )
  const improvementPlan = buildImprovementPlan(sensitivity, optimizationSuggestions, weakest, op.dead, narr, labelMaps.variableNames)
  const optimizationStrategies = buildStrategyPicks(strategyComparison, composite, txt, narr)
  const successOpportunities = buildSuccessOpportunities(locale, scores, composite, op)

  const strengths: string[] = []
  const weaknesses: string[] = []
  const structuralRisks: string[] = []

  if (composite.painScore >= 65) strengths.push(narr.painScore(Math.round(composite.painScore)))
  else weaknesses.push(narr.painWeak(Math.round(composite.painScore)))
  if (composite.retentionScore >= 60) strengths.push(narr.retentionGood(Math.round(composite.retentionScore)))
  else weaknesses.push(narr.retentionWeak(Math.round(composite.retentionScore)))
  if (composite.distributionScore >= 60) strengths.push(narr.distributionGood(Math.round(composite.distributionScore)))
  else weaknesses.push(narr.distributionWeak(Math.round(composite.distributionScore)))
  if (composite.clarityScore >= 65) strengths.push(narr.clarityGood(Math.round(composite.clarityScore)))
  else weaknesses.push(narr.clarityWeak(Math.round(composite.clarityScore)))

  const gap = scores.distribution.distributionPower - scores.retention.retentionPotential
  if (gap >= 20) structuralRisks.push(narr.gapRisk(gap))
  if (scores.market.competitionIntensity >= 70) structuralRisks.push(narr.competitionRisk)
  if (scores.market.platformDependency >= 60) structuralRisks.push(narr.platformRisk)
  if (scores.risk.technicalDebt >= 65) structuralRisks.push(narr.techDebtRisk)

  const publishReady = op.dead < 0.35 && coreJudgment.worthInvesting
  const headline = publishReady
    ? narr.headlinePublish(coreJudgment.mostLikelyOutcome, weakest.label)
    : op.dead >= 0.5
      ? narr.headlineHighDeath(pct(op.dead), deathReasons[0]?.title ?? coreJudgment.biggestRisk)
      : narr.headlineValidate(pct(op.dead), coreJudgment.topOptimizationDirection)

  const productName = profile?.name ? `「${profile.name}」` : txt.productFallback
  const typeLabel = profile ? (labelMaps.artifactType[profile.type] ?? profile.type) : txt.unspecified
  const stageLabel = profile ? (labelMaps.stage[profile.stage] ?? profile.stage) : txt.unspecified
  const stageHint =
    profile?.stage === 'idea' || profile?.stage === 'prototype'
      ? narr.stageHintEarly
      : profile?.stage === 'decline' || profile?.stage === 'stagnant'
        ? narr.stageHintDecline
        : ''

  const diagnosisSummary = narr.diagnosisSummary({
    product: productName,
    type: typeLabel,
    stage: stageLabel,
    benchmark: input.ranking.hasBenchmarkData,
    outcome: coreJudgment.mostLikelyOutcome,
    death: pct(op.dead),
    success: pctSoft(successProb),
    topRisk: deathReasons[0]?.title ?? coreJudgment.biggestRisk,
    optimize: coreJudgment.topOptimizationDirection,
    stageHint,
    lowConf: confidence < 0.5,
    deathValue: op.dead,
  })

  const verdict = {
    publishReady,
    headline,
    mostLikelyOutcome: coreJudgment.mostLikelyOutcome,
    deathProb: op.dead,
    successProb,
    confidenceNote:
      confidence >= 0.7 ? narr.confHigh : confidence >= 0.45 ? narr.confMid : narr.confLow,
  }

  return {
    diagnosisSummary,
    artifactContext: {
      type: profile?.type ?? 'unknown',
      typeLabel,
      stage: profile?.stage ?? 'unknown',
      stageLabel,
    },
    verdict,
    scoreDiagnosis: { strengths, weaknesses, structuralRisks },
    deathReasons,
    successOpportunities,
    improvementPlan,
    optimizationStrategies,
    actionRoadmap: buildActionRoadmap(improvementPlan, verdict, locale),
  }
}

export function formatProductInsightMarkdown(report: ProductInsightReport, locale: Locale = 'zh-CN'): string {
  const narr = getInsightNarrative(locale)
  const s = narr.reportSections
  const lines: string[] = [
    `## ${s.insightSummary}`,
    '',
    report.diagnosisSummary,
    '',
    `> **${report.verdict.headline}**`,
    '',
    `| ${s.decisionTable} | ${locale === 'zh-CN' ? '结论' : locale === 'ja-JP' ? '結論' : locale === 'ko-KR' ? '결론' : 'Conclusion'} |`,
    '|--------|------|',
    `| ${s.publishDecision} | ${report.verdict.publishReady ? narr.publishYes : narr.publishNo} |`,
    `| ${s.mostLikely} | ${report.verdict.mostLikelyOutcome} |`,
    `| ${s.deathProb} | ${pct(report.verdict.deathProb)} |`,
    `| ${s.successProb} | ${pct(report.verdict.successProb)} |`,
    `| ${s.confidenceNote} | ${report.verdict.confidenceNote} |`,
    `| ${s.artifactType} | ${report.artifactContext.typeLabel} |`,
    `| ${s.stage} | ${report.artifactContext.stageLabel} |`,
    '',
    `### ${s.scoreDiag}`,
    '',
    `- **${s.strengths}**：${report.scoreDiagnosis.strengths.join('；') || s.noStrength}`,
    `- **${s.weaknesses}**：${report.scoreDiagnosis.weaknesses.join('；') || s.none}`,
    `- **${s.structuralRisks}**：${report.scoreDiagnosis.structuralRisks.join('；') || s.noStructural}`,
    '',
    `## ${s.deathAnalysis}`,
    '',
  ]

  report.deathReasons.forEach((d, i) => {
    lines.push(
      `### ${i + 1}. ${d.title}（${locale === 'zh-CN' ? '相关度' : locale === 'ja-JP' ? '関連度' : locale === 'ko-KR' ? '관련도' : 'relevance'} ${pct(d.relevance)} · ${s.severity[d.severity]}）`,
      '',
      `**${s.rootCause}**：${d.rootCause}`,
      '',
      `**${s.scoreEvidence}**：`,
      ...d.scoreEvidence.map((e) => `- ${e}`),
      '',
      `**${s.earlySignals}**：`,
      ...d.earlySignals.map((e) => `- ${e}`),
      '',
      `**${s.prevention}**：`,
      ...d.preventionActions.map((e) => `- ${e}`),
      '',
    )
  })

  lines.push(`## ${s.growthOps}`, '')
  report.successOpportunities.forEach((o, i) => {
    lines.push(
      `### ${i + 1}. ${o.title}（${locale === 'zh-CN' ? '概率' : locale === 'ja-JP' ? '確率' : locale === 'ko-KR' ? '확률' : 'prob.'} ${pct(o.probability)}）`,
      '',
      `**${s.trigger}**：${o.triggerCondition}`,
      '',
      `**${s.keyActions}**：`,
      ...o.keyActions.map((a) => `- ${a}`),
      '',
      `**${s.metricsWatch}**：${o.metricsToWatch.join('、')}`,
      '',
    )
  })

  lines.push(`## ${s.roadmap}`, '')
  report.actionRoadmap.forEach((phase) => {
    lines.push(
      `### ${phase.phase}（${phase.timeframe}）`,
      '',
      `**${s.goals}**：${phase.goals.join('；')}`,
      '',
      `**${s.tasks}**：`,
      ...phase.tasks.map((t) => `- ${t}`),
      '',
    )
  })

  lines.push(`## ${s.improvements}`, '')
  report.improvementPlan.forEach((a) => {
    const urg = s.urgency[a.urgency]
    lines.push(
      `### P${a.rank} · ${a.title}（${urg} · ${locale === 'zh-CN' ? '工作量' : 'effort'}${s.effort[a.effort]}）`,
      '',
      `**${s.whyNow}**：${a.whyNow}`,
      '',
      `**${s.expectedImpact}**：${a.expectedImpact}`,
      '',
      `**${s.concreteSteps}**：`,
      ...a.concreteSteps.map((step) => `- ${step}`),
      '',
      `**${s.metricsWatch}**：${a.metricsToWatch.join('、')}`,
      '',
    )
  })

  lines.push(`## ${s.strategyRec}`, '')
  report.optimizationStrategies.forEach((st) => {
    lines.push(
      `### #${st.rank} ${st.label} ${'⭐'.repeat(st.recommendationLevel)}`,
      '',
      `**${s.bestFor}**：${st.bestFor}`,
      '',
      `**${s.whyRecommended}**：${st.whyRecommended}`,
      '',
      `| ${s.deathProb} | Top10% | ${locale === 'zh-CN' ? '爆款概率' : 'Blockbuster'} | ${locale === 'zh-CN' ? '中位用户' : 'Median users'} |`,
      `|----------|--------|----------|----------|`,
      `| ${pct(st.deathProb)} | ${pct(st.top10Prob)} | ${pct(st.blockbusterProb)} | ${st.medianUsers.toLocaleString(locale)} |`,
      '',
      `**${s.execList}**：`,
      ...st.actionItems.map((x) => `- ${x}`),
      '',
    )
  })

  return lines.join('\n')
}
