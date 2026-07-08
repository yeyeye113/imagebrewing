// ============================================================
// ConfigPage — simulation configuration
// ============================================================

import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/store'
import { useAccountUser } from '@/store/account'
import { checkSimulationGate } from '@/lib/simulation-gate'
import { Card, CardHeader, CardContent, Button } from '@/components/ui'
import { formatNumber, chipButtonClass } from '@/lib/utils'
import { PageEmpty } from '@/components/PageEmpty'
import { PageActions, PageShell } from '@/components/PageActions'
import { toast } from '@/components/Toast'
import { useT } from '@/hooks/useT'
import { useLabels } from '@/hooks/useLabels'
import { useLocaleStore } from '@/store/locale'
import type { SimMode, TimeGranularity, SimScenario, StrategyType } from '@/types'
import { Play, Save, Clock } from 'lucide-react'

const modes: {
  key: SimMode
  labelKey: 'config.modeQuick' | 'config.modeStandard' | 'config.modeDeep' | 'config.modeUltra'
  runs: number
  hintKey: 'config.modeQuickHint' | 'config.modeStandardHint' | 'config.modeDeepHint' | 'config.modeUltraHint'
  zoneKey: 'tier.basic' | 'tier.pro' | 'tier.flagship' | 'tier.institutional'
  featKey: 'config.zoneFeatBasic' | 'config.zoneFeatPro' | 'config.zoneFeatFlagship' | 'config.zoneFeatInstitutional'
}[] = [
  { key: 'quick', labelKey: 'config.modeQuick', runs: 10000, hintKey: 'config.modeQuickHint', zoneKey: 'tier.basic', featKey: 'config.zoneFeatBasic' },
  { key: 'standard', labelKey: 'config.modeStandard', runs: 50000, hintKey: 'config.modeStandardHint', zoneKey: 'tier.pro', featKey: 'config.zoneFeatPro' },
  { key: 'deep', labelKey: 'config.modeDeep', runs: 100000, hintKey: 'config.modeDeepHint', zoneKey: 'tier.flagship', featKey: 'config.zoneFeatFlagship' },
  { key: 'ultra', labelKey: 'config.modeUltra', runs: 500000, hintKey: 'config.modeUltraHint', zoneKey: 'tier.institutional', featKey: 'config.zoneFeatInstitutional' },
]

const periods: { days: number; labelKey: 'config.period30' | 'config.period90' | 'config.period180' | 'config.period365' | 'config.period1095' }[] = [
  { days: 30, labelKey: 'config.period30' },
  { days: 90, labelKey: 'config.period90' },
  { days: 180, labelKey: 'config.period180' },
  { days: 365, labelKey: 'config.period365' },
  { days: 1095, labelKey: 'config.period1095' },
]

const granularities: { key: TimeGranularity; labelKey: 'config.granDay' | 'config.granWeek' | 'config.granMonth' }[] = [
  { key: 'day', labelKey: 'config.granDay' },
  { key: 'week', labelKey: 'config.granWeek' },
  { key: 'month', labelKey: 'config.granMonth' },
]

const allScenarios: SimScenario[] = [
  'baseline', 'optimistic', 'pessimistic', 'black_swan',
  'long_compound', 'competitor_shock', 'platform_boost', 'negative_event',
]

const allStrategies: StrategyType[] = [
  'original', 'clarity_boost', 'distribution_boost', 'retention_boost',
  'monetization_boost', 'quality_boost', 'community_boost',
]

function estimateRunLabel(runs: number, tr: ReturnType<typeof useT>): string {
  if (runs <= 10000) return tr('config.estimateQuick')
  if (runs <= 50000) return tr('config.estimateStandard')
  if (runs <= 100000) return tr('config.estimateDeep')
  return tr('config.estimateUltra')
}

