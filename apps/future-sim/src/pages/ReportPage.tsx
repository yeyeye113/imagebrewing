// ============================================================
// ReportPage — full markdown report
// ============================================================

import { useMemo, useState } from 'react'
import { useAppStore } from '@/store'
import { useLocalizedResult } from '@/hooks/useLocalizedResult'
import { Card, CardContent, Button, Badge } from '@/components/ui'
import { BorderBeam, DecodeText } from '@/components/fx'
import { formatNumber, formatPercent } from '@/lib/utils'
import { formatProductInsightMarkdown } from '@/lib/product-insight-report'
import { MarkdownPreview } from '@/components/MarkdownPreview'
import { PageEmpty } from '@/components/PageEmpty'
import { PageShellWide } from '@/components/PageActions'
import { toast } from '@/components/Toast'
import { useT } from '@/hooks/useT'
import { getLabels } from '@/lib/i18n/labels'
import { getInsightNarrative } from '@/lib/i18n/insight-narrative'
import { getMessage } from '@/lib/i18n'
import { getTier } from '@/lib/simulation-tiers'
import { useLocaleStore } from '@/store/locale'
import { Copy, Download, FileJson, Lock } from 'lucide-react'
import type { SimulationResult, ArtifactProfile } from '@/types'
import type { Locale } from '@/lib/i18n/types'

