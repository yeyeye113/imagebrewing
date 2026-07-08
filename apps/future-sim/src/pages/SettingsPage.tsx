// ============================================================
// SettingsPage — 设置（语言 / 主题）
// ============================================================

import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardContent, Button } from '@/components/ui'
import { PageShell } from '@/components/PageActions'
import { LanguageToggle } from '@/components/LanguageToggle'
import { ThemeToggle } from '@/components/ThemeToggle'
import { useT } from '@/hooks/useT'
import { useLocaleStore } from '@/store/locale'
import { Settings } from 'lucide-react'

export default function SettingsPage() {
  const navigate = useNavigate()
  const tr = useT()
  const hydrate = useLocaleStore((s) => s.hydrate)

  useEffect(() => {
    hydrate()
  }, [hydrate])

  return (
    <PageShell>
      <div className="mb-6">
        <h1 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
          <Settings className="w-6 h-6" />
          {tr('settings.title')}
        </h1>
      </div>

      <Card className="mb-4">
        <CardHeader>
          <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('settings.language')}</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tr('settings.languageHint')}</p>
        </CardHeader>
        <CardContent>
          <LanguageToggle variant="prominent" />
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('settings.theme')}</h2>
        </CardHeader>
        <CardContent>
          <ThemeToggle />
        </CardContent>
      </Card>

      <div className="flex flex-col sm:flex-row gap-2">
        <Button variant="secondary" className="flex-1" onClick={() => navigate('/pricing')}>
          {tr('nav.pricing')}
        </Button>
        <Button variant="secondary" className="flex-1" onClick={() => navigate('/recharge')}>
          {tr('nav.recharge')}
        </Button>
      </div>

      <p className="text-center text-xs text-gray-400 dark:text-gray-500 mt-8">{tr('settings.disclaimer')}</p>
    </PageShell>
  )
}
