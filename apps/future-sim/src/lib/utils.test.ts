import { describe, it, expect } from 'vitest'
import { cn, clamp, formatNumber, formatPercent, generateId, quantile, normalRandom } from './utils'

describe('Utils', () => {
  describe('cn', () => {
    it('should merge class names', () => {
      expect(cn('foo', 'bar')).toBe('foo bar')
    })

    it('should handle conditional classes', () => {
      expect(cn('foo', false && 'bar', 'baz')).toBe('foo baz')
    })
  })

  describe('clamp', () => {
    it('should clamp value within range', () => {
      expect(clamp(5, 0, 10)).toBe(5)
      expect(clamp(-5, 0, 10)).toBe(0)
      expect(clamp(15, 0, 10)).toBe(10)
    })
  })

  describe('formatNumber', () => {
    it('should format thousands', () => {
      expect(formatNumber(1000)).toBe('1.0K')
      expect(formatNumber(1500)).toBe('1.5K')
    })

    it('should format millions', () => {
      expect(formatNumber(1000000)).toBe('1.0M')
      expect(formatNumber(2500000)).toBe('2.5M')
    })

    it('should format small numbers', () => {
      expect(formatNumber(100)).toBe('100')
    })
  })

  describe('formatPercent', () => {
    it('should format as percentage', () => {
      expect(formatPercent(0.5)).toBe('50.0%')
      expect(formatPercent(0.123)).toBe('12.3%')
      expect(formatPercent(1)).toBe('100.0%')
    })
  })

  describe('generateId', () => {
    it('should generate unique ids', () => {
      const id1 = generateId()
      const id2 = generateId()
      expect(id1).not.toBe(id2)
      expect(id1.length).toBeGreaterThan(5)
    })
  })

  describe('quantile', () => {
    it('should calculate median', () => {
      const sorted = [1, 2, 3, 4, 5]
      expect(quantile(sorted, 0.5)).toBe(3)
    })

    it('should calculate percentile', () => {
      const sorted = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
      expect(quantile(sorted, 0.9)).toBe(9.1)
    })

    it('should handle empty array', () => {
      expect(quantile([], 0.5)).toBe(0)
    })
  })

  describe('normalRandom', () => {
    it('should generate values around mean', () => {
      const values: number[] = []
      for (let i = 0; i < 1000; i++) {
        values.push(normalRandom(100, 10))
      }
      const avg = values.reduce((a, b) => a + b, 0) / values.length
      expect(avg).toBeGreaterThan(90)
      expect(avg).toBeLessThan(110)
    })
  })
})
