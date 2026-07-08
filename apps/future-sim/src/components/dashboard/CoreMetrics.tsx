// CoreMetrics - 核心指标卡片
import React from 'react'
import { Card, MetricCard } from '@/components/ui'
import { AnimatedNumber } from '@/components/fx'
import { useT } from '@/hooks/useT'
import { formatPercent } from '@/lib/utils'
import type { OutcomeProbabilities, RankingStats, SimulationResult } from '@/types'

interface CoreMetricsProps {
  result: SimulationResult
})


export const CoreMetrics = React.memo(function CoreMetrics({ result }: CoreMetricsProps) {
  const tr = useT()
  const op = result.outcomeProbabilities
  const r = result.ranking
  
  return (
    <>
      <div id="diagnosis" className="scroll-mt-28 grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <MetricCard label={tr('dash.mostLikely')} value={result.coreJudgment.mostLikelyOutcome} />
        <MetricCard
          label={tr('dash.deathProb')}
          value={<AnimatedNumber value={op.dead * 100} format={(n) => `${n.toFixed(1)}%`} />}
          subtext={op.dead > 0.4 ? tr('dash.riskHigh') : tr('dash.riskLow')}
        />
        <MetricCard label={tr('dash.top10Prob')} value={<AnimatedNumber value={r.top10 * 100} format={(n) => `${n.toFixed(1)}%`} />} />
        <MetricCard label={tr('dash.blockbusterProb')} value={<AnimatedNumber value={op.blockbuster * 100} format={(n) => `${n.toFixed(1)}%`} />} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <MetricCard label={tr('dash.longCompoundProb')} value={formatPercent(op.longCompound)} />
        <MetricCard label={tr('dash.biggestOpportunity')} value={result.coreJudgment.biggestOpportunity} />
        <MetricCard label={tr('dash.recommendedStrategy')} value={result.coreJudgment.topOptimizationDirection} />
      </div>
    </>
  )
})