function generateMarkdownReport(result: SimulationResult, project: ArtifactProfile, locale: Locale): string {
  const labels = getLabels(locale)
  const m = getInsightNarrative(locale).markdownReport
  const o = labels.outcome
  const op = result.outcomeProbabilities
  const r = result.ranking
  const f = result.forecast
  const cj = result.coreJudgment

  let md = `# ${m.title}\n\n`
  md += `> ${m.disclaimer}\n\n`

  md += `## 1. ${m.basicInfo}\n\n`
  md += `| ${m.project} | ${locale === 'zh-CN' ? '内容' : locale === 'ja-JP' ? '内容' : locale === 'ko-KR' ? '내용' : 'Value'} |\n|---|---|\n`
  md += `| ${m.name} | ${project.name} |\n`
  md += `| ${m.type} | ${labels.artifactType[project.type] ?? project.type} |\n`
  md += `| ${m.stage} | ${labels.stage[project.stage] ?? project.stage} |\n`
  md += `| ${m.targetUsers} | ${project.targetUsers || m.notFilled} |\n`
  md += `| ${m.period} | ${result.config.periodDays} ${m.days} |\n`
  md += `| ${m.runs} | ${formatNumber(result.config.runs)} |\n`
  md += `| ${m.confidence} | ${formatPercent(result.confidence)} |\n`
  md += `| ${m.completeness} | ${formatPercent(result.dataCompleteness)} |\n\n`

  md += `## 2. ${m.coreJudgment}\n\n`
  md += `- **${m.mostLikely}**：${cj.mostLikelyOutcome}\n`
  md += `- **${m.biggestOpp}**：${cj.biggestOpportunity}\n`
  md += `- **${m.biggestRisk}**：${cj.biggestRisk}\n`
  md += `- **${m.worthInvest}**：${cj.worthInvesting ? m.yes : m.no}\n`
  md += `- **${m.topOptimize}**：${cj.topOptimizationDirection}\n\n`

  if (result.productInsight) {
    md += formatProductInsightMarkdown(result.productInsight, locale)
    md += `\n---\n\n`
  } else {
    md += `> ⚠️ ${m.legacyInsight}\n\n`
  }

  md += `## 3. ${m.outcomeDist}\n\n`
  md += `| ${m.colOutcome} | ${m.colProb} |\n|---|---|\n`
  md += `| ${o.dead} | ${formatPercent(op.dead)} |\n`
  md += `| ${o.low_alive} | ${formatPercent(op.lowAlive)} |\n`
  md += `| ${o.niche_success} | ${formatPercent(op.nicheSuccess)} |\n`
  md += `| ${o.moderate_success} | ${formatPercent(op.moderateSuccess)} |\n`
  md += `| ${o.clear_success} | ${formatPercent(op.clearSuccess)} |\n`
  md += `| ${o.blockbuster} | ${formatPercent(op.blockbuster)} |\n`
  md += `| ${o.long_compound} | ${formatPercent(op.longCompound)} |\n\n`

  md += `## 4. ${m.ranking}\n\n`
  md += `> ${r.hasBenchmarkData ? m.benchmarkYes : m.benchmarkNo}\n\n`
  md += `| ${m.colIndicator} | ${m.colValue} |\n|---|---|\n`
  md += `| ${m.rankAboveMedian} | ${formatPercent(r.aboveMedian)} |\n`
  md += `| Top 30% | ${formatPercent(r.top30)} |\n`
  md += `| Top 20% | ${formatPercent(r.top20)} |\n`
  md += `| Top 10% | ${formatPercent(r.top10)} |\n`
  md += `| Top 5% | ${formatPercent(r.top5)} |\n`
  md += `| Top 1% | ${formatPercent(r.top1)} |\n`
  md += `| ${m.rankExpectedPctl} | ${formatPercent(r.expectedPercentile)} |\n`
  md += `| ${m.rankMedianPctl} | ${formatPercent(r.medianPercentile)} |\n\n`

  // 5. Forecast（行标签复用 dash.* 消息）
  const dashLabel = (key: Parameters<typeof getMessage>[1]) => getMessage(locale, key)
  md += `## 5. ${m.forecast}\n\n`
  md += `| ${m.colIndicator} | P10 | ${m.colMedian} | P90 |\n|---|---|---|---|\n`
  md += `| ${dashLabel('dash.exposure')} | ${formatNumber(f.exposure.p10)} | ${formatNumber(f.exposure.p50)} | ${formatNumber(f.exposure.p90)} |\n`
  md += `| ${dashLabel('dash.users')} | ${formatNumber(f.users.p10)} | ${formatNumber(f.users.p50)} | ${formatNumber(f.users.p90)} |\n`
  md += `| ${dashLabel('dash.activeUsers')} | ${formatNumber(f.activeUsers.p10)} | ${formatNumber(f.activeUsers.p50)} | ${formatNumber(f.activeUsers.p90)} |\n`
  md += `| ${dashLabel('dash.retention')} | ${f.retention.p10}% | ${f.retention.p50}% | ${f.retention.p90}% |\n`
  md += `| ${dashLabel('dash.shares')} | ${formatNumber(f.shares.p10)} | ${formatNumber(f.shares.p50)} | ${formatNumber(f.shares.p90)} |\n`
  md += `| ${dashLabel('dash.revenue')} | ¥${formatNumber(f.revenue.p10)} | ¥${formatNumber(f.revenue.p50)} | ¥${formatNumber(f.revenue.p90)} |\n\n`

  // 6. Future Paths（基于模拟 pathData 动态生成，而非写死文案）
  md += `## 6. ${m.futurePaths}\n\n`
  const path = (result.pathData || []) as { day: number; users: number; activeUsers: number; revenue: number }[]
  const atDay = (target: number) =>
    path.length === 0 ? null : path.reduce((prev, cur) =>
      Math.abs(cur.day - target) < Math.abs(prev.day - target) ? cur : prev)
  const fill = (tpl: string, vars: Record<string, string>) => tpl.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '')
  const seg = (label: string, target: number, prevTarget: number, riskHint: string, oppHint: string) => {
    const p = atDay(target)
    if (!p) return `### ${label}\n- ${m.notCovered}\n\n`
    const prev = atDay(prevTarget)
    const growth = prev && prev.users > 0 ? (p.users - prev.users) / prev.users * 100 : 0
    const trend = growth > 20 ? m.trendFast : growth > 2 ? m.trendSteady : growth > -10 ? m.trendPlateau : m.trendDecline
    const actRate = p.users > 0 ? p.activeUsers / p.users * 100 : 0
    return `### ${label}\n` +
      `- ${fill(m.pathStat, { users: formatNumber(p.users), active: formatNumber(p.activeUsers), rate: actRate.toFixed(0), rev: formatNumber(p.revenue) })}\n` +
      `- ${fill(m.phaseTrend, { trend, growth: `${growth >= 0 ? '+' : ''}${growth.toFixed(0)}` })}\n` +
      `- **${m.keyRisk}**：${riskHint}\n` +
      `- **${m.keyOpp}**：${oppHint}\n\n`
  }
  md += seg(m.phase0_7, 7, 0, m.riskHint0_7, m.oppHint0_7)
  md += seg(m.phase8_30, 30, 7, m.riskHint8_30, m.oppHint8_30)
  md += seg(m.phase31_90, 90, 30, m.riskHint31_90, m.oppHint31_90)
  md += seg(m.phase91_365, 365, 90, m.riskHint91_365, m.oppHint91_365)

  // 7. Failure Paths（诊断已覆盖时跳过，避免重复）
  if (!result.productInsight) {
    md += `## 7. ${m.failurePaths}\n\n`
    result.failurePaths.forEach((p, i) => {
      md += `### ${i + 1}. ${p.name}\n`
      md += `- **${m.pTrigger}**：${p.triggerCondition}\n`
      md += `- **${m.pProb}**：${formatPercent(p.probability)}\n`
      md += `- **${m.pSignals}**：${p.earlySignals}\n`
      md += `- **${m.pSolution}**：${p.solution}\n\n`
    })
  }

  // 8. Success Paths
  if (!result.productInsight) {
    md += `## 8. ${m.successPaths}\n\n`
    result.successPaths.forEach((p, i) => {
      md += `### ${i + 1}. ${p.name}\n`
      md += `- **${m.pTrigger}**：${p.triggerCondition}\n`
      md += `- **${m.pProb}**：${formatPercent(p.probability)}\n`
      md += `- **${m.pKeyVars}**：${p.keyVariables || ''}\n`
      md += `- **${m.pHowImprove}**：${p.howToImprove || ''}\n\n`
    })
  }

  // 敏感性 / 策略 / 优化 / 预警 / 结论（有诊断时章节号前移 2）
  let sec = result.productInsight ? 7 : 9

  // ---- v3 增强分析章节（结果档位内已生成的才输出）----
  const adv = result.advanced
  const msg = (key: Parameters<typeof getMessage>[1], vars?: Record<string, string | number>) => {
    const raw = getMessage(locale, key)
    return vars ? raw.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? '')) : raw
  }

  if (adv?.milestones && adv.milestones.length > 0) {
    md += `## ${sec++}. ${msg('report.secMilestones')}\n\n`
    md += `| ${msg('dash.colMilestone')} | ${msg('dash.colReachProb')} | ${msg('dash.colMedianDay')} |\n|---|---|---|\n`
    adv.milestones.forEach((m) => {
      const label = m.kind === 'users' ? msg('dash.msUsers', { n: formatNumber(m.threshold) }) : msg('dash.msRevenue', { n: formatNumber(m.threshold) })
      const day = m.medianDay !== null ? msg('dash.dayN', { n: m.medianDay }) : msg('dash.notReached')
      md += `| ${label} | ${formatPercent(m.reachProbability)} | ${day} |\n`
    })
    md += `\n`
  }

  if (adv?.survival) {
    md += `## ${sec++}. ${msg('report.secSurvival')}\n\n`
    md += `- ${msg('dash.medianCrashDay')}：${adv.survival.medianCrashDay !== null ? msg('dash.dayN', { n: adv.survival.medianCrashDay }) : msg('dash.noCrash')}\n`
    adv.survival.crashProbByPhase.forEach((p) => {
      md += `- ${msg(`dash.crashPhase_${p.phase}` as Parameters<typeof getMessage>[1])}：${formatPercent(p.prob)}\n`
    })
    md += `\n`
  }

  if (adv?.scenarioBreakdown && adv.scenarioBreakdown.length > 0) {
    md += `## ${sec++}. ${msg('report.secScenario')}\n\n`
    md += `| ${msg('dash.colScenario')} | ${msg('dash.colRuns')} | ${msg('dash.colDeath')} | ${msg('dash.colSuccess')} | ${msg('dash.colMedianUsers')} |\n|---|---|---|---|---|\n`
    adv.scenarioBreakdown.forEach((s) => {
      md += `| ${labels.scenario[s.scenario] ?? s.scenario} | ${formatNumber(s.runs)} | ${formatPercent(s.deathProb)} | ${formatPercent(s.successProb)} | ${formatNumber(s.medianUsers)} |\n`
    })
    md += `\n`
  }

  if (adv?.ltvPerUser) {
    md += `## ${sec++}. ${msg('report.secLtv')}\n\n`
    md += `- P50：¥${adv.ltvPerUser.p50}\n`
    md += `- P90：¥${adv.ltvPerUser.p90}\n\n`
  }

  if (result.sensitivity.length > 0) {
    md += `## ${sec++}. ${m.sensitivity}\n\n`
    md += `| ${m.colVariable} | ${m.colScore} | ${m.colTop10Impact} | ${m.colPriority} |\n|---|---|---|---|\n`
    result.sensitivity.forEach((s) => {
      md += `| ${labels.variableNames[s.variable] || s.variable} | ${s.originalValue} | +${formatPercent(s.top10AfterIncrease)} / -${formatPercent(s.top10AfterDecrease)} | #${s.optimizationPriority} |\n`
    })
    md += `\n`
  }

  if (result.strategyComparison.length > 0) {
    md += `## ${sec++}. ${m.strategyCompare}\n\n`
    md += `| ${m.colStrategy} | ${m.colDeath} | Top10% | ${m.colBlockbuster} | ${m.colUsers} | ${m.colRevenue} | ${m.colRecommend} |\n|---|---|---|---|---|---|---|\n`
    result.strategyComparison.forEach((s) => {
      md += `| ${labels.strategy[s.strategy] || s.strategy} | ${formatPercent(s.deathProb)} | ${formatPercent(s.top10Prob)} | ${formatPercent(s.blockbusterProb)} | ${formatNumber(s.medianUsers)} | ¥${formatNumber(s.medianRevenue)} | ${'⭐'.repeat(s.recommendationLevel)} |\n`
    })
    md += `\n`
  }

  if (!result.productInsight) {
    md += `## ${sec++}. ${m.optimization}\n\n`
    result.optimizationSuggestions.forEach((o) => {
      md += `### ${m.oPriority} ${o.priority}：${o.title}\n`
      md += `- **${m.oWhy}**：${o.whyImportant}\n`
      md += `- **${m.oSuccessImpact}**：${o.impactOnSuccess}\n`
      md += `- **${m.oFailImpact}**：${o.impactOnFailure}\n`
      md += `- **${m.oWhatChange}**：${o.whatToChange}\n`
      md += `- **${m.oVerify}**：${o.howToVerify}\n`
      md += `- **${m.oMetric}**：${o.metricToWatch}\n\n`
    })
  }

  md += `## ${sec++}. ${m.warnings}\n\n`
  md += `| ${m.colIndicator} | ${m.colHealthy} | ${m.colDanger} | ${m.colDesc} |\n|---|---|---|---|\n`
  result.warningIndicators.forEach((w) => {
    md += `| ${w.metric} | ${w.healthyThreshold} | ${w.dangerThreshold} | ${w.description} |\n`
  })
  md += `\n`

  // Conclusion
  md += `## ${sec}. ${m.conclusion}\n\n`
  md += `- **${m.worthPublish}**：${cj.worthInvesting ? m.yes : m.suggestOptimizeFirst}\n`
  md += `- **${m.optimizeBeforePublish}**：${op.dead > 0.4 ? m.suggestOptimizeFirst : m.directPublish}\n`
  md += `- **${m.mostLikely}**：${cj.mostLikelyOutcome}\n`
  md += `- **${m.biggestOpp}**：${cj.biggestOpportunity}\n`
  md += `- **${m.biggestRisk}**：${cj.biggestRisk}\n`
  md += `- **${m.topOptimize}**：${cj.topOptimizationDirection}\n`
  md += `- **${m.worthInvest}**：${cj.worthInvesting ? m.keepInvesting : m.cautionInvest}\n\n`

  md += `---\n\n`
  md += `*${m.generatedAt}：${new Date().toLocaleString(locale)}*\n`
  md += `*${m.footer}*\n`

  return md
}

