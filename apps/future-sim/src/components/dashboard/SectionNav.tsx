// SectionNav - 章节锚点导航
import { useT } from '@/hooks/useT'
import React from 'react'
import { cn } from '@/lib/utils'

const SECTION_NAV_KEYS = [
  { id: 'verdict', labelKey: 'dash.nav.overview' as const },
  { id: 'diagnosis', labelKey: 'dash.nav.diagnosis' as const },
  { id: 'charts', labelKey: 'dash.nav.charts' as const },
  { id: 'ranking', labelKey: 'dash.nav.ranking' as const },
  { id: 'advanced', labelKey: 'dash.nav.advanced' as const },
] as const

interface SectionNavProps {
  className?: string
})


export const SectionNav = React.memo(function SectionNav({ className }: SectionNavProps) {
  const tr = useT()
  
  return (
    <div className={cn('sticky top-0 z-10 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2 bg-gray-50/85 dark:bg-gray-950/80 backdrop-blur-md border-b border-gray-200/80 dark:border-gray-800/80', className)}>
      <div className="flex gap-1 overflow-x-auto scrollbar-none">
        {SECTION_NAV_KEYS.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            className="shrink-0 px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-white/90 dark:hover:bg-gray-900 rounded-md border border-transparent hover:border-cyan-500/30 dark:hover:border-cyan-400/30 transition-colors"
          >
            {tr(s.labelKey)}
          </a>
        ))}
      </div>
    </div>
  )
})


export { SECTION_NAV_KEYS }