export default function ConfigPage() {
  const { config, updateConfig, currentProject, saveCurrentProject } = useAppStore()
  const user = useAccountUser()
  const navigate = useNavigate()
  const tr = useT()
  const labels = useLabels()
  const locale = useLocaleStore((s) => s.locale)
  const modeGate = checkSimulationGate(config.mode, user, locale)

  if (!currentProject) {
    return <PageEmpty kind="no-project" />
  }

  const handleSave = async () => {
    await saveCurrentProject()
    toast(tr('toast.configSaved'))
  }

  const handleRun = async () => {
    await saveCurrentProject()
    navigate('/run')
  }

  const toggleScenario = (s: SimScenario) => {
    const current = config.scenarios
    const next = current.includes(s)
      ? current.filter((x) => x !== s)
      : [...current, s]
    updateConfig({ scenarios: next.length > 0 ? next : [s] })
  }

  const toggleStrategy = (s: StrategyType) => {
    const current = config.strategies
    const next = current.includes(s)
      ? current.filter((x) => x !== s)
      : [...current, s]
    updateConfig({ strategies: next.length > 0 ? next : [s] })
  }

  return (
    <PageShell>
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{tr('config.title')}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{tr('config.subtitle')}</p>
        </div>
        <div className="hidden md:flex gap-2 shrink-0">
          <Button variant="secondary" onClick={handleSave}>
            <Save className="w-4 h-4 mr-1" />
            {tr('common.save')}
          </Button>
          <Button onClick={handleRun}>
            <Play className="w-4 h-4 mr-1" />
            {tr('config.runNow')}
          </Button>
        </div>
      </div>

      <div className="mb-4 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 rounded-lg bg-gray-50 dark:bg-gray-800/50 px-3 py-2">
        <Clock className="w-3.5 h-3.5" />
        {estimateRunLabel(config.runs, tr)}
      </div>

      {!modeGate.allowed && (
        <div className="mb-4 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 px-4 py-3 text-sm text-amber-900 dark:text-amber-200 flex flex-wrap items-center justify-between gap-2">
          <span>{modeGate.message}</span>
          {modeGate.actionHref && (
            <Button size="sm" variant="secondary" onClick={() => navigate(modeGate.actionHref!)}>
              {modeGate.actionLabel}
            </Button>
          )}
        </div>
      )}

      {modeGate.allowed && config.mode !== 'quick' && (
        <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">
          {user?.plan === 'pro' || user?.plan === 'team'
            ? tr('config.memberIncluded')
            : tr('config.creditsCost', { cost: modeGate.creditCost ?? 0 })}
        </p>
      )}

      {modeGate.allowed && config.mode === 'quick' && modeGate.freeQuotaLeft !== undefined && (
        <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">
          {modeGate.freeQuotaLeft > 0
            ? tr('run.quotaLeft', { left: modeGate.freeQuotaLeft })
            : tr('config.creditsCost', { cost: modeGate.creditCost ?? 1 })}
        </p>
      )}

      <div className="space-y-4">
        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('config.simScale')}</h2></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{tr('config.runCount')}</label>
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2">
                {modes.map((m) => (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => updateConfig({ mode: m.key, runs: m.runs })}
                    className={chipButtonClass(config.mode === m.key, 'px-4 py-3 text-left')}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{tr(m.labelKey)}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        m.key === 'ultra'
                          ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300'
                          : m.key === 'deep'
                            ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
                            : m.key === 'standard'
                              ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'
                              : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                      }`}>
                        {tr(m.zoneKey)}
                      </span>
                    </div>
                    <div className="text-[11px] opacity-80 mt-0.5">{tr(m.hintKey)}</div>
                    <div className="text-[10px] opacity-60 mt-1 leading-relaxed">{tr(m.featKey)}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{tr('config.period')}</label>
              <div className="flex flex-wrap gap-2">
                {periods.map((p) => (
                  <button
                    key={p.days}
                    type="button"
                    onClick={() => updateConfig({ periodDays: p.days })}
                    className={chipButtonClass(config.periodDays === p.days, 'flex-1 min-w-[4rem] px-3 py-2 text-center')}
                  >
                    {tr(p.labelKey)}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{tr('config.granularity')}</label>
              <div className="grid grid-cols-3 gap-2">
                {granularities.map((g) => (
                  <button
                    key={g.key}
                    type="button"
                    onClick={() => updateConfig({ granularity: g.key })}
                    className={chipButtonClass(config.granularity === g.key, 'px-3 py-2 text-center')}
                  >
                    {tr(g.labelKey)}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2 pt-2 border-t border-gray-100 dark:border-gray-800">
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded border-gray-300 dark:border-gray-600"
                  checked={config.seed !== undefined}
                  onChange={(e) => updateConfig({
                    seed: e.target.checked ? (config.seed ?? 42) : undefined,
                  })}
                />
                {tr('config.fixedSeed')}
              </label>
              {config.seed !== undefined && (
                <div className="flex flex-wrap items-center gap-3">
                  <input
                    type="number"
                    min={1}
                    max={999999999}
                    className="w-40 px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-md text-sm bg-white dark:bg-gray-900 dark:text-gray-100"
                    value={config.seed}
                    onChange={(e) => {
                      const v = parseInt(e.target.value, 10)
                      if (!Number.isNaN(v) && v > 0) updateConfig({ seed: v })
                    }}
                  />
                  <span className="text-xs text-gray-500 dark:text-gray-400">{tr('config.seedDefault')}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('config.simScenarios')}</h2></CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {allScenarios.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleScenario(s)}
                  className={chipButtonClass(config.scenarios.includes(s), 'px-4 py-3')}
                >
                  {labels.scenario[s]}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('config.strategyCompare')}</h2></CardHeader>
          <CardContent>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{tr('config.strategyHint')}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {allStrategies.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleStrategy(s)}
                  className={chipButtonClass(config.strategies.includes(s), 'px-4 py-3')}
                >
                  {labels.strategy[s]}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gray-50 dark:bg-gray-800/40 border-dashed">
          <CardContent className="py-4">
            <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
              <div>{tr('config.summaryRuns', {
                runs: formatNumber(config.runs),
                days: config.periodDays,
                gran: tr(granularities.find((g) => g.key === config.granularity)?.labelKey ?? 'config.granDay'),
              })}</div>
              <div>{labels.mode[config.mode]} · {estimateRunLabel(config.runs, tr)}</div>
              <div>{config.scenarios.map((s) => labels.scenario[s]).join('、')}</div>
              <div>{config.strategies.map((s) => labels.strategy[s]).join('、')}</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <PageActions className="md:hidden">
        <Button variant="secondary" className="flex-1" onClick={handleSave}>{tr('common.save')}</Button>
        <Button className="flex-1" onClick={handleRun}>
          <Play className="w-4 h-4 mr-1" />
          {tr('config.run')}
        </Button>
      </PageActions>
    </PageShell>
  )
}
