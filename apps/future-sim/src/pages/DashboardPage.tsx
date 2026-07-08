// ============================================================
// DashboardPage — simulation results dashboard
// ============================================================

import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/store'
import { useLocalizedResult } from '@/hooks/useLocalizedResult'
import { Card, CardHeader, CardContent, Badge, Button, MetricCard, Table, Th, Td, Collapsible } from '@/components/ui'
import { AnimatedNumber, DecodeText, Reveal } from '@/components/fx'
import { formatNumber, formatPercent } from '@/lib/utils'
import { VerdictBanner } from '@/components/VerdictBanner'
import { PageEmpty } from '@/components/PageEmpty'
import { PageShellWide } from '@/components/PageActions'
import { TierBadge, LockedSection } from '@/components/TierGate'
import { useChartTheme } from '@/hooks/useChartTheme'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ComposedChart, Area } from 'recharts'
import { useT } from '@/hooks/useT'
import { useLabels } from '@/hooks/useLabels'
import { FileText, TrendingUp, Skull, ListChecks, Zap, Milestone, HeartPulse, Layers, Coins } from 'lucide-react'
import type { MessageKey } from '@/lib/i18n'

const SECTION_NAV_KEYS = [
  { id: 'verdict', labelKey: 'dash.nav.overview' as const },
  { id: 'diagnosis', labelKey: 'dash.nav.diagnosis' as const },
  { id: 'charts', labelKey: 'dash.nav.charts' as const },
  { id: 'ranking', labelKey: 'dash.nav.ranking' as const },
  { id: 'advanced', labelKey: 'dash.nav.advanced' as const },
] as const

