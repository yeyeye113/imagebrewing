// ============================================================
// DataCompletenessCard
// ============================================================

import { ProgressBar, Badge } from '@/components/ui'
import { computeDataCompleteness, profileFillRatio, scoreFillRatio } from '@/lib/completeness'
import type { ArtifactProfile, ScoreProfile } from '@/types'
import { useT } from '@/hooks/useT'
import { Lightbulb } from 'lucide-react'

function profileTipKeys(profile: ArtifactProfile): Array<'completeness.tipDesc' | 'completeness.tipUsers' | 'completeness.tipFeatures' | 'completeness.tipCompetitors' | 'completeness.tipChannels'> {
  const tips: Array<'completeness.tipDesc' | 'completeness.tipUsers' | 'completeness.tipFeatures' | 'completeness.tipCompetitors' | 'completeness.tipChannels'> = []
  if (profile.description.trim().length <= 10) tips.push('completeness.tipDesc')
  if (!profile.targetUsers.trim()) tips.push('completeness.tipUsers')
  if (profile.coreFeatures.length === 0) tips.push('completeness.tipFeatures')
  if (profile.competitors.length === 0) tips.push('completeness.tipCompetitors')
  if (!profile.channelResources.trim()) tips.push('completeness.tipChannels')
  return tips.slice(0, 3)
}

export function DataCompletenessCard({
  scores,
  profile,
}: {
  scores: ScoreProfile
  profile?: ArtifactProfile | null
}) {
  const tr = useT()
  const total = Math.round(computeDataCompleteness(scores, profile) * 100)
  const scorePct = Math.round(scoreFillRatio(scores) * 100)
  const profilePct = profile ? Math.round(profileFillRatio(profile) * 100) : 0
  const tipKeys = profile ? profileTipKeys(profile) : []

  const level = total >= 70 ? 'success' : total >= 45 ? 'warning' : 'danger'
  const levelLabel =
    total >= 70 ? tr('completeness.levelHigh') : total >= 45 ? tr('completeness.levelMid') : tr('completeness.levelLow')

  return (
    <div className="mb-6 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('completeness.title')}</span>
          <Badge variant={level}>
            {levelLabel} · {total}%
          </Badge>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {tr('completeness.scores')} {scorePct}% · {tr('completeness.profile')} {profilePct}%
        </span>
      </div>
      <ProgressBar value={total} className="h-2.5" />
      {total < 70 && (
        <div className="mt-3 flex items-start gap-2 text-xs text-gray-600 dark:text-gray-400">
          <Lightbulb className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-500" />
          <p>
            {tipKeys.length > 0
              ? `${tr('completeness.hintPrefix')}${tipKeys.map((k) => tr(k)).join('、')}`
              : tr('completeness.hintDefault')}
          </p>
        </div>
      )}
    </div>
  )
}
