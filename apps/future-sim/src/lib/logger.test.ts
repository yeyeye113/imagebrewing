import { describe, it, expect, beforeEach } from 'vitest'
import { logger, type LogEntry, type LogLevel, type LogModule } from './logger'

describe('Logger', () => {
  beforeEach(() => {
    logger.clear()
    logger.clearContext()
    logger.clearFilters()
  })

  describe('Basic logging', () => {
    it('should add log entry', () => {
      logger.info('simulation', 'Test message')
      const entries = logger.getEntries()
      expect(entries).toHaveLength(1)
      expect(entries[0].message).toBe('Test message')
      expect(entries[0].level).toBe('info')
      expect(entries[0].module).toBe('simulation')
    })

    it('should support different log levels', () => {
      logger.debug('ui', 'Debug message')
      logger.info('engine', 'Info message')
      logger.warn('worker', 'Warning message')
      logger.error('api', 'Error message')

      const entries = logger.getEntries()
      expect(entries).toHaveLength(4)
      expect(entries.map(e => e.level)).toEqual(['debug', 'info', 'warn', 'error'])
    })

    it('should include metadata', () => {
      logger.info('simulation', 'Test', { userId: 123, action: 'test' })
      const entries = logger.getEntries()
      expect(entries[0].metadata).toEqual({ userId: 123, action: 'test' })
    })
  })

  describe('Context', () => {
    it('should set session context', () => {
      logger.setSession('session-123')
      logger.info('ui', 'Test')
      const entries = logger.getEntries()
      expect(entries[0].sessionId).toBe('session-123')
    })

    it('should set project context', () => {
      logger.setProject('project-456')
      logger.info('ui', 'Test')
      const entries = logger.getEntries()
      expect(entries[0].projectId).toBe('project-456')
    })

    it('should clear context', () => {
      logger.setSession('session-123')
      logger.setProject('project-456')
      logger.clearContext()
      logger.info('ui', 'Test')
      const entries = logger.getEntries()
      expect(entries[0].sessionId).toBeUndefined()
      expect(entries[0].projectId).toBeUndefined()
    })
  })

  describe('Filtering', () => {
    it('should filter by level', () => {
      logger.debug('ui', 'Debug log')
      logger.info('ui', 'Info log')
      logger.warn('engine', 'Warn log')
      logger.error('simulation', 'Error log')

      logger.setFilters({ level: ['error'] })
      const entries = logger.getFilteredEntries()
      expect(entries).toHaveLength(1)
      expect(entries[0].level).toBe('error')
    })

    it('should filter by module', () => {
      logger.debug('ui', 'Debug log')
      logger.info('ui', 'Info log')
      logger.warn('engine', 'Warn log')
      logger.error('simulation', 'Error log')

      logger.setFilters({ modules: ['ui'] })
      const entries = logger.getFilteredEntries()
      expect(entries).toHaveLength(2)
      expect(entries.every(e => e.module === 'ui')).toBe(true)
    })

    it('should search in message', () => {
      logger.debug('ui', 'Debug log')
      logger.info('ui', 'Info log')
      logger.warn('engine', 'Warn log')
      logger.error('simulation', 'Error log')

      logger.setFilters({ search: 'Error' })
      const entries = logger.getFilteredEntries()
      expect(entries).toHaveLength(1)
      expect(entries[0].message).toContain('Error')
    })

    it('should clear filters', () => {
      logger.debug('ui', 'Debug log')
      logger.info('ui', 'Info log')
      logger.warn('engine', 'Warn log')
      logger.error('simulation', 'Error log')

      logger.setFilters({ level: ['error'] })
      logger.clearFilters()
      const entries = logger.getFilteredEntries()
      expect(entries).toHaveLength(4)
    })
  })

  describe('Statistics', () => {
    it('should compute stats', () => {
      logger.info('simulation', 'Test 1')
      logger.info('simulation', 'Test 2')
      logger.warn('engine', 'Test 3')
      logger.error('worker', 'Test 4')

      const stats = logger.getStats()
      expect(stats.total).toBe(4)
      expect(stats.byLevel.info).toBe(2)
      expect(stats.byLevel.warn).toBe(1)
      expect(stats.byLevel.error).toBe(1)
      expect(stats.byModule.simulation).toBe(2)
      expect(stats.byModule.engine).toBe(1)
      expect(stats.byModule.worker).toBe(1)
    })
  })

  describe('Export', () => {
    it('should export as JSON', () => {
      logger.info('ui', 'Test message')
      const json = logger.exportAsJSON()
      expect(json).toContain('Test message')
      expect(() => JSON.parse(json)).not.toThrow()
    })

    it('should export as CSV', () => {
      logger.info('ui', 'Test message')
      const csv = logger.exportAsCSV()
      expect(csv).toContain('timestamp,level,module,message')
      expect(csv).toContain('Test message')
    })
  })

  describe('Subscription', () => {
    it('should notify subscribers', () => {
      let notified = false
      logger.subscribe(() => { notified = true })
      logger.info('ui', 'Test')
      expect(notified).toBe(true)
    })

    it('should allow unsubscribing', () => {
      let callCount = 0
      const unsubscribe = logger.subscribe(() => { callCount++ })
      unsubscribe()
      logger.info('ui', 'Test 1')
      logger.info('ui', 'Test 2')
      expect(callCount).toBe(0)
    })
  })

  describe('Max entries', () => {
    it('should limit entries to MAX_ENTRIES', () => {
      for (let i = 0; i < 1100; i++) {
        logger.info('simulation', `Message ${i}`)
      }
      const entries = logger.getEntries()
      expect(entries.length).toBeLessThanOrEqual(1000)
    })
  })
})
