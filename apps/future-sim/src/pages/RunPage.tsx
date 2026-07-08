// ============================================================
// RunPage — simulation progress
// ============================================================

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/store'
import { Card, CardContent, Button, ProgressBar, MetricCard, Badge } from '@/components/ui'
import { AnimatedNumber, BorderBeam, DecodeText, ProgressRing, PulseDot, Reveal } from '@/components/fx'
import { cn, formatNumber, formatPercent } from '@/lib/utils'
import { PageEmpty } from '@/components/PageEmpty'
import { PageShell } from '@/components/PageActions'
import { useAccountStore, useAccountUser } from '@/store/account'
import { useLocaleStore } from '@/store/locale'
import { checkSimulationGate, deductSimulationCredits, recordQuickRun } from '@/lib/simulation-gate'
import { useT } from '@/hooks/useT'
import { useLabels } from '@/hooks/useLabels'
import { Play, X, CheckCircle, Loader2, FileText, BarChart3, Lock } from 'lucide-react'
import type { SimulationResult } from '@/types'
import { logger } from '@/lib/logger'

const STAGE_KEYS = [
  { key: 'params', labelKey: 'run.stage.params' as const },
  { key: 'simulating', labelKey: 'run.stage.simulating' as const },
  { key: 'stats', labelKey: 'run.stage.stats' as const },
  { key: 'sensitivity', labelKey: 'run.stage.sensitivity' as const },
  { key: 'strategies', labelKey: 'run.stage.strategies' as const },
  { key: 'report', labelKey: 'run.stage.report' as const },
] as const

type LiveStats = { deathProb: number; successProb: number; blockbusterProb: number }

