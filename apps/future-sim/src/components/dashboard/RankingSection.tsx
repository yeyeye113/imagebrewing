// RankingSection - 排名统计区块
import React from 'react'
import { Card, CardHeader, CardContent } from '@/components/ui'
import { formatNumber, formatPercent } from '@/lib/utils'
import { useT } from '@/hooks/useT'
import type { RankingStats } from '@/types'

interface RankingSectionProps {
  ranking: RankingStats
})


export const RankingSection = React.memo(function RankingSection({ ranking }: RankingSectionProps) {
  const tr = useT()
  
  return (
    <Card>
      <CardHeader>
        <h2 className="text-sm font-medium">{tr('dash.ranking')}</h2>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {formatPercent(ranking.top10)}
            </div>
            <div className="text-xs text-gray-500">{tr('dash.top10')}</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {formatPercent(ranking.top1)}
            </div>
            <div className="text-xs text-gray-500">{tr('dash.top1')}</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {formatPercent(ranking.top25)}
            </div>
            <div className="text-xs text-gray-500">{tr('dash.top25')}</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {formatPercent(ranking.bottom25)}
            </div>
            <div className="text-xs text-gray-500">{tr('dash.bottom25')}</div>
          </div>
        </div>
        {ranking.medianRank !== undefined && (
          <div className="pt-2 border-t border-gray-100 dark:border-gray-800">
            <div className="text-sm text-gray-500">{tr('dash.medianRank')}: #{formatNumber(ranking.medianRank)}</div>
          </div>
        )}
      </CardContent>
    </Card>
  )
})

