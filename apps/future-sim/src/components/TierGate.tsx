// ============================================================
// TierGate — 付费区锁卡与档位徽章
// ============================================================
//
// 结果对象自带产出时的档位（result.advanced.tier）：
// 低档位结果查看高档位分析时显示锁卡，引导切换模式重跑解锁。

import { useNavigate } from 'react-router-dom'
import { Card, CardContent, Badge, Button } from '@/components/ui'
import { useT } from '@/hooks/useT'
import { Lock, Crown, Gem, Zap, Building2 } from 'lucide-react'
import type { SimTierId } from '@/types'
import type { MessageKey } from '@/lib/i18n'

const TIER_LABEL_KEY: Record<SimTierId, MessageKey> = {
  basic: 'tier.basic',
  pro: 'tier.pro',
  flagship: 'tier.flagship',
  institutional: 'tier.institutional',
}

const TIER_ICON: Record<SimTierId, typeof Zap> = {
  basic: Zap,
  pro: Gem,
  flagship: Crown,
  institutional: Building2,
}

/** 结果档位徽章（看板头部展示结果产自哪个付费区） */
export function TierBadge({ tier }: { tier: SimTierId }) {
  const tr = useT()
  const Icon = TIER_ICON[tier]
  return (
    <Badge variant={tier === 'institutional' || tier === 'flagship' ? 'success' : tier === 'pro' ? 'info' : 'default'}>
      <Icon className="w-3 h-3 mr-1 inline-block" />
      {tr('tier.resultBadge', { tier: tr(TIER_LABEL_KEY[tier]) })}
    </Badge>
  )
}

/** 未解锁分析的锁卡：说明所需档位 + 升级 CTA */
export function LockedSection({ requiredTier, title }: { requiredTier: SimTierId; title: string }) {
  const tr = useT()
  const navigate = useNavigate()
  const tierLabel = tr(TIER_LABEL_KEY[requiredTier])
  return (
    <Card className="border-dashed bg-gray-50/60 dark:bg-gray-900/40">
      <CardContent className="py-6 flex flex-col items-center text-center gap-2">
        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
          <Lock className="w-4 h-4" />
          <span className="text-sm font-medium">{title}</span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {tr('tier.lockedTitle', { tier: tierLabel })} · {tr('tier.lockedDesc', { tier: tierLabel })}
        </p>
        <Button size="sm" variant="secondary" className="mt-1" onClick={() => navigate('/config')}>
          {tr('tier.upgradeCta')}
        </Button>
      </CardContent>
    </Card>
  )
}
