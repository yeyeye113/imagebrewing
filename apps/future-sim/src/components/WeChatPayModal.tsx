// ============================================================
// WeChatPayModal — 微信支付 UI
// ============================================================

import { useState, useEffect, useCallback } from 'react'
import type { PaymentOrder } from '@/lib/api/billing'
import { apiConfirmOrderStub } from '@/lib/api/billing'
import type { PlanId } from '@/types/account'
import { Button } from '@/components/ui'
import { DevNotice } from '@/components/DevNotice'
import { toast } from '@/components/Toast'
import { useT } from '@/hooks/useT'
import { X, QrCode, CheckCircle, Loader2, AlertCircle } from 'lucide-react'

interface WeChatPayModalProps {
  order: PaymentOrder
  grant?: { credits?: number; plan?: PlanId }
  onClose: () => void
  onSuccess?: () => void
}

type PayStatus = 'pending' | 'polling' | 'success' | 'expired' | 'error'

function formatYuan(cents: number): string {
  return `¥${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 1)}`
}

const POLL_INTERVAL = 3000 // 3秒轮询
const EXPIRE_TIME = 15 * 60 * 1000 // 15分钟过期

export function WeChatPayModal({ order, grant, onClose, onSuccess }: WeChatPayModalProps) {
  const [status, setStatus] = useState<PayStatus>('pending')
  const [countdown, setCountdown] = useState(EXPIRE_TIME)
  const [confirming, setConfirming] = useState(false)
  const tr = useT()

  // 倒计时
  useEffect(() => {
    if (status !== 'pending') return
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1000) {
          setStatus('expired')
          return 0
        }
        return prev - 1000
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [status])

  // 轮询支付状态（模拟）
  const pollPayment = useCallback(async () => {
    setStatus('polling')
    // TODO: 接入真实微信支付后端 API 轮询
    // const result = await apiPollOrder(order.orderId)
    // if (result.paid) { setStatus('success'); onSuccess?.() }
  }, [order.orderId, onSuccess])

  const handleSimulatePaid = async () => {
    setConfirming(true)
    try {
      await apiConfirmOrderStub(order, grant ?? {})
      setStatus('success')
      toast(tr('pay.simulateDone'))
      onSuccess?.()
      // 成功后自动关闭
      setTimeout(() => onClose(), 1500)
    } catch {
      setStatus('error')
      toast(tr('pay.failed'))
    } finally {
      setConfirming(false)
    }
  }

  const handleCancel = () => {
    if (status === 'polling') {
      if (!confirm('支付进行中，确定取消？')) return
    }
    onClose()
  }

  const formatCountdown = (ms: number) => {
    const mins = Math.floor(ms / 60000)
    const secs = Math.floor((ms % 60000) / 1000)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      role="dialog"
      aria-modal
      onClick={(e) => e.target === e.currentTarget && handleCancel()}
    >
      <div className="w-full max-w-sm max-h-[90vh] overflow-y-auto bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('pay.title')}</span>
            {status === 'pending' && (
              <span className="text-xs text-gray-400 dark:text-gray-500">
                {formatCountdown(countdown)}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={handleCancel}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label={tr('common.close')}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* 订单信息 */}
          <div className="text-center space-y-1">
            <p className="text-sm text-gray-500 dark:text-gray-400">{order.title}</p>
            <p className="text-4xl font-bold text-gray-900 dark:text-gray-100 tabular-nums">
              {formatYuan(order.amountCents)}
            </p>
            <p className="text-[10px] text-gray-400 dark:text-gray-500 font-mono">
              {tr('pay.orderId')} {order.orderId}
            </p>
          </div>

          {/* 二维码区域 */}
          <div className="relative">
            {status === 'success' ? (
              <div className="flex flex-col items-center justify-center py-8 rounded-xl bg-green-50 dark:bg-green-900/20 border-2 border-green-200 dark:border-green-800">
                <CheckCircle className="w-16 h-16 text-green-500 mb-3" />
                <p className="text-base font-medium text-green-700 dark:text-green-400">{tr('pay.paid')}</p>
                <p className="text-xs text-green-600 dark:text-green-500 mt-1">{tr('pay.redirecting')}</p>
              </div>
            ) : status === 'expired' ? (
              <div className="flex flex-col items-center justify-center py-8 rounded-xl bg-amber-50 dark:bg-amber-900/20 border-2 border-amber-200 dark:border-amber-800">
                <AlertCircle className="w-16 h-16 text-amber-500 mb-3" />
                <p className="text-base font-medium text-amber-700 dark:text-amber-400">{tr('pay.expired')}</p>
                <p className="text-xs text-amber-600 dark:text-amber-500 mt-1">请重新发起支付</p>
              </div>
            ) : (
              <div className="flex flex-col items-center py-6 rounded-xl bg-gray-50 dark:bg-gray-800/50 border-2 border-dashed border-gray-200 dark:border-gray-700">
                {/* 二维码占位（真实接入时替换为微信支付二维码图片） */}
                <div className="relative">
                  <QrCode className="w-40 h-40 text-gray-300 dark:text-gray-600" strokeWidth={1} />
                  {status === 'polling' && (
                    <div className="absolute inset-0 flex items-center justify-center bg-white/80 dark:bg-gray-900/80 rounded-lg">
                      <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                    </div>
                  )}
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-4 px-4 text-center">
                  {status === 'polling' ? tr('pay.scanning') : tr('pay.qrHint')}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                  使用微信扫一扫支付
                </p>
              </div>
            )}
          </div>

          {/* 开发提示 */}
          {status === 'pending' && (
            <DevNotice title={tr('pay.devTitle')} detail={tr('pay.devDetail')} />
          )}

          {/* 操作按钮 */}
          <div className="flex gap-3">
            {status === 'pending' ? (
              <>
                <Button
                  variant="secondary"
                  className="flex-1"
                  onClick={handleCancel}
                >
                  {tr('common.cancel')}
                </Button>
                <Button
                  className="flex-1"
                  disabled={confirming}
                  onClick={handleSimulatePaid}
                >
                  {confirming ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {tr('common.processing')}
                    </span>
                  ) : tr('pay.simulateSuccess')}
                </Button>
              </>
            ) : status === 'expired' ? (
              <Button className="flex-1" onClick={() => setStatus('pending')}>
                重新生成订单
              </Button>
            ) : status === 'error' ? (
              <Button className="flex-1" onClick={() => setStatus('pending')}>
                重试
              </Button>
            ) : null}
          </div>

          {/* 额度提示 */}
          {grant?.credits && (
            <p className="text-center text-xs text-gray-400 dark:text-gray-500">
              支付成功后自动到账 <span className="font-medium text-gray-600 dark:text-gray-300">{grant.credits}</span> 点
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
