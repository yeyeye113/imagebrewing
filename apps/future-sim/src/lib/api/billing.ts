// ============================================================
// Billing API 预留 — 订单 / 余额契约（本地 stub）
// ============================================================

import type { PlanId } from '@/types/account'
import { apiRequest, ApiError } from './client'
import { apiGetSession } from './auth'
import { useAccountStore } from '@/store/account'
import { generateId } from '@/lib/utils'

export type PayChannel = 'wechat_native' | 'alipay' | 'stripe'

export interface CreateOrderRequest {
  skuId: string
  channel: PayChannel
  amountCents: number
  title: string
}

export interface PaymentOrder {
  orderId: string
  skuId: string
  channel: PayChannel
  amountCents: number
  title: string
  status: 'pending' | 'paid' | 'closed'
  /** 微信 Native 二维码内容（预留） */
  wechatCodeUrl?: string
  createdAt: string
}

export interface CreateOrderResponse {
  order: PaymentOrder
}

/** 预留：创建支付订单 */
export async function apiCreateOrder(req: CreateOrderRequest): Promise<CreateOrderResponse> {
  try {
    return await apiRequest<CreateOrderResponse>('/billing/orders', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  } catch (e) {
    if (e instanceof ApiError && e.code === 'API_NOT_CONFIGURED') {
      const order: PaymentOrder = {
        orderId: `ord_stub_${generateId()}`,
        skuId: req.skuId,
        channel: req.channel,
        amountCents: req.amountCents,
        title: req.title,
        status: 'pending',
        wechatCodeUrl: `weixin://wxpay/bizpayurl?pr=STUB_${req.skuId}`,
        createdAt: new Date().toISOString(),
      }
      return { order }
    }
    throw e
  }
}

/** 预留：查询订单状态 */
export async function apiGetOrder(orderId: string): Promise<PaymentOrder> {
  try {
    return await apiRequest<PaymentOrder>(`/billing/orders/${orderId}`)
  } catch (e) {
    if (e instanceof ApiError && e.code === 'API_NOT_CONFIGURED') {
      return {
        orderId,
        skuId: 'stub',
        channel: 'wechat_native',
        amountCents: 0,
        title: 'Stub',
        status: 'pending',
        createdAt: new Date().toISOString(),
      }
    }
    throw e
  }
}

/** 模拟支付成功回调：真实后端按服务端 SKU 表权威发放（忽略客户端 grant），随后同步本地会话 */
export async function apiConfirmOrderStub(
  order: PaymentOrder,
  grant: { credits?: number; plan?: PlanId },
): Promise<void> {
  try {
    await apiRequest(`/billing/orders/${order.orderId}/confirm`, { method: 'POST' })
    await apiGetSession()
  } catch (e) {
    if (e instanceof ApiError && e.code === 'API_NOT_CONFIGURED') {
      const store = useAccountStore.getState()
      if (grant.credits) store.addCreditsStub(grant.credits)
      if (grant.plan) store.setPlanStub(grant.plan)
      return
    }
    throw e
  }
}

export interface BalanceResponse {
  credits: number
  plan: PlanId
}

export async function apiGetBalance(): Promise<BalanceResponse> {
  try {
    return await apiRequest<BalanceResponse>('/billing/balance')
  } catch (e) {
    if (e instanceof ApiError && e.code === 'API_NOT_CONFIGURED') {
      const user = useAccountStore.getState().session?.user
      return { credits: user?.credits ?? 0, plan: user?.plan ?? 'free' }
    }
    throw e
  }
}
