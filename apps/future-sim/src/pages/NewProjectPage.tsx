// ============================================================
// NewProjectPage — create a new simulation
// ============================================================

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/store'
import { startOnboarding } from '@/lib/onboarding'
import { Card, CardHeader, CardContent, Button, Input } from '@/components/ui'
import type { ArtifactType, ProjectStage } from '@/types'
import { chipButtonClass } from '@/lib/utils'
import { useT } from '@/hooks/useT'
import { useLabels } from '@/hooks/useLabels'

const artifactTypes: ArtifactType[] = [
  'software', 'app', 'game', 'website', 'video', 'article',
  'community', 'ai_agent', 'business_idea', 'open_source',
]

const stages: ProjectStage[] = [
  'idea', 'prototype', 'demo', 'mvp', 'launched', 'growth', 'stagnant', 'decline',
]

export default function NewProjectPage() {
  const [name, setName] = useState('')
  const [type, setType] = useState<ArtifactType>('app')
  const [stage, setStage] = useState<ProjectStage>('mvp')
  const [error, setError] = useState('')
  const createNewProject = useAppStore((s) => s.createNewProject)
  const saveCurrentProject = useAppStore((s) => s.saveCurrentProject)
  const navigate = useNavigate()
  const tr = useT()
  const labels = useLabels()

  const handleCreate = async () => {
    if (!name.trim()) {
      setError(tr('new.nameRequired'))
      return
    }
    createNewProject(name.trim(), type, stage)
    startOnboarding()
    await saveCurrentProject()
    navigate('/profile')
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-6">{tr('new.title')}</h1>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('new.basic')}</h2>
        </CardHeader>
        <CardContent className="space-y-6">
          <Input
            label={tr('new.name')}
            placeholder={tr('new.namePlaceholder')}
            value={name}
            onChange={(e) => { setName(e.target.value); setError('') }}
            autoComplete="off"
            error={error}
          />

          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{tr('new.type')}</label>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
              {artifactTypes.map((t) => (
                <button key={t} onClick={() => setType(t)} className={chipButtonClass(type === t, 'text-xs')}>
                  {labels.artifactType[t]}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{tr('new.stage')}</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {stages.map((s) => (
                <button key={s} onClick={() => setStage(s)} className={chipButtonClass(stage === s, 'text-xs')}>
                  {labels.stage[s]}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <Button onClick={handleCreate}>{tr('new.create')}</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
