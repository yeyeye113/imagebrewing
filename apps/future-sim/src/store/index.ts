// ============================================================
// Zustand store — global state management
// ============================================================

import { create } from 'zustand'
import type {
  ArtifactProfile,
  ScoreProfile,
  SimulationConfig,
  SimulationResult,
  ArtifactType,
  ProjectStage,
} from '@/types'
import { createDefaultScores, createDefaultExistingData } from '@/lib/defaults'
import { generateId } from '@/lib/utils'
import { getMessage, getStoredLocale } from '@/lib/i18n'
import type { ProjectRecord } from '@/lib/database'
import * as db from '@/lib/database'

interface AppState {
  // Current project
  currentProject: ArtifactProfile | null
  scores: ScoreProfile
  config: SimulationConfig
  result: SimulationResult | null

  // Project list
  projects: ProjectRecord[]
  loadingProjects: boolean

  // Actions
  loadProjects: () => Promise<void>
  createNewProject: (name: string, type: ArtifactType, stage: ProjectStage) => void
  openProject: (id: string) => Promise<void>
  saveCurrentProject: () => Promise<void>
  deleteProject: (id: string) => Promise<void>
  duplicateProject: (id: string) => Promise<void>

  updateProfile: (updates: Partial<ArtifactProfile>) => void
  updateScores: (group: keyof ScoreProfile, key: string, value: number) => void
  setScores: (scores: ScoreProfile) => void
  updateConfig: (updates: Partial<SimulationConfig>) => void
  setResult: (result: SimulationResult) => void
  reset: () => void
}

function defaultConfig(): SimulationConfig {
  return {
    runs: 10000,
    periodDays: 90,
    granularity: 'day',
    mode: 'quick',
    scenarios: ['baseline', 'optimistic', 'pessimistic'],
    strategies: ['original', 'clarity_boost', 'distribution_boost', 'retention_boost'],
  }
}

export const useAppStore = create<AppState>((set, get) => ({
  currentProject: null,
  scores: createDefaultScores(),
  config: defaultConfig(),
  result: null,
  projects: [],
  loadingProjects: false,

  loadProjects: async () => {
    set({ loadingProjects: true })
    const projects = await db.getAllProjects()
    set({ projects, loadingProjects: false })
  },

  createNewProject: (name, type, stage) => {
    const now = new Date().toISOString()
    const profile: ArtifactProfile = {
      id: generateId(),
      name,
      type,
      stage,
      description: '',
      targetUsers: '',
      coreFeatures: [],
      coreSellingPoints: [],
      competitors: [],
      channelResources: '',
      budget: '',
      teamSize: 1,
      updateFrequency: '',
      creatorInfluence: '',
      existingData: createDefaultExistingData(),
      createdAt: now,
      updatedAt: now,
    }
    set({
      currentProject: profile,
      scores: createDefaultScores(),
      config: defaultConfig(),
      result: null,
    })
  },

  openProject: async (id) => {
    const record = await db.getProject(id)
    if (record) {
      set({
        currentProject: record.profile,
        scores: record.scores || createDefaultScores(),
        config: record.config || defaultConfig(),
        result: record.result,
      })
    }
  },

  saveCurrentProject: async () => {
    const { currentProject, scores, config, result } = get()
    if (!currentProject) return
    const record: ProjectRecord = {
      id: currentProject.id,
      profile: currentProject,
      scores,
      config,
      result,
      updatedAt: new Date().toISOString(),
    }
    await db.saveProject(record)
    // Reload project list
    const projects = await db.getAllProjects()
    set({ projects })
  },

  deleteProject: async (id) => {
    await db.deleteProject(id)
    const projects = await db.getAllProjects()
    set({ projects })
  },

  duplicateProject: async (id) => {
    const record = await db.getProject(id)
    if (!record) return
    const newId = generateId()
    const now = new Date().toISOString()
    const newRecord: ProjectRecord = {
      ...record,
      id: newId,
      profile: {
        ...record.profile,
        id: newId,
        name: record.profile.name + getMessage(getStoredLocale(), 'common.copySuffix'),
        createdAt: now,
        updatedAt: now,
      },
      updatedAt: now,
    }
    await db.saveProject(newRecord)
    const projects = await db.getAllProjects()
    set({ projects })
  },

  updateProfile: (updates) => {
    const { currentProject } = get()
    if (!currentProject) return
    set({
      currentProject: {
        ...currentProject,
        ...updates,
        updatedAt: new Date().toISOString(),
      },
    })
  },

  updateScores: (group, key, value) => {
    const { scores } = get()
    set({
      scores: {
        ...scores,
        [group]: {
          ...scores[group],
          [key]: value,
        },
      },
    })
  },

  setScores: (scores) => set({ scores }),

  updateConfig: (updates) => {
    const { config } = get()
    set({ config: { ...config, ...updates } })
  },

  setResult: (result) => set({ result }),

  reset: () => {
    set({
      currentProject: null,
      scores: createDefaultScores(),
      config: defaultConfig(),
      result: null,
    })
  },
}))
