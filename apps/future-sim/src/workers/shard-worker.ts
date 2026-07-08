// ============================================================
// shard-worker — 并行分片子 Worker
// ============================================================
//
// 只负责跑主模拟的一个连续分片：接收分片参数 → runShard →
// 回传剥离路径的 RunResult[] + 聚合器状态，由协调 Worker 归并。
// 敏感性/策略/聚合仍在协调 Worker（simulator.ts）完成。

import { runShard } from './simulator.ts'
import type { ScoreProfile, SimulationConfig } from '../types'

interface ShardMessage {
  type: 'shard'
  scores: ScoreProfile
  config: SimulationConfig
  strategyBoosts: Record<string, number>
  shardIndex: number
  startIdx: number
  count: number
}

// 覆盖 simulator.ts 模块副作用注册的主协调 handler（本 Worker 只处理分片协议）
self.onmessage = (e: MessageEvent<ShardMessage>) => {
  const msg = e.data
  if (msg.type !== 'shard') return

  const { runs, aggState } = runShard(
    msg.scores,
    msg.config,
    msg.strategyBoosts ?? {},
    msg.startIdx,
    msg.count,
    msg.shardIndex,
    (done) => self.postMessage({ type: 'shard_progress', shardIndex: msg.shardIndex, done }),
  )

  self.postMessage({ type: 'shard_done', shardIndex: msg.shardIndex, runs, aggState })
}
