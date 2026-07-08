// OutcomeChart - 结果分布图表
import React from 'react'
import { Card, CardHeader, CardContent } from '@/components/ui'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useT } from '@/hooks/useT'
import { useLabels } from '@/hooks/useLabels'
import type { OutcomeProbabilities } from '@/types'

interface OutcomeChartProps {
  outcomeProbabilities: OutcomeProbabilities
})


export const OutcomeChart = React.memo(function OutcomeChart({ outcomeProbabilities }: OutcomeChartProps) {
  const tr = useT()
  const labels = useLabels()
  
  const data = [
    { name: labels.outcome.dead, value: Math.round(outcomeProbabilities.dead * 100), color: '#EF4444' },
    { name: labels.outcome.low_alive, value: Math.round(outcomeProbabilities.lowAlive * 100), color: '#F59E0B' },
    { name: labels.outcome.niche_success, value: Math.round(outcomeProbabilities.nicheSuccess * 100), color: '#10B981' },
    { name: labels.outcome.moderate_success, value: Math.round(outcomeProbabilities.moderateSuccess * 100), color: '#3B82F6' },
    { name: labels.outcome.clear_success, value: Math.round(outcomeProbabilities.clearSuccess * 100), color: '#8B5CF6' },
    { name: labels.outcome.blockbuster, value: Math.round(outcomeProbabilities.blockbuster * 100), color: '#EC4899' },
    { name: labels.outcome.long_compound, value: Math.round(outcomeProbabilities.longCompound * 100), color: '#06B6D4' },
  ]

  return (
    <Card>
      <CardHeader>
        <h2 className="text-sm font-medium">{tr('dash.outcomeDist')}</h2>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--tw-border-gray-200, #e5e7eb)" />
            <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={60} />
            <YAxis tick={{ fontSize: 10 }} unit="%" width={40} />
            <Tooltip 
              formatter={(value: number) => [`${value}%`, tr('dash.probability')]}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
})

