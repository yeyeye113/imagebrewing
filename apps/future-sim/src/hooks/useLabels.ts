// ============================================================
// useLabels — 枚举标签（作品类型 / 阶段 / 结局等）
// ============================================================

import { useMemo } from 'react'
import { getLabels } from '@/lib/i18n/labels'
import { useLocaleStore } from '@/store/locale'

export function useLabels() {
  const locale = useLocaleStore((s) => s.locale)
  return useMemo(() => getLabels(locale), [locale])
}
