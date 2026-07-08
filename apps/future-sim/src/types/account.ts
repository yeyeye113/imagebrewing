// ============================================================
// Account — 账户 / 会员类型（预留，待接后端）
// ============================================================

export type PlanId = 'free' | 'pro' | 'team'

export interface AccountUser {
  id: string
  email: string
  displayName: string
  plan: PlanId
  credits: number
  createdAt: string
}

/** 本地预留会话；正式环境由服务端 JWT 替换 */
export interface AccountSession {
  token: string
  user: AccountUser
  expiresAt: string
}

// 会员档位显示名请使用 getLabels(locale).plan（四语），不在此保留单语副本
