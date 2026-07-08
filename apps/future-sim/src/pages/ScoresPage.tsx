// ============================================================
// ScoresPage — variable scoring
// ============================================================

import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/store'
import { Button, Slider, Collapsible } from '@/components/ui'
import { PageEmpty } from '@/components/PageEmpty'
import { PageActions, PageShell } from '@/components/PageActions'
import { DataCompletenessCard } from '@/components/DataCompletenessCard'
import { toast } from '@/components/Toast'
import { useT } from '@/hooks/useT'
import { useLabels } from '@/hooks/useLabels'
import type { ScoreProfile } from '@/types'
import { Save } from 'lucide-react'

const GROUP_VARS: Record<string, { variables: string[]; negatives?: string[] }> = {
  artifact: {
    variables: ['quality', 'originality', 'clarity', 'usability', 'emotionalHook', 'differentiation', 'completeness', 'reliability', 'aestheticQuality', 'problemSolutionFit'],
  },
  market: {
    variables: ['marketSize', 'audiencePain', 'willingnessToPay', 'trendFit', 'timingScore', 'competitionIntensity', 'substitutionRisk', 'platformDependency', 'regulatoryRisk', 'categoryGrowth'],
    negatives: ['competitionIntensity', 'substitutionRisk', 'platformDependency', 'regulatoryRisk'],
  },
  distribution: {
    variables: ['shareability', 'viralityPotential', 'storyValue', 'socialProofPotential', 'creatorReputation', 'distributionPower', 'communityPotential', 'mediaFriendliness', 'recommendationFit', 'visualSpreadPower'],
  },
  retention: {
    variables: ['activationRatePotential', 'firstSessionValue', 'retentionPotential', 'habitPotential', 'networkEffect', 'switchingCost', 'longTermValue', 'updateVelocity', 'feedbackLoopStrength', 'communityLockIn'],
  },
  business: {
    variables: ['monetizationFit', 'pricingPower', 'arpuPotential', 'conversionPotential', 'upsellPotential', 'enterprisePotential', 'lowCostDistribution', 'grossMarginPotential', 'lifecycleValue', 'revenueDiversity'],
  },
  risk: {
    variables: ['executionRisk', 'technicalDebt', 'churnRisk', 'negativeFeedbackRisk', 'copycatRisk', 'scalabilityRisk', 'maintenanceBurden', 'legalRisk', 'platformBanRisk', 'founderDependency'],
    negatives: ['executionRisk', 'technicalDebt', 'churnRisk', 'negativeFeedbackRisk', 'copycatRisk', 'scalabilityRisk', 'maintenanceBurden', 'legalRisk', 'platformBanRisk', 'founderDependency'],
  },
}

export default function ScoresPage() {
  const { scores, updateScores, currentProject, saveCurrentProject } = useAppStore()
  const navigate = useNavigate()
  const tr = useT()
  const { scoreGroups, variableNames } = useLabels()

  if (!currentProject) {
    return <PageEmpty kind="no-project" />
  }

  const handleSave = async () => {
    await saveCurrentProject()
    toast(tr('toast.scoresSaved'))
  }

  const handleNext = async () => {
    await saveCurrentProject()
    navigate('/config')
  }

  return (
    <PageShell>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{tr('scores.title')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{tr('scores.subtitle')}</p>
        </div>
        <div className="hidden md:flex gap-2 shrink-0">
          <Button variant="secondary" onClick={handleSave}>
            <Save className="w-4 h-4 mr-1" />
            {tr('common.save')}
          </Button>
          <Button onClick={handleNext}>{tr('scores.next')}</Button>
        </div>
      </div>

      <DataCompletenessCard scores={scores} profile={currentProject} />

      <div className="space-y-3">
        {scoreGroups.map((group, gi) => {
          const def = GROUP_VARS[group.key]
          if (!def) return null
          const avg = Math.round(
            def.variables.reduce((sum, v) => sum + (scores[group.key as keyof ScoreProfile] as unknown as Record<string, number>)[v], 0) / def.variables.length,
          )
          return (
            <Collapsible
              key={group.key}
              title={group.label}
              subtitle={`${group.subtitle} · ${tr('common.avg')} ${avg}`}
              defaultOpen={gi === 0}
            >
              <div className="grid grid-cols-1 gap-4 pt-3">
                {def.variables.map((v) => (
                  <Slider
                    key={v}
                    label={variableNames[v] || v}
                    value={(scores[group.key as keyof ScoreProfile] as unknown as Record<string, number>)[v]}
                    onChange={(val) => updateScores(group.key as keyof ScoreProfile, v, val)}
                    negative={def.negatives?.includes(v)}
                  />
                ))}
              </div>
            </Collapsible>
          )
        })}
      </div>

      <PageActions className="md:hidden">
        <Button variant="secondary" className="flex-1" onClick={handleSave}>{tr('common.save')}</Button>
        <Button className="flex-1" onClick={handleNext}>{tr('common.next')} →</Button>
      </PageActions>
    </PageShell>
  )
}
