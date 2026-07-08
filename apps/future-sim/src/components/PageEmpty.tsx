// ============================================================
// PageEmpty — 统一的空状态 + 引导下一步
// ============================================================

import { useNavigate } from 'react-router-dom'
import { EmptyState, Button } from '@/components/ui'
import { useT } from '@/hooks/useT'
import { BarChart3, Play, Plus } from 'lucide-react'

type EmptyKind = 'no-project' | 'no-result'

export function PageEmpty({ kind }: { kind: EmptyKind }) {
  const navigate = useNavigate()
  const tr = useT()

  const title = kind === 'no-project' ? tr('empty.noProject.title') : tr('empty.noResult.title')
  const description = kind === 'no-project' ? tr('empty.noProject.desc') : tr('empty.noResult.desc')
  const primaryLabel = kind === 'no-project' ? tr('empty.newProject') : tr('empty.goRun')
  const secondaryLabel = kind === 'no-project' ? tr('empty.backList') : tr('empty.checkConfig')
  const primaryPath = kind === 'no-project' ? '/new' : '/run'
  const secondaryPath = kind === 'no-project' ? '/' : '/config'

  return (
    <div className="max-w-lg mx-auto px-6 py-16">
      <EmptyState
        icon={kind === 'no-project' ? <Plus className="w-12 h-12" /> : <BarChart3 className="w-12 h-12" />}
        title={title}
        description={description}
        action={
          <div className="flex flex-col sm:flex-row gap-2 justify-center">
            <Button onClick={() => navigate(primaryPath)}>
              {kind === 'no-result' && <Play className="w-4 h-4 mr-2" />}
              {primaryLabel}
            </Button>
            <Button variant="secondary" onClick={() => navigate(secondaryPath)}>
              {secondaryLabel}
            </Button>
          </div>
        }
      />
    </div>
  )
}