export default function RunPage() {
  const { scores, config, currentProject, setResult, saveCurrentProject } = useAppStore()
  const user = useAccountUser()
  const { hydrate, deductCreditsStub } = useAccountStore()
  const navigate = useNavigate()
  const workerRef = useRef<Worker | null>(null)
  const [currentStage, setCurrentStage] = useState<string>('params')
  const [completed, setCompleted] = useState(0)
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const [cancelled, setCancelled] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<LiveStats | null>(null)
  const [preview, setPreview] = useState<SimulationResult | null>(null)

  const locale = useLocaleStore((s) => s.locale)
  const tr = useT()
  const labels = useLabels()

  const gate = checkSimulationGate(config.mode, user, locale)

  useEffect(() => {
    hydrate()
  }, [hydrate])

  const startSimulation = () => {
    if (!currentProject) return

    const gateNow = checkSimulationGate(config.mode, user, locale)
    if (!gateNow.allowed) {
      setError(gateNow.message ?? tr('run.cannotRun'))
      logger.warn('simulation', 'Simulation blocked by gate', { mode: config.mode, reason: gateNow.message })
      return
    }

    const creditCost = deductSimulationCredits(config.mode, user)
    if (creditCost > 0 && !deductCreditsStub(creditCost)) {
      setError(tr('run.creditsInsufficient', { cost: creditCost }))
      logger.warn('simulation', 'Insufficient credits', { required: creditCost, mode: config.mode })
      return
    }
    // 基础区每日额度记账（免费或超额付点都计入当日次数）
    if (config.mode === 'quick') recordQuickRun()

    // 设置日志上下文
    logger.setSession()
    logger.setProject(currentProject.id)
    logger.info('simulation', 'Starting simulation', {
      projectName: currentProject.name,
      projectId: currentProject.id,
      config: { runs: config.runs, periodDays: config.periodDays, mode: config.mode },
    })

    setRunning(true)
    setDone(false)
    setCancelled(false)
    setCompleted(0)
    setStats(null)
    setPreview(null)
    setError(null)
    setCurrentStage('params')

    setTimeout(() => setCurrentStage('simulating'), 500)

    const worker = new Worker(
      new URL('../workers/simulator.ts', import.meta.url),
      { type: 'module' },
    )
    workerRef.current = worker

    worker.onmessage = (e) => {
      const data = e.data

      // 处理 Worker 日志
      if (data.type === 'log') {
        const { entry } = data
        // 将 Worker 日志转发到主日志系统
        if (entry.level === 'error') {
          logger.error(entry.module as any, entry.message, { metadata: entry.meta })
        } else if (entry.level === 'warn') {
          logger.warn(entry.module as any, entry.message, { metadata: entry.meta })
        } else if (entry.level === 'info') {
          logger.info(entry.module as any, entry.message, { metadata: entry.meta })
        } else {
          logger.debug(entry.module as any, entry.message, { metadata: entry.meta })
        }
        return
      }

      if (data.type === 'progress') {
        setCompleted(data.completed)
        if (data.stats) setStats(data.stats)
      } else if (data.type === 'stage') {
        // 真实阶段推进（stats / sensitivity / strategies / report），由 Worker 在计算各阶段时上报
        setCurrentStage(data.stage)
        logger.info('simulation', `Stage: ${data.stage}`)
      } else if (data.type === 'done') {
        setCurrentStage('report')
        setResult(data.result)
        setPreview(data.result)
        setRunning(false)
        setDone(true)
        worker.terminate()
        logger.info('simulation', 'Simulation completed', {
          deathProb: data.result.outcomeProbabilities.dead,
          successProb: data.result.outcomeProbabilities.clearSuccess + data.result.outcomeProbabilities.blockbuster,
          confidence: data.result.confidence,
        })
        // 结果已入内存 store（本页与仪表盘可正常查看），落库异步进行；
        // IndexedDB 写失败不能静默——否则用户刷新后结果凭空消失且无从知晓。
        saveCurrentProject()
          .then(() => logger.info('storage', 'Project saved to IndexedDB'))
          .catch((err) => {
            logger.error('storage', 'Failed to save project', { stack: (err as Error).stack })
            setError(tr('run.saveFailed'))
          })
      }
    }

    worker.onerror = (ev) => {
      setRunning(false)
      const errorMsg = ev.message || tr('run.workerError')
      setError(errorMsg)
      logger.error('worker', 'Worker error', { stack: ev.message })
      worker.terminate()
    }

    worker.postMessage({
      type: 'start',
      scores,
      config,
      strategyBoosts: {},
      profile: currentProject,
      locale,
    })
  }

  const handleCancel = () => {
    workerRef.current?.postMessage({ type: 'cancel' })
    workerRef.current?.terminate()
    setRunning(false)
    setCancelled(true)
  }

  useEffect(() => {
    return () => {
      workerRef.current?.terminate()
    }
  }, [])

  if (!currentProject) {
    return <PageEmpty kind="no-project" />
  }

  const pct = config.runs > 0 ? (completed / config.runs) * 100 : 0

  return (
    <PageShell className="max-w-2xl">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
        <DecodeText text={tr('run.title')} />
      </h1>
      <p className="text-sm text-gray-500 mb-6">
        {tr('run.subtitle', { name: currentProject.name, runs: formatNumber(config.runs) })}
      </p>

      <Card className="mb-4">
        <CardContent className="py-4 space-y-2 text-sm text-gray-600 dark:text-gray-400">
          <div className="font-medium text-gray-900 dark:text-gray-100">{tr('run.configTitle')}</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div>{tr('run.configMode')}：{labels.mode[config.mode]} · {formatNumber(config.runs)}</div>
            <div className="col-span-2">{tr('run.configScenarios')}：{config.scenarios.map((s) => labels.scenario[s]).join('、')}</div>
            <div className="col-span-2">{tr('run.configStrategies')}：{config.strategies.map((s) => labels.strategy[s]).join('、')}</div>
          </div>
        </CardContent>
      </Card>

      {!gate.allowed && (
        <div className="mb-4 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-start gap-2 text-sm text-amber-900 dark:text-amber-200">
            <Lock className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{gate.message}</span>
          </div>
          {gate.actionHref && (
            <Button size="sm" variant="secondary" onClick={() => navigate(gate.actionHref!)}>
              {gate.actionLabel ?? tr('common.next')}
            </Button>
          )}
        </div>
      )}

      {gate.allowed && gate.creditCost != null && gate.creditCost > 0 && user && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {tr('run.creditsWillUse', { cost: gate.creditCost, balance: user.credits })}
        </p>
      )}

      {gate.allowed && config.mode === 'quick' && (gate.freeQuotaLeft ?? 0) > 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {tr('run.quotaLeft', { left: gate.freeQuotaLeft! })}
        </p>
      )}

      {/* 运行主控台：运行中化身 HUD——光束描边巡游 + 扫描线下扫 */}
      <Card className={cn('relative mb-6', running && 'fx-scanline overflow-hidden')}>
        {running && <BorderBeam />}
        <CardContent className="space-y-6">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
            {STAGE_KEYS.map((s, i) => {
              const stageOrder = STAGE_KEYS.findIndex((x) => x.key === currentStage)
              const isDone = i < stageOrder
              const isCurrent = s.key === currentStage
              return (
                <div key={s.key} className="flex items-center gap-1">
                  {isDone ? (
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  ) : isCurrent ? (
                    <Loader2 className="w-4 h-4 text-cyan-500 dark:text-cyan-400 animate-spin" />
                  ) : (
                    <div className="w-4 h-4 rounded-full border-2 border-gray-200 dark:border-gray-700" />
                  )}
                  <span
                    className={cn(
                      'text-xs',
                      isCurrent
                        ? 'font-medium text-cyan-700 dark:text-cyan-300 [text-shadow:0_0_12px_rgb(34_211_238/0.4)]'
                        : 'text-gray-400 dark:text-gray-500',
                    )}
                  >
                    {tr(s.labelKey)}
                  </span>
                  {i < STAGE_KEYS.length - 1 && <span className="text-gray-300 dark:text-gray-600 mx-1 hidden sm:inline">→</span>}
                </div>
              )
            })}
          </div>

          {running && (
            <div className="flex flex-col sm:flex-row items-center gap-5 sm:gap-8">
              {/* 辉光进度环：百分比数字弹簧滚动 */}
              <ProgressRing value={pct} size={136} className="shrink-0">
                <AnimatedNumber
                  value={pct}
                  format={(n) => `${Math.round(n)}%`}
                  className="text-2xl font-semibold text-gray-900 dark:text-gray-100"
                />
                <span className="mt-0.5 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-gray-400">
                  <PulseDot />
                  {tr('run.live')}
                </span>
              </ProgressRing>

              <div className="w-full flex-1">
                <div className="flex justify-between text-xs text-gray-500 mb-2">
                  <span>{tr('run.pathsDone', { done: formatNumber(completed), total: formatNumber(config.runs) })}</span>
                  <span className="tabular-nums">{Math.round(pct)}%</span>
                </div>
                <ProgressBar value={pct} />
                <p className="text-[11px] text-gray-400 mt-2">
                  {config.runs >= 50000 ? `${tr('run.parallelNote')} · ` : ''}
                  {tr('run.sampleHint')}
                </p>
              </div>
            </div>
          )}

          {running && stats && completed > 100 && (
            <div className="grid grid-cols-3 gap-3">
              <MetricCard
                label={`${tr('run.liveDeath')} (${tr('run.live')})`}
                value={<AnimatedNumber value={stats.deathProb * 100} format={(n) => `${n.toFixed(1)}%`} />}
              />
              <MetricCard
                label={`${tr('run.liveSuccess')} (${tr('run.live')})`}
                value={<AnimatedNumber value={stats.successProb * 100} format={(n) => `${n.toFixed(1)}%`} />}
              />
              <MetricCard
                label={`${tr('run.liveBlockbuster')} (${tr('run.live')})`}
                value={<AnimatedNumber value={stats.blockbusterProb * 100} format={(n) => `${n.toFixed(1)}%`} />}
              />
            </div>
          )}

          {done && preview && (
            <Reveal y={10}>
              <div className="rounded-xl border border-green-200 dark:border-green-900/50 bg-green-50/60 dark:bg-green-950/25 p-4 space-y-3">
                <div className="flex items-center gap-2 text-green-800 dark:text-green-300">
                  <CheckCircle className="w-5 h-5" />
                  <span className="font-medium">
                    <DecodeText text={tr('run.done')} />
                  </span>
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  {preview.productInsight?.verdict.headline ?? preview.coreJudgment.mostLikelyOutcome}
                </p>
                <div className="grid grid-cols-3 gap-2">
                  <MetricCard
                    className="bg-white/80 dark:bg-gray-900/60"
                    label={tr('dash.deathProb')}
                    value={<AnimatedNumber value={preview.outcomeProbabilities.dead * 100} format={(n) => `${n.toFixed(1)}%`} />}
                  />
                  <MetricCard
                    className="bg-white/80 dark:bg-gray-900/60"
                    label="Top10%"
                    value={<AnimatedNumber value={preview.ranking.top10 * 100} format={(n) => `${n.toFixed(1)}%`} />}
                  />
                  <MetricCard
                    className="bg-white/80 dark:bg-gray-900/60"
                    label={tr('common.confidence')}
                    value={<AnimatedNumber value={preview.confidence * 100} format={(n) => `${n.toFixed(1)}%`} />}
                  />
                </div>
                {preview.productInsight && (
                  <Badge variant={preview.productInsight.verdict.publishReady ? 'success' : 'warning'}>
                    {preview.productInsight.verdict.publishReady ? tr('run.diagnosisPublish') : tr('run.diagnosisOptimize')}
                  </Badge>
                )}
              </div>
            </Reveal>
          )}

          <div className="flex flex-wrap gap-3">
            {!running && !done && (
              <Button onClick={startSimulation} disabled={!gate.allowed}>
                <Play className="w-4 h-4 mr-2" />
                {tr('run.start')}
              </Button>
            )}
            {running && (
              <Button variant="danger" onClick={handleCancel}>
                <X className="w-4 h-4 mr-2" />
                {tr('run.cancel')}
              </Button>
            )}
            {done && (
              <>
                <Button onClick={() => navigate('/dashboard')}>
                  <BarChart3 className="w-4 h-4 mr-2" />
                  {tr('run.viewDashboard')}
                </Button>
                <Button variant="secondary" onClick={() => navigate('/report')}>
                  <FileText className="w-4 h-4 mr-2" />
                  {tr('run.viewReport')}
                </Button>
              </>
            )}
            {cancelled && (
              <Button variant="secondary" onClick={startSimulation}>{tr('run.rerun')}</Button>
            )}
            {error && (
              <div className="w-full rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}
          </div>

          <p className="text-xs text-gray-400">{tr('run.disclaimer')}</p>
        </CardContent>
      </Card>
    </PageShell>
  )
}