export default function ReportPage() {
  const { currentProject } = useAppStore()
  // 语言自适应视图：切语言后报告叙事按新语言重建
  const result = useLocalizedResult()
  const [copied, setCopied] = useState(false)
  const tr = useT()
  const locale = useLocaleStore((s) => s.locale)

  const report = useMemo(() => {
    if (!result || !currentProject) return ''
    return generateMarkdownReport(result, currentProject, locale)
  }, [result, currentProject, locale])

  if (!result || !currentProject) {
    return <PageEmpty kind="no-result" />
  }

  const insight = result.productInsight
  const deathProb = insight?.verdict.deathProb ?? result.outcomeProbabilities.dead
  // 导出能力按结果产出档位门控；旧结果（无 advanced）保持全部可用不破坏存量
  const caps = result.advanced ? getTier(result.advanced.tier) : null
  const canDownloadMd = caps?.markdownDownload ?? true
  const canExportJson = caps?.jsonExport ?? true

  const handleCopy = async () => {
    await navigator.clipboard.writeText(report)
    setCopied(true)
    toast(tr('report.copied'))
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownloadMd = () => {
    const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${currentProject.name}_${tr('report.fileReport')}.md`
    a.click()
    URL.revokeObjectURL(url)
    toast(tr('report.mdDownloaded'))
  }

  const handleDownloadJson = () => {
    const summary = {
      project: currentProject,
      productInsight: result.productInsight ?? null,
      outcomeProbabilities: result.outcomeProbabilities,
      ranking: result.ranking,
      forecast: result.forecast,
      coreJudgment: result.coreJudgment,
      riskAnalysis: result.riskAnalysis,
      deathReasons: result.productInsight?.deathReasons ?? [],
      successOpportunities: result.productInsight?.successOpportunities ?? [],
      improvementPlan: result.productInsight?.improvementPlan ?? [],
      actionRoadmap: result.productInsight?.actionRoadmap ?? [],
      optimizationStrategies: result.productInsight?.optimizationStrategies ?? [],
      sensitivity: result.sensitivity,
      strategyComparison: result.strategyComparison,
      failurePaths: result.failurePaths,
      successPaths: result.successPaths,
      optimizationSuggestions: result.optimizationSuggestions,
      warningIndicators: result.warningIndicators,
      createdAt: result.createdAt,
    }
    const blob = new Blob([JSON.stringify(summary, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${currentProject.name}_${tr('report.fileSummary')}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast(tr('report.jsonExported'))
  }

  return (
    <PageShellWide className="max-w-4xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
            <DecodeText text={tr('report.title')} />
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {currentProject.name} · {tr('common.confidence')} {formatPercent(result.confidence)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={handleCopy}>
            <Copy className="w-4 h-4 mr-1" />
            {copied ? tr('report.copiedShort') : tr('report.copyShort')}
          </Button>
          <Button
            variant="secondary"
            disabled={!canDownloadMd}
            title={canDownloadMd ? undefined : tr('report.mdLocked')}
            onClick={handleDownloadMd}
          >
            {canDownloadMd ? <Download className="w-4 h-4 mr-1" /> : <Lock className="w-4 h-4 mr-1" />}
            {tr('report.download')}
          </Button>
          <Button
            variant="secondary"
            disabled={!canExportJson}
            title={canExportJson ? undefined : tr('report.jsonLocked')}
            onClick={handleDownloadJson}
          >
            {canExportJson ? <FileJson className="w-4 h-4 mr-1" /> : <Lock className="w-4 h-4 mr-1" />}
            {tr('report.exportJson')}
          </Button>
        </div>
      </div>

      {(!canDownloadMd || !canExportJson) && (
        <p className="text-xs text-amber-600 dark:text-amber-400 -mt-3 mb-4">
          {!canDownloadMd ? tr('report.mdLocked') : tr('report.jsonLocked')}
        </p>
      )}

      {/* 执行摘要卡片：光束描边巡游，突出「报告核心结论」地位 */}
      <Card className="relative mb-6 overflow-hidden">
        <BorderBeam />
        <CardContent className="py-5">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <Badge variant={deathProb > 0.4 ? 'danger' : deathProb > 0.25 ? 'warning' : 'success'}>
              {tr('report.deathBadge')} {formatPercent(deathProb)}
            </Badge>
            <Badge variant="info">Top10% {formatPercent(result.ranking.top10)}</Badge>
            {insight && (
              <Badge variant={insight.verdict.publishReady ? 'success' : 'warning'}>
                {insight.verdict.publishReady ? tr('report.publishReady') : tr('report.optimizeFirst')}
              </Badge>
            )}
          </div>
          <p className="text-base font-medium text-gray-900 dark:text-gray-100">
            {insight?.verdict.headline ?? result.coreJudgment.mostLikelyOutcome}
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2 leading-relaxed">
            {insight?.diagnosisSummary ?? result.coreJudgment.biggestRisk}
          </p>
          {!insight && (
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-3">{tr('report.rerunHint')}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6 sm:p-8">
          <MarkdownPreview source={report} />
        </CardContent>
      </Card>
    </PageShellWide>
  )
}
