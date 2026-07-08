// DiagnosisSection - 诊断区块
import React from 'react'
import { Card, CardHeader, CardContent, Badge } from '@/components/ui'
import { useT } from '@/hooks/useT'
import type { ProductInsightReport } from '@/types'

interface DiagnosisSectionProps {
  insight: ProductInsightReport | null
  confidence: number
})


export const DiagnosisSection = React.memo(function DiagnosisSection({ insight, confidence }: DiagnosisSectionProps) {
  const tr = useT()
  
  return (
    <>
      {!insight && (
        <div className="mb-6 rounded-lg border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/30 px-4 py-3 text-sm text-blue-800 dark:text-blue-200">
          {tr('dash.legacyNotice')}
        </div>
      )}

      {confidence < 0.45 && (
        <div className="mb-6 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
          {tr('dash.lowConfidence', { confidence: `${(confidence * 100).toFixed(0)}%` })}
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
                <Badge key={s} variant="default">&#10003; {s}</Badge>
              ))}
              {insight.scoreDiagnosis.weaknesses.map((s) => (
                <Badge key={s} variant="warning">&#9651; {s}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </>
  )
})

