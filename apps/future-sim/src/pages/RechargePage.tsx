// ============================================================
// RechargePage — 充值 / 会员订阅
// ============================================================

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardContent, Badge, Button, Tabs } from '@/components/ui'
import { PageShell, PageShellWide } from '@/components/PageActions'
import { DevNotice } from '@/components/DevNotice'
import { WeChatPayModal } from '@/components/WeChatPayModal'
import { toast } from '@/components/Toast'
import { useAccountStore, useAccountUser } from '@/store/account'
import type { PlanId } from '@/types/account'
import { apiCreateOrder, type PaymentOrder } from '@/lib/api/billing'
import { getBillingCatalog } from '@/lib/i18n/billing'
import { useT } from '@/hooks/useT'
import { useLabels } from '@/hooks/useLabels'
import { useLocaleStore } from '@/store/locale'
import { Coins, Crown, Wallet, CreditCard, Check, Sparkles } from 'lucide-react'

type RechargeTab = 'credits' | 'membership'

interface PendingPay {
  order: PaymentOrder
  grant?: { credits?: number; plan?: PlanId }
}

export default function RechargePage() {
  const navigate = useNavigate()
  const user = useAccountUser()
  const { hydrate } = useAccountStore()
  const tr = useT()
  const labels = useLabels()
  const locale = useLocaleStore((s) => s.locale)
  const catalog = getBillingCatalog(locale)
  const { creditPacks, creditRules, subscriptionSkus, membershipPlans } = catalog
  const [tab, setTab] = useState<RechargeTab>('credits')
  const [pendingPay, setPendingPay] = useState<PendingPay | null>(null)
  const [paying, setPaying] = useState<string | null>(null)

  useEffect(() => {
    hydrate()
  }, [hydrate])

  const requireLogin = () => {
    toast(tr('recharge.loginFirst'))
    navigate(`/login?return=${encodeURIComponent('/recharge')}`)
  }

  const openWechatPay = async (
    skuId: string,
    title: string,
    amountCents: number,
    grant?: PendingPay['grant'],
  ) => {
    if (!user) {
      requireLogin()
      return
    }
    setPaying(skuId)
    try {
      const { order } = await apiCreateOrder({
        skuId,
        channel: 'wechat_native',
        amountCents,
        title,
      })
      setPendingPay({ order, grant })
    } catch {
      toast(tr('recharge.orderFailed'))
    } finally {
      setPaying(null)
    }
  }

  const handlePackHover = (packId: string) => {
    // 悬停时预加载逻辑（预留）
  }

  return (
    <PageShellWide className="max-w-5xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
          <Wallet className="w-6 h-6" />
          {tr('recharge.title')}
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{catalog.notice}</p>
      </div>

      <div className="mb-6">
        <DevNotice />
      </div>

      {/* 账户状态卡片 */}
      <Card className="mb-6">
        <CardContent className="py-4">
          {user ? (
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-medium">
                  {user.email?.[0]?.toUpperCase() ?? 'U'}
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{tr('recharge.currentAccount')}</p>
                  <p className="font-medium text-gray-900 dark:text-gray-100">{user.email}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-6 text-sm">
                <div className="flex items-center gap-2">
                  <CreditCard className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-500 dark:text-gray-400">{tr('recharge.balance')}</span>
                  <span className="font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
                    {user.credits.toLocaleString()} {tr('common.credits')}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Crown className="w-4 h-4 text-amber-500" />
                  <span className="text-gray-500 dark:text-gray-400">{tr('recharge.membership')}</span>
                  <Badge variant={user.plan === 'free' ? 'default' : 'success'}>{labels.plan[user.plan]}</Badge>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <CreditCard className="w-4 h-4" />
                {tr('recharge.loginHint')}
              </div>
              <Button onClick={() => navigate('/login?return=/recharge')} size="sm">
                {tr('recharge.goLogin')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 充值规则提示 */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-lg p-4 mb-6">
        <div className="flex items-start gap-3">
          <Sparkles className="w-5 h-5 text-blue-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-blue-900 dark:text-blue-100">{catalog.audience.primary}</p>
            <p className="text-xs text-blue-700 dark:text-blue-300 mt-1">{catalog.audience.anchor}</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        tabs={[
          { key: 'credits', label: tr('recharge.tab.credits') },
          { key: 'membership', label: tr('recharge.tab.membership') },
        ]}
        active={tab}
        onChange={setTab}
      />

      <div className="mt-6">
        {tab === 'credits' && (
          <div className="space-y-6">
            {/* 充值包 */}
            <div>
              <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                <Coins className="w-4 h-4" />
                {tr('recharge.packTitle', { n: '' })}
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {creditPacks.map((pack, index) => (
                  <Card
                    key={pack.id}
                    className={`relative transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 ${
                      pack.id === 'pack_30' ? 'ring-2 ring-blue-500 dark:ring-blue-400' : ''
                    }`}
                    onMouseEnter={() => handlePackHover(pack.id)}
                  >
                    {pack.tag && (
                      <div className="absolute -top-2.5 left-4">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium bg-blue-500 text-white rounded-full">
                          <Sparkles className="w-3 h-3" />
                          {pack.tag}
                        </span>
                      </div>
                    )}
                    <CardHeader className="pb-2 pt-4">
                      <div className="flex items-center justify-between">
                        <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                          {pack.credits}
                        </span>
                        <span className="text-xs text-gray-400 dark:text-gray-500">{tr('common.credits')}</span>
                      </div>
                      <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1">{pack.priceLabel}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{pack.unit}</p>
                    </CardHeader>
                    <CardContent>
                      <Button
                        className="w-full"
                        disabled={!user || paying !== null}
                        loading={paying === pack.id}
                        onClick={() => openWechatPay(pack.id, tr('recharge.packTitle', { n: pack.credits }), pack.priceCents, { credits: pack.credits })}
                      >
                        {paying === pack.id ? tr('common.processing') : tr('recharge.wechatPay')}
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>

            {/* 计费规则 */}
            <Card>
              <CardHeader>
                <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <CreditCard className="w-4 h-4" />
                  {tr('pricing.rules')}
                </h2>
              </CardHeader>
              <CardContent className="divide-y divide-gray-100 dark:divide-gray-800 p-0">
                {creditRules.map((r) => (
                  <div key={r.action} className="flex justify-between items-center px-4 py-3 text-sm">
                    <span className="text-gray-700 dark:text-gray-300">{r.action}</span>
                    <Badge variant="secondary">{r.cost}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        )}

        {tab === 'membership' && (
          <div className="space-y-6">
            {/* 会员方案 */}
            <div>
              <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                <Crown className="w-4 h-4 text-amber-500" />
                {tr('recharge.membership')}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {membershipPlans.filter((p) => p.id !== 'free').map((plan) => (
                  <Card
                    key={plan.id}
                    className={`relative transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 ${
                      plan.highlight ? 'ring-2 ring-amber-500 dark:ring-amber-400' : ''
                    }`}
                  >
                    {plan.highlight && (
                      <div className="absolute -top-2.5 left-1/2 -translate-x-1/2">
                        <span className="inline-flex items-center gap-1 px-3 py-0.5 text-[10px] font-medium bg-amber-500 text-white rounded-full">
                          <Sparkles className="w-3 h-3" />
                          推荐
                        </span>
                      </div>
                    )}
                    <CardHeader className="pt-4">
                      <div className="flex items-center gap-2">
                        <Crown className={`w-5 h-5 ${plan.highlight ? 'text-amber-500' : 'text-gray-400'}`} />
                        <h3 className="font-semibold text-gray-900 dark:text-gray-100">{plan.name}</h3>
                      </div>
                      <div className="mt-2">
                        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 inline-flex items-baseline gap-1">
                          {plan.priceLabel}
                          <span className="text-sm font-normal text-gray-500">{plan.period}</span>
                        </p>
                        {plan.yearly && (
                          <p className="text-xs text-green-600 dark:text-green-400 mt-1">{plan.yearly}</p>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-2 mb-4">
                        {plan.features.slice(0, 4).map((f, i) => (
                          <li key={i} className="flex items-start gap-2 text-xs text-gray-600 dark:text-gray-400">
                            <Check className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
                            {f}
                          </li>
                        ))}
                      </ul>
                      <Button
                        className="w-full"
                        variant={plan.highlight ? 'default' : 'secondary'}
                        disabled={!user || paying !== null}
                        loading={paying === plan.id}
                        onClick={() => {
                          const sku = subscriptionSkus.find(s => s.planId === plan.id)
                          if (sku) {
                            openWechatPay(sku.id, sku.label, sku.priceCents, { plan: plan.id })
                          }
                        }}
                      >
                        {tr('recharge.subscribe')}
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>

            {/* 订阅 SKU 快速入口 */}
            <Card>
              <CardHeader>
                <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('recharge.choosePlan')}</h2>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-3">
                  {subscriptionSkus.map((sku) => (
                    <button
                      key={sku.id}
                      disabled={!user || paying !== null}
                      onClick={() => openWechatPay(sku.id, sku.label, sku.priceCents, { plan: sku.planId })}
                      className="inline-flex items-center gap-2 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Crown className="w-4 h-4 text-amber-500" />
                      <span className="font-medium text-gray-900 dark:text-gray-100">{sku.label}</span>
                      <span className="text-gray-500 dark:text-gray-400">{sku.priceLabel}</span>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      <p className="text-center text-xs text-gray-400 dark:text-gray-500 mt-8">
        <Link to="/pricing" className="underline hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
          {tr('recharge.viewPricing')}
        </Link>
      </p>

      {/* 支付弹窗 */}
      {pendingPay && (
        <WeChatPayModal
          order={pendingPay.order}
          grant={pendingPay.grant}
          onClose={() => setPendingPay(null)}
          onSuccess={() => hydrate()}
        />
      )}
    </PageShellWide>
  )
}
