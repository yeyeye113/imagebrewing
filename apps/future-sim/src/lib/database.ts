// ============================================================
// IndexedDB — Project persistence
// ============================================================

import { openDB, type IDBPDatabase } from 'idb'
import type { ArtifactProfile, SimulationConfig, ScoreProfile, SimulationResult } from '@/types'

const DB_NAME = 'future-simulation-engine'
const DB_VERSION = 1

export interface ProjectRecord {
  id: string
  profile: ArtifactProfile
  scores: ScoreProfile | null
  config: SimulationConfig | null
  result: SimulationResult | null
  updatedAt: string
}

let dbPromise: Promise<IDBPDatabase> | null = null

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('projects')) {
          const store = db.createObjectStore('projects', { keyPath: 'id' })
          store.createIndex('updatedAt', 'updatedAt')
        }
      },
    })
  }
  return dbPromise
}

export async function getAllProjects(): Promise<ProjectRecord[]> {
  const db = await getDB()
  const all = await db.getAll('projects')
  return all.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export async function getProject(id: string): Promise<ProjectRecord | undefined> {
  const db = await getDB()
  return db.get('projects', id)
}

export async function saveProject(record: ProjectRecord): Promise<void> {
  const db = await getDB()
  record.updatedAt = new Date().toISOString()
  await db.put('projects', record)
}

export async function deleteProject(id: string): Promise<void> {
  const db = await getDB()
  await db.delete('projects', id)
}
