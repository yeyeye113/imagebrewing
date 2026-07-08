// ============================================================
// DevNotice — 预留能力提示条
// ============================================================

import { getBillingCatalog } from '@/lib/i18n/billing'
import { useLocaleStore } from '@/store/locale'
import { useT } from '@/hooks/useT'
import { Construction } from 'lucide-react'

export function DevNotice({ title, detail }: { title?: string; detail?: string }) {
  const locale = useLocaleStore((s) => s.locale)
  const tr = useT()
  const billing = getBillingCatalog(locale)

  return (
    <div className="rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 px-4 py-3 flex gap-3">
      <Construction className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
      <div className="text-sm">
        <p className="font-medium text-amber-900 dark:text-amber-200">{title ?? tr('dev.defaultTitle')}</p>
        <p className="text-amber-800/80 dark:text-amber-300/80 mt-1 text-xs leading-relaxed">
          {detail ?? billing.notice}
        </p>
      </div>
    </div>
  )
}
