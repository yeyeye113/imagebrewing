// ============================================================
// ProfilePage — artifact info input
// ============================================================

import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/store'
import { Card, CardHeader, CardContent, Button, Input, Textarea } from '@/components/ui'
import { PageEmpty } from '@/components/PageEmpty'
import { PageActions, PageShell } from '@/components/PageActions'
import { DataCompletenessCard } from '@/components/DataCompletenessCard'
import { toast } from '@/components/Toast'
import { useT } from '@/hooks/useT'
import { Save } from 'lucide-react'

const METRIC_KEYS = [
  'exposure', 'visitors', 'users', 'activeUsers', 'revenue',
  'day1Retention', 'day7Retention', 'day30Retention',
  'shares', 'comments', 'saves', 'rating',
] as const

const METRIC_LABEL_KEYS: Record<typeof METRIC_KEYS[number], Parameters<ReturnType<typeof useT>>[0]> = {
  exposure: 'profile.metric.exposure',
  visitors: 'profile.metric.visitors',
  users: 'profile.metric.users',
  activeUsers: 'profile.metric.activeUsers',
  revenue: 'profile.metric.revenue',
  day1Retention: 'profile.metric.day1',
  day7Retention: 'profile.metric.day7',
  day30Retention: 'profile.metric.day30',
  shares: 'profile.metric.shares',
  comments: 'profile.metric.comments',
  saves: 'profile.metric.saves',
  rating: 'profile.metric.rating',
}

export default function ProfilePage() {
  const { currentProject, scores, updateProfile, saveCurrentProject } = useAppStore()
  const navigate = useNavigate()
  const tr = useT()

  if (!currentProject) {
    return <PageEmpty kind="no-project" />
  }

  const handleSave = async () => {
    await saveCurrentProject()
    toast(tr('toast.profileSaved'))
  }

  const handleNext = async () => {
    await saveCurrentProject()
    navigate('/scores')
  }

  const updateField = (field: string, value: unknown) => {
    updateProfile({ [field]: value })
  }

  const updateExistingData = (field: string, value: number) => {
    updateProfile({
      existingData: { ...currentProject.existingData, [field]: value },
    })
  }

  const ed = currentProject.existingData

  return (
    <PageShell>
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{tr('profile.title')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{tr('profile.subtitle')}</p>
        </div>
        <div className="hidden md:flex gap-2 shrink-0">
          <Button variant="secondary" onClick={handleSave}>
            <Save className="w-4 h-4 mr-1" />
            {tr('common.save')}
          </Button>
          <Button onClick={handleNext}>{tr('profile.next')}</Button>
        </div>
      </div>

      <DataCompletenessCard scores={scores} profile={currentProject} />

      <div className="space-y-4">
        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('profile.basic')}</h2></CardHeader>
          <CardContent className="space-y-4">
            <Input label={tr('profile.field.name')} value={currentProject.name} onChange={(e) => updateField('name', e.target.value)} />
            <Textarea label={tr('profile.field.desc')} placeholder={tr('profile.field.descPh')} value={currentProject.description} onChange={(e) => updateField('description', e.target.value)} />
            <Input label={tr('profile.field.users')} placeholder={tr('profile.field.usersPh')} value={currentProject.targetUsers} onChange={(e) => updateField('targetUsers', e.target.value)} />
            <Textarea label={tr('profile.field.features')} placeholder={'Feature 1\nFeature 2'} value={currentProject.coreFeatures.join('\n')} onChange={(e) => updateField('coreFeatures', e.target.value.split('\n').filter(Boolean))} />
            <Textarea label={tr('profile.field.selling')} placeholder={'Point 1\nPoint 2'} value={currentProject.coreSellingPoints.join('\n')} onChange={(e) => updateField('coreSellingPoints', e.target.value.split('\n').filter(Boolean))} />
            <Textarea label={tr('profile.field.competitors')} placeholder={'Competitor 1\nCompetitor 2'} value={currentProject.competitors.join('\n')} onChange={(e) => updateField('competitors', e.target.value.split('\n').filter(Boolean))} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('profile.resources')}</h2></CardHeader>
          <CardContent className="space-y-4">
            <Textarea label={tr('profile.field.channels')} placeholder={tr('profile.field.channelsPh')} value={currentProject.channelResources} onChange={(e) => updateField('channelResources', e.target.value)} />
            <Input label={tr('profile.field.budget')} placeholder={tr('profile.field.budgetPh')} value={currentProject.budget} onChange={(e) => updateField('budget', e.target.value)} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input label={tr('profile.field.teamSize')} type="number" min={1} value={currentProject.teamSize} onChange={(e) => updateField('teamSize', Number(e.target.value))} />
              <Input label={tr('profile.field.updateFreq')} placeholder={tr('profile.field.updateFreqPh')} value={currentProject.updateFrequency} onChange={(e) => updateField('updateFrequency', e.target.value)} />
            </div>
            <Input label={tr('profile.field.influence')} placeholder={tr('profile.field.influencePh')} value={currentProject.creatorInfluence} onChange={(e) => updateField('creatorInfluence', e.target.value)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('profile.existing')}</h2></CardHeader>
          <CardContent>
            <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">{tr('profile.existingHint')}</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {METRIC_KEYS.map((key) => (
                <Input
                  key={key}
                  label={tr(METRIC_LABEL_KEYS[key])}
                  type="number"
                  min={0}
                  value={(ed as unknown as Record<string, number>)[key] || ''}
                  onChange={(e) => updateExistingData(key, Number(e.target.value))}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <PageActions className="md:hidden">
        <Button variant="secondary" className="flex-1" onClick={handleSave}>{tr('common.save')}</Button>
        <Button className="flex-1" onClick={handleNext}>{tr('common.next')} →</Button>
      </PageActions>
    </PageShell>
  )
}
