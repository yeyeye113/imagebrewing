// ============================================================
// VerdictBanner — 一眼看懂「该不该发、风险多大」
// ============================================================

import { Badge } from '@/components/ui'
import { formatPercent } from '@/lib/utils'
import type { SimulationResult } from '@/types'
import { useT } from '@/hooks/useT'
import { AlertTriangle, Rocket, Scale, TrendingDown } from 'lucide-react'

interface VerdictBannerProps {
  result: SimulationResult
}

function riskLevel(deathProb: number): 'low' | 'medium' | 'high' {
  if (deathProb >= 0.45) return 'high'
  if (deathProb >= 0.25) return 'medium'
  return 'low'
}

export function VerdictBanner({ result }: VerdictBannerProps) {
  const tr = useT()
  const op = result.outcomeProbabilities
  const cj = result.coreJudgment
  const insight = result.productInsight
  const deathProb = insight?.verdict.deathProb ?? op.dead
  const risk = riskLevel(deathProb)

  const riskStyles = {
    low: {
      border: 'border-green-200 dark:border-green-900/50',
      bg: 'bg-gradient-to-br from-green-50 to-white dark:from-green-950/30 dark:to-gray-900',
      icon: Rocket,
      iconColor: 'text-green-600 dark:text-green-400',
      label: tr('verdict.riskLow'),
      badge: 'success' as const,
    },
    medium: {
      border: 'border-amber-200 dark:border-amber-900/50',
      bg: 'bg-gradient-to-br from-amber-50 to-white dark:from-amber-950/30 dark:to-gray-900',
      icon: Scale,
      iconColor: 'text-amber-600 dark:text-amber-400',
      label: tr('verdict.riskMed'),
      badge: 'warning' as const,
    },
    high: {
      border: 'border-red-200 dark:border-red-900/50',
      bg: 'bg-gradient-to-br from-red-50 to-white dark:from-red-950/30 dark:to-gray-900',
      icon: TrendingDown,
      iconColor: 'text-red-600 dark:text-red-400',
      label: tr('verdict.riskHigh'),
      badge: 'danger' as const,
    },
  }

  const style = riskStyles[risk]
  const Icon = style.icon

  const headline = insight?.verdict.headline ?? cj.mostLikelyOutcome
  const publishReady = insight?.verdict.publishReady ?? cj.worthInvesting
  const confidenceNote =
    insight?.verdict.confidenceNote ??
    (result.confidence < 0.45 ? tr('verdict.confidenceLow') : tr('verdict.confidenceDefault'))

  return (
    <section id="verdict" className={`mb-6 rounded-xl border ${style.border} ${style.bg} p-6 scroll-mt-24`}>
      <div className="flex flex-col sm:flex-row sm:items-start gap-4">
        <div className={`shrink-0 p-3 rounded-lg bg-white/80 dark:bg-gray-800/80 ${style.iconColor}`}>
          <Icon className="w-8 h-8" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <Badge variant={style.badge}>{style.label}</Badge>
            <Badge variant={publishReady ? 'success' : 'warning'}>
              {publishReady ? tr('verdict.publishYes') : tr('verdict.publishNo')}
            </Badge>
            {result.confidence < 0.45 && (
              <Badge variant="warning">
                <AlertTriangle className="w-3 h-3 mr-1 inline" />
                {tr('verdict.lowConfidence')}
              </Badge>
            )}
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 leading-snug">{headline}</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2 leading-relaxed">
            {insight?.diagnosisSummary ??
              tr('verdict.mostLikely', { outcome: cj.mostLikelyOutcome, note: confidenceNote })}
          </p>
          <div className="flex flex-wrap gap-4 mt-4 text-sm">
            <div>
              <span className="text-gray-500">{tr('verdict.deathProb')} </span>
              <span className={`font-semibold tabular-nums ${deathProb > 0.4 ? 'text-red-600' : 'text-gray-900 dark:text-gray-100'}`}>
                {formatPercent(deathProb)}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Top10% </span>
              <span className="font-semibold text-green-700 tabular-nums">{formatPercent(result.ranking.top10)}</span>
            </div>
            <div>
              <span className="text-gray-500">{tr('verdict.topOptimize')} </span>
              <span className="font-medium text-gray-800 dark:text-gray-200">{cj.topOptimizationDirection}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
