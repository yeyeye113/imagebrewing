// ============================================================
// Account store — 登录 / 余额预留（本地模拟，无真实支付）
// ============================================================

import { create } from 'zustand'
import type { AccountSession, AccountUser, PlanId } from '@/types/account'
import { clearSession, loadSession, saveSession } from '@/lib/account-storage'
import { generateId } from '@/lib/utils'
import { getMessage, getStoredLocale } from '@/lib/i18n'

interface AccountState {
  session: AccountSession | null
  hydrated: boolean
  hydrate: () => void
  /** 写入服务端返回的真实会话（API 登录/会话刷新） */
  setSession: (session: AccountSession) => void
  /** 预留：邮箱密码登录，当前仅本地模拟 */
  loginStub: (email: string, displayName?: string) => void
  logout: () => void
  /** 预留：充值点数，当前仅本地累加（测试用） */
  addCreditsStub: (amount: number) => void
  /** 预留：切换会员档位（测试用） */
  setPlanStub: (plan: PlanId) => void
  /** 模拟扣点；余额不足返回 false */
  deductCreditsStub: (amount: number) => boolean
}

function buildStubUser(email: string, displayName?: string): AccountUser {
  const now = new Date().toISOString()
  return {
    id: generateId(),
    email: email.trim().toLowerCase(),
    displayName: displayName?.trim() || email.split('@')[0] || getMessage(getStoredLocale(), 'common.userFallback'),
    plan: 'free',
    credits: 0,
    createdAt: now,
  }
}

function buildSession(user: AccountUser): AccountSession {
  const expires = new Date()
  expires.setDate(expires.getDate() + 30)
  return {
    token: `stub_${generateId()}`,
    user,
    expiresAt: expires.toISOString(),
  }
}

export const useAccountStore = create<AccountState>((set, get) => ({
  session: null,
  hydrated: false,

  hydrate: () => {
    if (get().hydrated) return
    set({ session: loadSession(), hydrated: true })
  },

  setSession: (session) => {
    saveSession(session)
    set({ session, hydrated: true })
  },

  loginStub: (email, displayName) => {
    if (!email.trim()) return
    const session = buildSession(buildStubUser(email, displayName))
    saveSession(session)
    set({ session, hydrated: true })
  },

  logout: () => {
    clearSession()
    set({ session: null })
  },

  addCreditsStub: (amount) => {
    const { session } = get()
    if (!session || amount <= 0) return
    const next: AccountSession = {
      ...session,
      user: { ...session.user, credits: session.user.credits + amount },
    }
    saveSession(next)
    set({ session: next })
  },

  setPlanStub: (plan) => {
    const { session } = get()
    if (!session) return
    const next: AccountSession = {
      ...session,
      user: { ...session.user, plan },
    }
    saveSession(next)
    set({ session: next })
  },

  deductCreditsStub: (amount) => {
    const { session } = get()
    if (!session || amount <= 0) return true
    // 会员豁免统一由 simulation-gate 判定（ultra 仅 Team 免），这里只做纯余额扣减
    if (session.user.credits < amount) return false
    const next: AccountSession = {
      ...session,
      user: { ...session.user, credits: session.user.credits - amount },
    }
    saveSession(next)
    set({ session: next })
    return true
  },
}))

export function useAccountUser(): AccountUser | null {
  return useAccountStore((s) => s.session?.user ?? null)
}

export function useIsLoggedIn(): boolean {
  return useAccountStore((s) => !!s.session)
}
