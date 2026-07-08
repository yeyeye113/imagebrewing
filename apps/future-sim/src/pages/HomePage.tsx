// ============================================================
// HomePage — project list
// ============================================================

import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/store'
import { Card, Badge, Button, EmptyState } from '@/components/ui'
import { DecodeText, Reveal, SpotlightCard } from '@/components/fx'
import { PageShellWide } from '@/components/PageActions'
import { formatPercent } from '@/lib/utils'
import { useT } from '@/hooks/useT'
import { useLabels } from '@/hooks/useLabels'
import { useLocaleStore } from '@/store/locale'
import { BCP47 } from '@/lib/i18n'
import { Plus, Copy, Trash2, FolderOpen, BarChart3 } from 'lucide-react'

export default function HomePage() {
  const { projects, loadingProjects, loadProjects, deleteProject, duplicateProject, openProject } = useAppStore()
  const navigate = useNavigate()
  const tr = useT()
  const labels = useLabels()
  const locale = useLocaleStore((s) => s.locale)

  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  const handleOpen = async (id: string) => {
    await openProject(id)
    navigate('/profile')
  }

  const handleViewResults = async (id: string) => {
    await openProject(id)
    navigate('/dashboard')
  }

  const handleDuplicate = async (id: string) => {
    await duplicateProject(id)
  }

  const handleDelete = async (id: string) => {
    if (confirm(tr('home.deleteConfirm'))) {
      await deleteProject(id)
    }
  }

  return (
    <PageShellWide>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 sm:mb-8">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-gray-100">
            <DecodeText text={tr('home.title')} />
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{tr('home.subtitle')}</p>
        </div>
        <Button className="w-full sm:w-auto" onClick={() => navigate('/new')}>
          <Plus className="w-4 h-4 mr-2" />
          {tr('home.new')}
        </Button>
      </div>

      {loadingProjects ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="fx-skeleton h-28 sm:h-20 rounded-xl border border-gray-200/80 dark:border-gray-800 bg-white/60 dark:bg-gray-900/50"
            />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <EmptyState
          icon={<FolderOpen className="w-12 h-12" />}
          title={tr('home.emptyTitle')}
          description={tr('home.emptyDesc')}
          action={
            <Button onClick={() => navigate('/new')}>
              <Plus className="w-4 h-4 mr-2" />
              {tr('home.new')}
            </Button>
          }
        />
      ) : (
        <div className="space-y-3">
          {projects.map((project, idx) => {
            const p = project.profile
            const r = project.result
            return (
              // 入场 stagger（封顶 0.4s 防长列表尾部等待）+ 追光 + 悬浮抬升
              <Reveal key={project.id} delay={Math.min(idx * 0.06, 0.4)}>
                <SpotlightCard>
                  <Card interactive>
                    <div className="px-4 sm:px-6 py-4 flex flex-col sm:flex-row sm:items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate max-w-full">{p.name}</h3>
                      <Badge>{labels.artifactType[p.type]}</Badge>
                      <Badge variant="info">{labels.stage[p.stage]}</Badge>
                    </div>
                    {p.description && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 sm:truncate">{p.description}</p>
                    )}
                    {project.updatedAt && (
                      <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
                        {tr('common.updatedAt')}{' '}
                        {new Date(project.updatedAt).toLocaleString(BCP47[locale], {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </p>
                    )}
                  </div>

                  {r ? (
                    <div className="flex items-center justify-between sm:justify-end gap-3 sm:gap-4 shrink-0 w-full sm:w-auto border-t sm:border-t-0 border-gray-100 dark:border-gray-800 pt-3 sm:pt-0">
                      <div className="flex gap-4">
                        <div className="text-center min-w-[48px]">
                          <div className="text-[11px] text-gray-400">{tr('common.death')}</div>
                          <div className="text-sm font-medium text-red-500">{formatPercent(r.outcomeProbabilities.dead)}</div>
                        </div>
                        <div className="text-center min-w-[48px]">
                          <div className="text-[11px] text-gray-400">Top10%</div>
                          <div className="text-sm font-medium text-green-600">{formatPercent(r.ranking.top10)}</div>
                        </div>
                        <div className="text-center min-w-[48px]">
                          <div className="text-[11px] text-gray-400">{tr('common.confidence')}</div>
                          <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{formatPercent(r.confidence)}</div>
                        </div>
                      </div>
                      {r.productInsight && (
                        <Badge variant={r.productInsight.verdict.publishReady ? 'success' : 'warning'} className="hidden sm:inline-flex">
                          {r.productInsight.verdict.publishReady ? tr('common.publishReady') : tr('common.needsWork')}
                        </Badge>
                      )}
                    </div>
                  ) : (
                    <span className="text-xs text-gray-400 shrink-0">{tr('common.notSimulated')}</span>
                  )}

                  <div className="flex items-center gap-1 shrink-0 w-full sm:w-auto border-t sm:border-t-0 border-gray-100 dark:border-gray-800 pt-3 sm:pt-0">
                    {r && (
                      <Button variant="secondary" size="sm" className="flex-1 sm:flex-none" onClick={() => handleViewResults(project.id)}>
                        <BarChart3 className="w-4 h-4 mr-1" />
                        {tr('common.results')}
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" onClick={() => handleOpen(project.id)} title={tr('common.edit')}>
                      <FolderOpen className="w-4 h-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDuplicate(project.id)}>
                      <Copy className="w-4 h-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(project.id)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
                  </Card>
                </SpotlightCard>
              </Reveal>
            )
          })}
        </div>
      )}
    </PageShellWide>
  )
}