export default function DashboardPage() {
  const { currentProject } = useAppStore()
  // 语言自适应视图：切语言后诊断叙事按新语言重建，避免英文界面残留中文正文
  const result = useLocalizedResult()
  const navigate = useNavigate()
  const tr = useT()
  const labels = useLabels()
  const chart = useChartTheme()

  if (!result || !currentProject) {
    return <PageEmpty kind="no-result" />
  }

  const op = result.outcomeProbabilities
  const r = result.ranking
  const f = result.forecast

  // Outcome distribution data
  const outcomeData = [
    { name: labels.outcome.dead, value: Math.round(op.dead * 100), color: '#EF4444' },
    { name: labels.outcome.low_alive, value: Math.round(op.lowAlive * 100), color: '#F59E0B' },
    { name: labels.outcome.niche_success, value: Math.round(op.nicheSuccess * 100), color: '#10B981' },
    { name: labels.outcome.moderate_success, value: Math.round(op.moderateSuccess * 100), color: '#3B82F6' },
    { name: labels.outcome.clear_success, value: Math.round(op.clearSuccess * 100), color: '#8B5CF6' },
    { name: labels.outcome.blockbuster, value: Math.round(op.blockbuster * 100), color: '#EC4899' },
    { name: labels.outcome.long_compound, value: Math.round(op.longCompound * 100), color: '#06B6D4' },
  ]

  const strategyData = result.strategyComparison.map((s) => ({
    name: labels.strategy[s.strategy] || s.strategy,
    death: Math.round(s.deathProb * 100),
    top10: Math.round(s.top10Prob * 100),
    blockbuster: Math.round(s.blockbusterProb * 100),
    users: s.medianUsers,
  }))

  const insight = result.productInsight

  const tooltipStyle = {
    backgroundColor: chart.tooltipBg,
    border: `1px solid ${chart.tooltipBorder}`,
    borderRadius: 8,
    fontSize: 12,
  }

  // ---- v3 增强分析（按产出档位裁剪；旧结果无 advanced） ----
  const adv = result.advanced
  const bandData = adv?.pathBands?.map((b) => ({
    day: b.day,
    outer: [b.p10, b.p90] as [number, number],
    inner: [b.p25, b.p75] as [number, number],
    p50: b.p50,
  }))
  const extremeData = adv?.extremePaths
    ? adv.extremePaths.best.map((p, i) => ({
        day: p.day,
        best: p.users,
        worst: adv.extremePaths!.worst[i]?.users ?? null,
      }))
    : undefined
  const ciText = adv
    ? tr('dash.ciNote', {
        low: formatPercent(adv.deathProbCI.low),
        high: formatPercent(adv.deathProbCI.high),
      })
    : undefined
  const milestoneLabel = (m: { kind: string; threshold: number }) =>
    m.kind === 'users'
      ? tr('dash.msUsers', { n: formatNumber(m.threshold) })
      : tr('dash.msRevenue', { n: formatNumber(m.threshold) })

  return (
    <PageShellWide>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-gray-100">
            <DecodeText text={tr('dash.title')} />
          </h1>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1 truncate">
            {currentProject.name} · {tr('common.confidence')} {formatPercent(result.confidence)} · {tr('common.completeness')} {formatPercent(result.dataCompleteness)}
          </p>
        </div>
        <div className="flex gap-2 shrink-0 w-full sm:w-auto">
          <Button variant="secondary" className="flex-1 sm:flex-none" onClick={() => navigate('/run')}>{tr('dash.rerun')}</Button>
          <Button className="flex-1 sm:flex-none" onClick={() => navigate('/report')}>
            <FileText className="w-4 h-4 mr-1 sm:mr-2" />
            {tr('dash.fullReport')}
          </Button>
        </div>
      </div>

      {/* 章节锚点导航：玻璃吸顶 + hover 电光描边 */}
      <div className="sticky top-0 z-10 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2 mb-4 bg-gray-50/85 dark:bg-gray-950/80 backdrop-blur-md border-b border-gray-200/80 dark:border-gray-800/80">
        <div className="flex gap-1 overflow-x-auto scrollbar-none">
          {SECTION_NAV_KEYS.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className="shrink-0 px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-white/90 dark:hover:bg-gray-900 rounded-md border border-transparent hover:border-cyan-500/30 dark:hover:border-cyan-400/30 transition-colors"
            >
              {tr(s.labelKey)}
            </a>
          ))}
        </div>
      </div>

      <Reveal>
        <VerdictBanner result={result} />
      </Reveal>

      {adv && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <TierBadge tier={adv.tier} />
        </div>
      )}

      {insight && !adv && (
        <div className="mb-6 rounded-lg border border-indigo-200 dark:border-indigo-900/50 bg-indigo-50 dark:bg-indigo-950/30 px-4 py-3 text-sm text-indigo-800 dark:text-indigo-200">
          {tr('tier.legacyResult')}
        </div>
      )}

      {/* Core Summary：核心概率数字入场时弹簧滚动到位 */}
      <div id="diagnosis" className="scroll-mt-28 grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <MetricCard label={tr('dash.mostLikely')} value={result.coreJudgment.mostLikelyOutcome} />
        <MetricCard
          label={tr('dash.deathProb')}
          value={<AnimatedNumber value={op.dead * 100} format={(n) => `${n.toFixed(1)}%`} />}
          subtext={ciText ?? (op.dead > 0.4 ? tr('dash.riskHigh') : tr('dash.riskLow'))}
        />
        <MetricCard label={tr('dash.top10Prob')} value={<AnimatedNumber value={r.top10 * 100} format={(n) => `${n.toFixed(1)}%`} />} />
        <MetricCard label={tr('dash.blockbusterProb')} value={<AnimatedNumber value={op.blockbuster * 100} format={(n) => `${n.toFixed(1)}%`} />} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <MetricCard label={tr('dash.longCompoundProb')} value={formatPercent(op.longCompound)} />
        <MetricCard label={tr('dash.biggestOpportunity')} value={result.coreJudgment.biggestOpportunity} />
        <MetricCard label={tr('dash.recommendedStrategy')} value={result.coreJudgment.topOptimizationDirection} />
      </div>

      {!insight && (
        <div className="mb-6 rounded-lg border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/30 px-4 py-3 text-sm text-blue-800 dark:text-blue-200">
          {tr('dash.legacyNotice')}
        </div>
      )}

      {result.confidence < 0.45 && (
        <div className="mb-6 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
          {tr('dash.lowConfidence', { confidence: formatPercent(result.confidence) })}
        </div>
      )}

      {insight && (
        <Card className="mb-6 border-gray-900/10">
          <CardHeader>
            <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('dash.diagnosisTitle')}</h2>
            <p className="text-xs text-gray-500 mt-1">{insight.verdict.headline}</p>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{insight.diagnosisSummary}</p>
            <div className="flex flex-wrap gap-2">
              {insight.scoreDiagnosis.strengths.map((s) => (
                <Badge key={s} variant="default">✓ {s}</Badge>
              ))}
              {insight.scoreDiagnosis.weaknesses.map((s) => (
                <Badge key={s} variant="warning">△ {s}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {insight && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <Card>
            <CardHeader>
              <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <Skull className="w-4 h-4 text-red-500" />
                {tr('dash.deathReasonsTop', { n: Math.min(insight.deathReasons.length, 4) })}
              </h2>
            </CardHeader>
            <CardContent className="space-y-4">
              {insight.deathReasons.slice(0, 4).map((d) => (
                <div key={d.id} className="border-l-2 border-red-200 dark:border-red-900/50 pl-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{d.title}</span>
                    <Badge variant={d.severity === 'critical' ? 'danger' : 'warning'}>
                      {formatPercent(d.relevance)}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{d.rootCause}</p>
                  <ul className="text-xs text-gray-500 mt-2 list-disc list-inside">
                    {d.preventionActions.slice(0, 2).map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <ListChecks className="w-4 h-4" />
                {tr('dash.improvementsPriority')}
              </h2>
            </CardHeader>
            <CardContent className="space-y-3">
              {insight.improvementPlan.slice(0, 4).map((a) => (
                <div key={a.rank} className="rounded-lg bg-gray-50 dark:bg-gray-800/50 p-3">
                  <div className="flex items-center gap-2">
                    <Badge variant={a.rank === 1 ? 'danger' : 'default'}>P{a.rank}</Badge>
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{a.title}</span>
                  </div>
                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{a.whyNow}</p>
                  <p className="text-xs text-green-700 dark:text-green-400 mt-1">{a.expectedImpact}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {insight && (
        <Card className="mb-6">
          <CardHeader>
            <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <Zap className="w-4 h-4" />
              {tr('dash.recommendedStrategies')}
            </h2>
          </CardHeader>
          <CardContent>
            <Table>
              <thead>
                <tr>
                  <Th>{tr('dash.colStrategy')}</Th>
                  <Th>{tr('dash.colApplicable')}</Th>
                  <Th className="text-right">{tr('dash.colDeathDown')}</Th>
                  <Th className="text-right">{tr('dash.colTop10Up')}</Th>
                  <Th>{tr('dash.colRecommend')}</Th>
                </tr>
              </thead>
              <tbody>
                {insight.optimizationStrategies.slice(0, 4).map((s) => (
                  <tr key={s.strategy}>
                    <Td className="font-medium">{s.label}</Td>
                    <Td className="text-xs text-gray-500 max-w-[140px]">{s.bestFor}</Td>
                    <Td className="text-right tabular-nums">{formatPercent(s.deathProb)}</Td>
                    <Td className="text-right text-green-600 tabular-nums">{formatPercent(s.top10Prob)}</Td>
                    <Td>{'⭐'.repeat(s.recommendationLevel)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardContent>
        </Card>
      )}

      {insight && insight.actionRoadmap.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-green-600" />
              {tr('dash.roadmap')}
            </h2>
          </CardHeader>
          <CardContent className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {insight.actionRoadmap.map((phase) => (
              <div key={phase.phase} className="rounded-lg border border-gray-100 dark:border-gray-800 p-3">
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400">{phase.phase} · {phase.timeframe}</div>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">{phase.goals.join('；')}</p>
                <ul className="text-xs text-gray-800 dark:text-gray-200 mt-2 space-y-1 list-disc list-inside">
                  {phase.tasks.slice(0, 3).map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {insight && insight.successOpportunities.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              {tr('dash.growthOpportunities')}
            </h2>
          </CardHeader>
          <CardContent className="space-y-3">
            {insight.successOpportunities.slice(0, 3).map((o) => (
              <div key={o.id} className="border-l-2 border-green-300 dark:border-green-800 pl-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{o.title}</span>
                  <Badge variant="default">{formatPercent(o.probability)}</Badge>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{o.triggerCondition}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* v3: 分位路径带（专业区+） */}
      {adv && (
        bandData ? (
          <Card className="mb-6">
            <CardHeader>
              <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('dash.pathBands')}</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tr('dash.pathBandsSubtitle')}</p>
            </CardHeader>
            <CardContent>
              <div className="h-64 sm:h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={bandData}>
                    <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                    <XAxis dataKey="day" tickFormatter={(d) => `D${d}`} tick={{ fill: chart.tick }} />
                    <YAxis tickFormatter={(v) => formatNumber(v)} tick={{ fill: chart.tick }} />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      formatter={(v) => Array.isArray(v) ? v.map((x) => formatNumber(Number(x))).join(' – ') : formatNumber(Number(v))}
                    />
                    <Area dataKey="outer" fill={chart.isDark ? '#1e3a5f' : '#dbeafe'} stroke="none" name={tr('dash.bandOuter')} />
                    <Area dataKey="inner" fill={chart.isDark ? '#1d4ed8' : '#93c5fd'} fillOpacity={0.55} stroke="none" name={tr('dash.bandInner')} />
                    <Line type="monotone" dataKey="p50" stroke={chart.linePrimary} strokeWidth={2} dot={false} name={tr('dash.bandMedian')} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="mb-6">
            <LockedSection requiredTier="pro" title={tr('dash.pathBands')} />
          </div>
        )
      )}

      {/* v3: 里程碑 + 生存分析 */}
      {adv && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {adv.milestones ? (
            <Card>
              <CardHeader>
                <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <Milestone className="w-4 h-4" />
                  {tr('dash.milestones')}
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tr('dash.milestonesSubtitle')}</p>
              </CardHeader>
              <CardContent>
                <Table>
                  <thead>
                    <tr>
                      <Th>{tr('dash.colMilestone')}</Th>
                      <Th className="text-right">{tr('dash.colReachProb')}</Th>
                      <Th className="text-right">{tr('dash.colMedianDay')}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {adv.milestones.map((m) => (
                      <tr key={`${m.kind}_${m.threshold}`}>
                        <Td className="font-medium whitespace-nowrap">{milestoneLabel(m)}</Td>
                        <Td className="text-right tabular-nums">{formatPercent(m.reachProbability)}</Td>
                        <Td className="text-right tabular-nums text-gray-600 dark:text-gray-400 whitespace-nowrap">
                          {m.medianDay !== null ? tr('dash.dayN', { n: m.medianDay }) : tr('dash.notReached')}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </CardContent>
            </Card>
          ) : (
            <LockedSection requiredTier="pro" title={tr('dash.milestones')} />
          )}

          {adv.survival ? (
            <Card>
              <CardHeader>
                <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <HeartPulse className="w-4 h-4 text-red-500" />
                  {tr('dash.survival')}
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {tr('dash.survivalSubtitle')} · {tr('dash.medianCrashDay')}：
                  {adv.survival.medianCrashDay !== null ? tr('dash.dayN', { n: adv.survival.medianCrashDay }) : tr('dash.noCrash')}
                </p>
              </CardHeader>
              <CardContent>
                <div className="h-40 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={adv.survival.curve}>
                      <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                      <XAxis dataKey="day" tickFormatter={(d) => `D${d}`} tick={{ fill: chart.tick }} />
                      <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fill: chart.tick }} />
                      <Tooltip formatter={(v) => formatPercent(Number(v))} contentStyle={tooltipStyle} />
                      <Line type="monotone" dataKey="alive" stroke="#EF4444" strokeWidth={2} dot={false} name={tr('dash.survivalAlive')} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="grid grid-cols-4 gap-2 mt-3">
                  {adv.survival.crashProbByPhase.map((p) => (
                    <div key={p.phase} className="rounded-lg bg-gray-50 dark:bg-gray-800/50 px-2 py-1.5 text-center">
                      <div className="text-[10px] text-gray-500 dark:text-gray-400">{tr(`dash.crashPhase_${p.phase}` as MessageKey)}</div>
                      <div className="text-xs font-medium text-gray-900 dark:text-gray-100 tabular-nums">{formatPercent(p.prob)}</div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : (
            <LockedSection requiredTier="flagship" title={tr('dash.survival')} />
          )}
        </div>
      )}

      {/* v3: 场景分解 + LTV/极端世界线 */}
      {adv && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {adv.scenarioBreakdown ? (
            <Card>
              <CardHeader>
                <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <Layers className="w-4 h-4" />
                  {tr('dash.scenarioBreakdown')}
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tr('dash.scenarioSubtitle')}</p>
              </CardHeader>
              <CardContent>
                <Table>
                  <thead>
                    <tr>
                      <Th>{tr('dash.colScenario')}</Th>
                      <Th className="text-right">{tr('dash.colDeath')}</Th>
                      <Th className="text-right">{tr('dash.colSuccess')}</Th>
                      <Th className="text-right">{tr('dash.colMedianUsers')}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {adv.scenarioBreakdown.map((s) => (
                      <tr key={s.scenario}>
                        <Td className="font-medium">{labels.scenario[s.scenario] ?? s.scenario}</Td>
                        <Td className="text-right tabular-nums text-red-500">{formatPercent(s.deathProb)}</Td>
                        <Td className="text-right tabular-nums text-green-600">{formatPercent(s.successProb)}</Td>
                        <Td className="text-right tabular-nums">{formatNumber(s.medianUsers)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </CardContent>
            </Card>
          ) : (
            <LockedSection requiredTier="flagship" title={tr('dash.scenarioBreakdown')} />
          )}

          {adv.ltvPerUser && extremeData ? (
            <Card>
              <CardHeader>
                <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <Coins className="w-4 h-4 text-amber-500" />
                  {tr('dash.ltv')} & {tr('dash.extremePaths')}
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tr('dash.ltvHint')}</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <MetricCard label={`${tr('dash.ltv')} P50`} value={`¥${adv.ltvPerUser.p50}`} />
                  <MetricCard label={`${tr('dash.ltv')} P90`} value={`¥${adv.ltvPerUser.p90}`} />
                </div>
                <div className="h-36 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={extremeData}>
                      <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                      <XAxis dataKey="day" tickFormatter={(d) => `D${d}`} tick={{ fill: chart.tick }} />
                      <YAxis tickFormatter={(v) => formatNumber(v)} tick={{ fill: chart.tick }} />
                      <Tooltip formatter={(v) => formatNumber(Number(v))} contentStyle={tooltipStyle} />
                      <Line type="monotone" dataKey="best" stroke="#10B981" strokeWidth={1.5} dot={false} name={tr('dash.extremeBest')} />
                      <Line type="monotone" dataKey="worst" stroke="#9CA3AF" strokeWidth={1.5} strokeDasharray="4 4" dot={false} name={tr('dash.extremeWorst')} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          ) : (
            <LockedSection requiredTier="flagship" title={tr('dash.ltv')} />
          )}
        </div>
      )}

      <div id="charts" className="scroll-mt-28 grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Outcome Distribution */}
        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('dash.outcomeProbDist')}</h2></CardHeader>
          <CardContent>
            <div className="h-52 sm:h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={outcomeData} layout="vertical" margin={{ left: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                <XAxis type="number" tickFormatter={(v) => `${v}%`} tick={{ fill: chart.tick }} />
                <YAxis type="category" dataKey="name" width={80} tick={{ fill: chart.tick }} />
                <Tooltip formatter={(v) => `${v}%`} contentStyle={tooltipStyle} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {outcomeData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* User Path Chart */}
        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('dash.userGrowthPath')}</h2></CardHeader>
          <CardContent>
            <div className="h-52 sm:h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={result.pathData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                <XAxis dataKey="day" tickFormatter={(d) => `D${d}`} tick={{ fill: chart.tick }} />
                <YAxis tickFormatter={(v) => formatNumber(v)} tick={{ fill: chart.tick }} />
                <Tooltip formatter={(v) => formatNumber(Number(v))} contentStyle={tooltipStyle} />
                <Line type="monotone" dataKey="users" stroke={chart.linePrimary} strokeWidth={2} dot={false} name={tr('dash.users')} />
                <Line type="monotone" dataKey="activeUsers" stroke={chart.lineSecondary} strokeWidth={1} dot={false} strokeDasharray="4 4" name={tr('dash.activeUsers')} />
              </LineChart>
            </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Revenue Path */}
        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('dash.revenuePath')}</h2></CardHeader>
          <CardContent>
            <div className="h-52 sm:h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={result.pathData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                <XAxis dataKey="day" tickFormatter={(d) => `D${d}`} tick={{ fill: chart.tick }} />
                <YAxis tickFormatter={(v) => formatNumber(v)} tick={{ fill: chart.tick }} />
                <Tooltip formatter={(v) => `¥${formatNumber(Number(v))}`} contentStyle={tooltipStyle} />
                <Line type="monotone" dataKey="revenue" stroke="#10B981" strokeWidth={2} dot={false} name={tr('dash.revenue')} />
              </LineChart>
            </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Strategy Comparison（专业区+；基础区结果为空时显示锁卡） */}
        {strategyData.length > 0 ? (
          <Card>
            <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('dash.strategyCompare')}</h2></CardHeader>
            <CardContent>
              <div className="h-52 sm:h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={strategyData} margin={{ left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: chart.tick }} angle={-20} textAnchor="end" height={60} />
                  <YAxis tickFormatter={(v) => `${v}%`} tick={{ fill: chart.tick }} />
                  <Tooltip formatter={(v) => `${v}%`} contentStyle={tooltipStyle} />
                  <Bar dataKey="top10" fill="#10B981" radius={[4, 4, 0, 0]} name={tr('dash.chartTop10')} />
                  <Bar dataKey="death" fill="#EF4444" radius={[4, 4, 0, 0]} name={tr('dash.chartDeathProb')} />
                </BarChart>
              </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        ) : (
          <LockedSection requiredTier="pro" title={tr('dash.strategyCompare')} />
        )}
      </div>

      {/* Ranking Stats */}
      <Card id="ranking" className="mb-6 scroll-mt-28">
        <CardHeader>
          <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('dash.rankingRate')}</h2>
          {!r.hasBenchmarkData ? (
            <p className="text-xs text-amber-600 dark:text-amber-400">{tr('dash.noBenchmark')}</p>
          ) : (
            <p className="text-xs text-green-700 dark:text-green-400">{tr('dash.benchmarkOk', { n: 13 })}</p>
          )}
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {[
              { label: tr('dash.aboveMedian'), value: r.aboveMedian },
              { label: 'Top 30%', value: r.top30 },
              { label: 'Top 20%', value: r.top20 },
              { label: 'Top 10%', value: r.top10 },
              { label: 'Top 5%', value: r.top5 },
            ].map((item) => (
              <MetricCard key={item.label} label={item.label} value={formatPercent(item.value)} />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Forecast Table */}
      <Card className="mb-6">
        <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('dash.keyMetricsForecast')}</h2></CardHeader>
        <CardContent>
          <Table>
            <thead>
              <tr>
                <Th>{tr('dash.colMetric')}</Th>
                <Th className="text-right">P10</Th>
                <Th className="text-right">{tr('dash.colMedian')}</Th>
                <Th className="text-right">P90</Th>
              </tr>
            </thead>
            <tbody>
              {[
                { label: tr('dash.exposure'), data: f.exposure },
                { label: tr('dash.users'), data: f.users },
                { label: tr('dash.activeUsers'), data: f.activeUsers },
                { label: tr('dash.retention'), data: f.retention, suffix: '%' },
                { label: tr('dash.shares'), data: f.shares },
                { label: tr('dash.revenue'), data: f.revenue, prefix: '¥' },
                { label: tr('dash.reputation'), data: f.reputation },
              ].map((row) => (
                <tr key={row.label}>
                  <Td className="font-medium">{row.label}</Td>
                  <Td className="text-right tabular-nums">{row.prefix || ''}{formatNumber(row.data.p10)}{row.suffix || ''}</Td>
                  <Td className="text-right font-medium tabular-nums">{row.prefix || ''}{formatNumber(row.data.p50)}{row.suffix || ''}</Td>
                  <Td className="text-right tabular-nums">{row.prefix || ''}{formatNumber(row.data.p90)}{row.suffix || ''}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>

      <div id="advanced" className="scroll-mt-28 space-y-6 mb-6">
      {result.sensitivity.length === 0 ? (
        <LockedSection requiredTier="pro" title={tr('dash.sensitivity')} />
      ) : (
      <Collapsible title={tr('dash.sensitivity')} subtitle={tr('dash.sensitivitySubtitle')} defaultOpen>
      <Card className="border-0 shadow-none">
        <CardContent className="pt-2 px-0">
          <Table>
            <thead>
              <tr>
                <Th>{tr('dash.colVariable')}</Th>
                <Th className="text-right">{tr('dash.colCurrentScore')}</Th>
                <Th className="text-right">{tr('dash.colScorePlus')}</Th>
                <Th className="text-right">{tr('dash.colScoreMinus')}</Th>
                <Th className="text-right">{tr('dash.colImpact')}</Th>
                <Th>{tr('dash.colPriority')}</Th>
              </tr>
            </thead>
            <tbody>
              {result.sensitivity.map((s) => (
                <tr key={s.variable}>
                  <Td className="font-medium">{labels.variableNames[s.variable] || s.variable}</Td>
                  <Td className="text-right tabular-nums">{s.originalValue}</Td>
                  <Td className="text-right text-green-600 tabular-nums">{formatPercent(s.top10AfterIncrease)}</Td>
                  <Td className="text-right text-red-500 tabular-nums">{formatPercent(s.top10AfterDecrease)}</Td>
                  <Td className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <div className="w-16 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                        <div className="h-full bg-gray-900 dark:bg-gray-200 rounded-full" style={{ width: `${s.impactStrength * 100}%` }} />
                      </div>
                    </div>
                  </Td>
                  <Td>
                    <Badge variant={s.optimizationPriority <= 2 ? 'danger' : s.optimizationPriority <= 4 ? 'warning' : 'default'}>
                      #{s.optimizationPriority}
                    </Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>
      </Collapsible>
      )}

      <Collapsible title={tr('dash.riskAnalysis')} subtitle={tr('dash.riskSubtitle')} defaultOpen={op.dead > 0.3}>
      <Card className="border-0 shadow-none">
        <CardContent className="pt-2 px-0">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-3">
              <div>
                <div className="text-xs text-gray-400">{tr('dash.topFailureReason')}</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{result.riskAnalysis.topFailureReason}</div>
              </div>
              <div>
                <div className="text-xs text-gray-400">{tr('dash.crashTime')}</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{result.riskAnalysis.mostLikelyCrashTime}</div>
              </div>
              <div>
                <div className="text-xs text-gray-400">{tr('dash.vulnerableVar')}</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{result.riskAnalysis.mostVulnerableVariable}</div>
              </div>
            </div>
            <div className="space-y-3">
              {[
                { label: tr('dash.negativeEvent'), value: result.riskAnalysis.negativeEventTriggerProb },
                { label: tr('dash.competitorShock'), value: result.riskAnalysis.competitorShockProb },
                { label: tr('dash.platformDep'), value: result.riskAnalysis.platformDependencyRisk },
                { label: tr('dash.updateInterrupt'), value: result.riskAnalysis.updateInterruptionRisk },
                { label: tr('dash.techDebt'), value: result.riskAnalysis.technicalDebtDragRisk },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">{item.label}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${item.value > 0.5 ? 'bg-red-500' : item.value > 0.3 ? 'bg-amber-500' : 'bg-green-500'}`}
                        style={{ width: `${item.value * 100}%` }}
                      />
                    </div>
                    <span className="text-xs tabular-nums text-gray-600 w-8 text-right">{formatPercent(item.value)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
      </Collapsible>

      <Collapsible title={tr('dash.warningMetrics')} subtitle={tr('dash.warningSubtitle')} defaultOpen={false}>
      <Card className="border-0 shadow-none">
        <CardContent className="pt-2 px-0">
          <Table>
            <thead>
              <tr>
                <Th>{tr('dash.colMetric')}</Th>
                <Th>{tr('dash.colHealthy')}</Th>
                <Th>{tr('dash.colDanger')}</Th>
                <Th>{tr('dash.colDescription')}</Th>
              </tr>
            </thead>
            <tbody>
              {result.warningIndicators.map((w) => (
                <tr key={w.metric}>
                  <Td className="font-medium">{w.metric}</Td>
                  <Td className="text-green-600">{w.healthyThreshold}</Td>
                  <Td className="text-red-500">{w.dangerThreshold}</Td>
                  <Td className="text-gray-500">{w.description}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>
      </Collapsible>
      </div>
    </PageShellWide>
  )
}
