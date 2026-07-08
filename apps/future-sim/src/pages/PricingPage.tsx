// ============================================================
// PricingPage — simulation pricing preview (i18n)
// ============================================================

import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardContent, Badge, Button } from '@/components/ui'
import { PageShellWide } from '@/components/PageActions'
import { formatNumber } from '@/lib/utils'
import { getBillingCatalog } from '@/lib/i18n/billing'
import { getTier, TIER_MATRIX_FEATURES, TIER_ORDER, type TierMatrixFeature } from '@/lib/simulation-tiers'
import { useT } from '@/hooks/useT'
import { useLocaleStore } from '@/store/locale'
import { Check, Zap, Crown, Building2, Coins, Minus } from 'lucide-react'
import type { PlanId } from '@/types/account'
import type { SimTierId } from '@/types'
import type { MessageKey } from '@/lib/i18n'

const TIER_NAME_KEY: Record<SimTierId, MessageKey> = {
  basic: 'tier.basic',
  pro: 'tier.pro',
  flagship: 'tier.flagship',
  institutional: 'tier.institutional',
}

const FEATURE_KEY: Record<TierMatrixFeature, MessageKey> = {
  runs: 'pricing.feat.runs',
  sensitivity: 'pricing.feat.sensitivity',
  strategies: 'pricing.feat.strategies',
  pathBands: 'pricing.feat.pathBands',
  milestones: 'pricing.feat.milestones',
  survival: 'pricing.feat.survival',
  scenarioBreakdown: 'pricing.feat.scenarioBreakdown',
  ltvAndExtremes: 'pricing.feat.ltvAndExtremes',
  insightLevel: 'pricing.feat.insightLevel',
  markdownDownload: 'pricing.feat.markdownDownload',
  jsonExport: 'pricing.feat.jsonExport',
  benchmark: 'pricing.feat.benchmark',
  compareBoard: 'pricing.feat.compareBoard',
}

const PLAN_ICONS: Record<PlanId, typeof Zap> = {
  free: Zap,
  pro: Crown,
  team: Building2,
}

