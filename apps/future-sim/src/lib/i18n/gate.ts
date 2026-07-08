// AUTO-GENERATED
import type { Locale } from './types.ts'
import type { SimMode } from '@/types'
import { getMessage } from './messages/index.ts'

export function formatGateDenied(
  locale: Locale,
  mode: SimMode,
  reason: 'login_required' | 'credits_insufficient',
  params: { cost: number; balance?: number },
) {
  if (reason === 'login_required') {
    return mode === 'ultra'
      ? getMessage(locale, 'run.loginRequiredUltra')
      : mode === 'deep'
        ? getMessage(locale, 'run.loginRequiredDeep')
        : getMessage(locale, 'run.loginRequiredStandard')
  }
  const modeLabel = getMessage(
    locale,
    mode === 'ultra' ? 'config.modeUltra' : mode === 'deep' ? 'config.modeDeep' : 'config.modeStandard',
  )
  return getMessage(locale, 'run.creditsNeed')
    .replace('{mode}', modeLabel)
    .replace('{cost}', String(params.cost))
    .replace('{balance}', String(params.balance ?? 0))
}

export function gateActionLabel(locale: Locale, reason: 'login_required' | 'credits_insufficient') {
  return reason === 'login_required'
    ? getMessage(locale, 'run.gateActionLogin')
    : getMessage(locale, 'run.gateActionRecharge')
}
