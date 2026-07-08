// ============================================================
// ComparePage — 多作品对比看板（Team / 机构级专属）
// ============================================================
//
// 把多个已模拟项目的结果放到同一张桌面：核心概率表 + 六维雷达。
// 门禁：Team 会员解锁；未解锁显示升级引导（本地 stub 可在充值页开通）。

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardContent, Badge, Button, Table, Th, Td } from '@/components/ui'
import { PageShellWide } from '@/components/PageActions'
import { toast } from '@/components/Toast'
import { useAccountUser } from '@/store/account'
import { useChartTheme } from '@/hooks/useChartTheme'
import { useT } from '@/hooks/useT'
import { formatNumber, formatPercent } from '@/lib/utils'
import { getAllProjects, type ProjectRecord } from '@/lib/database'
import {
  ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { Lock, Trophy, LayoutGrid, Download } from 'lucide-react'
import type { ScoreProfile, SimTierId } from '@/types'
import type { MessageKey } from '@/lib/i18n'

const SERIES_COLORS = ['#6366F1', '#10B981', '#F59E0B', '#EC4899']
const MAX_PICK = 4

const TIER_LABEL_KEY: Record<SimTierId, MessageKey> = {
  basic: 'tier.basic',
  pro: 'tier.pro',
  flagship: 'tier.flagship',
  institutional: 'tier.institutional',
}

/**
 * 六维展示画像：各评分组简单均值（风险组反转为安全分）。
 * 注意这是对比页的横向画像口径，非引擎加权综合分（那个在 Worker 内）。
 */
function scoreRadarProfile(scores: ScoreProfile): Record<string, number> {
  const groupAvg = (g: Record<string, number>) => {
    const vals = Object.values(g)
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
  }
  return {
    product: Math.round(groupAvg(scores.artifact as unknown as Record<string, number>)),
    market: Math.round(groupAvg(scores.market as unknown as Record<string, number>)),
    distribution: Math.round(groupAvg(scores.distribution as unknown as Record<string, number>)),
    retention: Math.round(groupAvg(scores.retention as unknown as Record<string, number>)),
    business: Math.round(groupAvg(scores.business as unknown as Record<string, number>)),
    safety: Math.round(100 - groupAvg(scores.risk as unknown as Record<string, number>)),
  }
}

export default function ComparePage() {
  const user = useAccountUser()
  const navigate = useNavigate()
  const tr = useT()
  const chart = useChartTheme()
  const [projects, setProjects] = useState<ProjectRecord[]>([])
  const [picked, setPicked] = useState<string[]>([])

  const unlocked = user?.plan === 'team'

  useEffect(() => {
    void getAllProjects().then((all) => {
      setProjects(all)
      // 默认选中最近 2 个有结果的项目
      const withResult = all.filter((p) => p.result && p.scores).map((p) => p.id)
      setPicked(withResult.slice(0, 2))
    })
  }, [])

  const togglePick = (id: string) => {
    setPicked((cur) => {
      if (cur.includes(id)) return cur.filter((x) => x !== id)
      if (cur.length >= MAX_PICK) return cur
      return [...cur, id]
    })
  }

  const selected = useMemo(
    () => picked
      .map((id) => projects.find((p) => p.id === id))
      .filter((p): p is ProjectRecord => !!p && !!p.result && !!p.scores),
    [picked, projects],
  )

  const dims: { key: string; labelKey: MessageKey }[] = [
    { key: 'product', labelKey: 'compare.dimProduct' },
    { key: 'market', labelKey: 'compare.dimMarket' },
    { key: 'distribution', labelKey: 'compare.dimDistribution' },
    { key: 'retention', labelKey: 'compare.dimRetention' },
    { key: 'business', labelKey: 'compare.dimBusiness' },
    { key: 'safety', labelKey: 'compare.dimSafety' },
  ]

  const radarData = useMemo(() => {
    if (selected.length < 2) return []
    const profiles = selected.map((p) => scoreRadarProfile(p.scores!))
    return dims.map((d) => {
      const row: Record<string, string | number> = { dim: tr(d.labelKey) }
      selected.forEach((p, i) => {
        row[p.profile.name] = profiles[i][d.key]
      })
      return row
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, tr])

  // 综合推荐：成功概率(明显成功+爆款+长期复利) − 死亡概率，取最高者
  const bestPick = useMemo(() => {
    if (selected.length < 2) return null
    let best: { name: string; score: number } | null = null
    for (const p of selected) {
      const op = p.result!.outcomeProbabilities
      const score = op.clearSuccess + op.blockbuster + op.longCompound - op.dead
      if (!best || score > best.score) best = { name: p.profile.name, score }
    }
    return best
  }, [selected])

  // 用户增长路径叠加：各项目均值世界线按采样日合并到同一 X 轴
  const overlayData = useMemo(() => {
    if (selected.length < 2) return []
    const byDay = new Map<number, Record<string, number>>()
    for (const p of selected) {
      for (const point of p.result!.pathData) {
        const row = byDay.get(point.day) ?? {}
        row[p.profile.name] = point.users
        byDay.set(point.day, row)
      }
    }
    return [...byDay.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([day, row]) => ({ day, ...row }))
  }, [selected])

  // 导出对比报告（Markdown）
  const handleExport = () => {
    const lines: string[] = [
      `# ${tr('compare.title')}`,
      '',
      ...(bestPick ? [`> ${tr('compare.verdictBest')}: **${bestPick.name}** — ${tr('compare.verdictBestDesc')}`, ''] : []),
      `| ${tr('compare.colProject')} | ${tr('compare.colDeath')} | ${tr('compare.colTop10')} | ${tr('compare.colBlockbuster')} | ${tr('compare.colCompound')} | ${tr('compare.colUsers')} | ${tr('compare.colRevenue')} | ${tr('compare.colConfidence')} |`,
      '|---|---|---|---|---|---|---|---|',
      ...selected.map((p) => {
        const res = p.result!
        const op = res.outcomeProbabilities
        return `| ${p.profile.name} | ${formatPercent(op.dead)} | ${formatPercent(res.ranking.top10)} | ${formatPercent(op.blockbuster)} | ${formatPercent(op.longCompound)} | ${formatNumber(res.forecast.users.p50)} | ¥${formatNumber(res.forecast.revenue.p50)} | ${formatPercent(res.confidence)} |`
      }),
      '',
      `## ${tr('compare.radar')}`,
      '',
      `| ${tr('compare.colProject')} | ${dims.map((d) => tr(d.labelKey)).join(' | ')} |`,
      `|---|${dims.map(() => '---').join('|')}|`,
      ...selected.map((p) => {
        const prof = scoreRadarProfile(p.scores!)
        return `| ${p.profile.name} | ${dims.map((d) => prof[d.key]).join(' | ')} |`
      }),
      '',
      '*Powered by Future Simulation Engine*',
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${tr('compare.fileName')}.md`
    a.click()
    URL.revokeObjectURL(url)
    toast(tr('compare.exported'))
  }

  const tooltipStyle = {
    backgroundColor: chart.tooltipBg,
    border: `1px solid ${chart.tooltipBorder}`,
    borderRadius: 8,
    fontSize: 12,
  }

  // ---- 未解锁：升级引导 ----
  if (!unlocked) {
    return (
      <PageShellWide className="max-w-3xl">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">{tr('compare.title')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">{tr('compare.subtitle')}</p>
        <Card className="border-dashed">
          <CardContent className="py-12 flex flex-col items-center text-center gap-3">
            <Lock className="w-8 h-8 text-gray-400" />
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('compare.locked')}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 max-w-md">{tr('compare.lockedDesc')}</p>
            <div className="flex gap-2 mt-2">
              <Button onClick={() => navigate('/pricing')}>{tr('compare.goTeam')}</Button>
              <Button variant="secondary" onClick={() => navigate('/recharge')}>{tr('pricing.goRecharge')}</Button>
            </div>
          </CardContent>
        </Card>
      </PageShellWide>
    )
  }

  const simulatable = projects.filter((p) => p.result && p.scores)

  return (
    <PageShellWide>
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <LayoutGrid className="w-6 h-6" />
            {tr('compare.title')}
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{tr('compare.subtitle')}</p>
        </div>
        {selected.length >= 2 && (
          <Button variant="secondary" className="shrink-0" onClick={handleExport}>
            <Download className="w-4 h-4 mr-1" />
            {tr('compare.export')}
          </Button>
        )}
      </div>

      {/* 项目选择 */}
      <Card className="mb-6">
        <CardHeader>
          <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('compare.pick')}</h2>
        </CardHeader>
        <CardContent>
          {projects.length === 0 || simulatable.length < 2 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">{tr('compare.emptyHint')}</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {projects.map((p) => {
                const hasResult = !!p.result && !!p.scores
                const active = picked.includes(p.id)
                return (
                  <button
                    key={p.id}
                    type="button"
                    disabled={!hasResult}
                    onClick={() => togglePick(p.id)}
                    className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
                      active
                        ? 'bg-gray-900 text-white border-gray-900 dark:bg-gray-100 dark:text-gray-900 dark:border-gray-100'
                        : hasResult
                          ? 'bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-gray-400'
                          : 'bg-gray-50 dark:bg-gray-800 text-gray-400 dark:text-gray-600 border-gray-100 dark:border-gray-800 cursor-not-allowed'
                    }`}
                  >
                    {p.profile.name}
                    {!hasResult && ` · ${tr('compare.noResult')}`}
                  </button>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {selected.length < 2 ? (
        simulatable.length >= 2 && (
          <p className="text-sm text-gray-500 dark:text-gray-400">{tr('compare.needTwo')}</p>
        )
      ) : (
        <>
          {/* 综合推荐 */}
          {bestPick && (
            <div className="mb-6 rounded-lg border border-green-200 dark:border-green-900/50 bg-green-50 dark:bg-green-950/30 px-4 py-3 flex items-center gap-3">
              <Trophy className="w-5 h-5 text-green-600 dark:text-green-400 shrink-0" />
              <div>
                <span className="text-sm font-medium text-green-900 dark:text-green-200">
                  {tr('compare.verdictBest')}：{bestPick.name}
                </span>
                <p className="text-xs text-green-700 dark:text-green-300 mt-0.5">{tr('compare.verdictBestDesc')}</p>
              </div>
            </div>
          )}

          {/* 核心指标对比表 */}
          <Card className="mb-6">
            <CardContent className="p-0 overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>{tr('compare.colProject')}</Th>
                    <Th>{tr('compare.colTier')}</Th>
                    <Th className="text-right">{tr('compare.colDeath')}</Th>
                    <Th className="text-right">{tr('compare.colTop10')}</Th>
                    <Th className="text-right">{tr('compare.colBlockbuster')}</Th>
                    <Th className="text-right">{tr('compare.colCompound')}</Th>
                    <Th className="text-right">{tr('compare.colUsers')}</Th>
                    <Th className="text-right">{tr('compare.colRevenue')}</Th>
                    <Th className="text-right">{tr('compare.colConfidence')}</Th>
                  </tr>
                </thead>
                <tbody>
                  {selected.map((p, i) => {
                    const res = p.result!
                    const op = res.outcomeProbabilities
                    return (
                      <tr key={p.id}>
                        <Td className="font-medium">
                          <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ backgroundColor: SERIES_COLORS[i % SERIES_COLORS.length] }} />
                          {p.profile.name}
                        </Td>
                        <Td>
                          {res.advanced
                            ? <Badge variant="info">{tr(TIER_LABEL_KEY[res.advanced.tier])}</Badge>
                            : <Badge variant="default">—</Badge>}
                        </Td>
                        <Td className="text-right tabular-nums text-red-500">{formatPercent(op.dead)}</Td>
                        <Td className="text-right tabular-nums">{formatPercent(res.ranking.top10)}</Td>
                        <Td className="text-right tabular-nums">{formatPercent(op.blockbuster)}</Td>
                        <Td className="text-right tabular-nums">{formatPercent(op.longCompound)}</Td>
                        <Td className="text-right tabular-nums">{formatNumber(res.forecast.users.p50)}</Td>
                        <Td className="text-right tabular-nums">¥{formatNumber(res.forecast.revenue.p50)}</Td>
                        <Td className="text-right tabular-nums">{formatPercent(res.confidence)}</Td>
                      </tr>
                    )
                  })}
                </tbody>
              </Table>
            </CardContent>
          </Card>

          {/* 用户增长路径叠加 */}
          {overlayData.length > 0 && (
            <Card className="mb-6">
              <CardHeader>
                <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('compare.pathOverlay')}</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tr('compare.pathOverlayHint')}</p>
              </CardHeader>
              <CardContent>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={overlayData}>
                      <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                      <XAxis dataKey="day" tickFormatter={(d) => `D${d}`} tick={{ fill: chart.tick }} />
                      <YAxis tickFormatter={(v) => formatNumber(v)} tick={{ fill: chart.tick }} />
                      <Tooltip formatter={(v) => formatNumber(Number(v))} contentStyle={tooltipStyle} />
                      <Legend />
                      {selected.map((p, i) => (
                        <Line
                          key={p.id}
                          type="monotone"
                          dataKey={p.profile.name}
                          stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                          strokeWidth={2}
                          dot={false}
                          connectNulls
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 六维雷达对比 */}
          <Card>
            <CardHeader>
              <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">{tr('compare.radar')}</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{tr('compare.radarHint')}</p>
            </CardHeader>
            <CardContent>
              <div className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData}>
                    <PolarGrid stroke={chart.grid} />
                    <PolarAngleAxis dataKey="dim" tick={{ fill: chart.tick, fontSize: 12 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={{ fill: chart.tick, fontSize: 10 }} />
                    {selected.map((p, i) => (
                      <Radar
                        key={p.id}
                        name={p.profile.name}
                        dataKey={p.profile.name}
                        stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                        fill={SERIES_COLORS[i % SERIES_COLORS.length]}
                        fillOpacity={0.15}
                      />
                    ))}
                    <Legend />
                    <Tooltip contentStyle={tooltipStyle} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </PageShellWide>
  )
}