export default function PricingPage() {
  const navigate = useNavigate()
  const tr = useT()
  const locale = useLocaleStore((s) => s.locale)
  const catalog = getBillingCatalog(locale)

  return (
    <PageShellWide>
      <div className="mb-8 text-center max-w-2xl mx-auto">
        <Badge variant="info" className="mb-3">{tr('pricing.previewBadge')}</Badge>
        <h1 className="text-3xl font-semibold text-gray-900 dark:text-gray-100">{tr('pricing.heroTitle')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-3 leading-relaxed">{tr('pricing.heroDesc')}</p>
      </div>

      <Card className="mb-10 border-indigo-200 dark:border-indigo-900/40 bg-indigo-50/50 dark:bg-indigo-950/20">
        <CardContent className="py-5">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">{tr('pricing.audience')}</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{tr('pricing.audienceCore')}</div>
              <p className="text-gray-800 dark:text-gray-200">{catalog.audience.primary}</p>
            </div>
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{tr('pricing.audienceExt')}</div>
              <p className="text-gray-800 dark:text-gray-200">{catalog.audience.secondary}</p>
            </div>
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{tr('pricing.valueAnchor')}</div>
              <p className="text-gray-800 dark:text-gray-200">{catalog.audience.anchor}</p>
            </div>
          </div>
          <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">{catalog.notice}</p>
        </CardContent>
      </Card>

      {/* 三大付费区能力矩阵 */}
      <section className="mb-10">
        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">{tr('pricing.matrix')}</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{tr('pricing.matrixHint')}</p>
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 dark:border-gray-800 text-left text-gray-500 dark:text-gray-400">
                  <th className="px-4 py-3 font-medium">{tr('pricing.colFeature')}</th>
                  {TIER_ORDER.map((t) => (
                    <th key={t} className="px-4 py-3 font-medium text-center">{tr(TIER_NAME_KEY[t])}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {TIER_MATRIX_FEATURES.map((feature) => (
                  <tr key={feature} className="border-b border-gray-50 dark:border-gray-800/80">
                    <td className="px-4 py-2.5 text-gray-700 dark:text-gray-300">{tr(FEATURE_KEY[feature])}</td>
                    {TIER_ORDER.map((t) => {
                      const cap = getTier(t)
                      if (feature === 'runs') {
                        return (
                          <td key={t} className="px-4 py-2.5 text-center tabular-nums font-medium text-gray-900 dark:text-gray-100">
                            {formatNumber(cap.runs)}
                          </td>
                        )
                      }
                      if (feature === 'insightLevel') {
                        return (
                          <td key={t} className="px-4 py-2.5 text-center text-xs">
                            <span className={cap.insightLevel === 'full' ? 'text-green-600 dark:text-green-400 font-medium' : 'text-gray-500 dark:text-gray-400'}>
                              {cap.insightLevel === 'full' ? tr('pricing.insightFull') : tr('pricing.insightSummary')}
                            </span>
                          </td>
                        )
                      }
                      const unlocked = cap[feature] === true
                      return (
                        <td key={t} className="px-4 py-2.5 text-center">
                          {unlocked
                            ? <Check className="w-4 h-4 text-green-500 inline-block" />
                            : <Minus className="w-4 h-4 text-gray-300 dark:text-gray-600 inline-block" />}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </section>

      <section className="mb-10">
        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">{tr('pricing.membership')}</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {catalog.membershipPlans.map((plan) => {
            const Icon = PLAN_ICONS[plan.id]
            return (
              <Card
                key={plan.id}
                className={plan.highlight ? 'ring-2 ring-gray-900 dark:ring-gray-100 relative' : ''}
              >
                {plan.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge variant="default" className="bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900">
                      {tr('pricing.mostPopular')}
                    </Badge>
                  </div>
                )}
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Icon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                    <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">{plan.name}</h3>
                  </div>
                  <div className="mt-2 flex items-baseline gap-1">
                    <span className="text-3xl font-bold text-gray-900 dark:text-gray-100">{plan.priceLabel}</span>
                    <span className="text-sm text-gray-500 dark:text-gray-400">{plan.period}</span>
                  </div>
                  {plan.yearly && (
                    <p className="text-xs text-green-600 dark:text-green-400 mt-1">{plan.yearly}</p>
                  )}
                </CardHeader>
                <CardContent className="space-y-4">
                  <ul className="space-y-2 text-sm">
                    {plan.features.map((f) => (
                      <li key={f} className="flex gap-2 text-gray-700 dark:text-gray-300">
                        <Check className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
                        {f}
                      </li>
                    ))}
                    {plan.limits.map((l) => (
                      <li key={l} className="flex gap-2 text-gray-400 dark:text-gray-500 text-xs">
                        <span className="w-4 text-center">—</span>
                        {l}
                      </li>
                    ))}
                  </ul>
                  <Button variant={plan.highlight ? 'primary' : 'secondary'} className="w-full" disabled>
                    {plan.id === 'free' ? tr('pricing.startFree') : tr('pricing.goRecharge')}
                  </Button>
                </CardContent>
              </Card>
            )
          })}
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-4 text-center">{tr('pricing.enterprise')}</p>
      </section>

      <section className="mb-10">
        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">{tr('pricing.payPerRun')}</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{tr('pricing.payPerRunHint')}</p>
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 dark:border-gray-800 text-left text-gray-500 dark:text-gray-400">
                  <th className="px-4 py-3 font-medium">{tr('pricing.colMode')}</th>
                  <th className="px-4 py-3 font-medium">{tr('pricing.colPaths')}</th>
                  <th className="px-4 py-3 font-medium">{tr('pricing.colPayg')}</th>
                  <th className="px-4 py-3 font-medium">{tr('pricing.colPro')}</th>
                  <th className="px-4 py-3 font-medium">{tr('pricing.colUseCase')}</th>
                </tr>
              </thead>
              <tbody>
                {catalog.simulationTiers.map((row) => (
                  <tr key={row.mode} className="border-b border-gray-50 dark:border-gray-800/80">
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{row.mode}</td>
                    <td className="px-4 py-3 tabular-nums">{formatNumber(row.runs)}</td>
                    <td className="px-4 py-3 text-amber-700 dark:text-amber-400">{row.payg}</td>
                    <td className="px-4 py-3 text-green-700 dark:text-green-400">{row.proIncluded}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400 text-xs">{row.deepNote}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </section>

      <section className="mb-10 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2 flex items-center gap-2">
            <Coins className="w-5 h-5" />
            {tr('pricing.creditsFlex')}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{tr('pricing.creditsFlexHint')}</p>
          <div className="space-y-3">
            {catalog.creditPacks.map((pack) => (
              <Card key={pack.id}>
                <CardContent className="py-4 flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-900 dark:text-gray-100">
                        {tr('pricing.creditsUnit', { n: pack.credits })}
                      </span>
                      <Badge variant={pack.tag ? 'success' : 'default'}>{pack.tag}</Badge>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{pack.unit}</p>
                  </div>
                  <span className="text-xl font-bold text-gray-900 dark:text-gray-100">{pack.priceLabel}</span>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">{tr('pricing.rules')}</h2>
          <Card>
            <CardContent className="divide-y divide-gray-100 dark:divide-gray-800 p-0">
              {catalog.creditRules.map((r) => (
                <div key={r.action} className="flex justify-between px-4 py-3 text-sm">
                  <span className="text-gray-700 dark:text-gray-300">{r.action}</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100 tabular-nums">{r.cost}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>

      <div className="flex flex-wrap gap-3 justify-center pb-8">
        <Button variant="secondary" onClick={() => navigate('/')}>{tr('pricing.backHome')}</Button>
        <Button variant="secondary" onClick={() => navigate('/login?return=/recharge')}>{tr('pricing.loginRecharge')}</Button>
        <Button onClick={() => navigate('/new')}>{tr('pricing.startFree')}</Button>
      </div>
    </PageShellWide>
  )
}
