import { describe, it, expect } from 'vitest'
import { relTime, isRecentlyActive, isRunning } from './relTime'

const NOW = Date.parse('2026-07-21T12:00:00Z')

describe('relTime', () => {
  it('formats buckets', () => {
    expect(relTime('2026-07-21T11:59:30Z', NOW)).toBe('just now')
    expect(relTime('2026-07-21T11:45:00Z', NOW)).toBe('15m ago')
    expect(relTime('2026-07-21T09:00:00Z', NOW)).toBe('3h ago')
    expect(relTime('2026-07-18T12:00:00Z', NOW)).toBe('3d ago')
  })
  it('returns "" for missing or unparseable input', () => {
    expect(relTime(null, NOW)).toBe('')
    expect(relTime(undefined, NOW)).toBe('')
    expect(relTime('not-a-date', NOW)).toBe('')
  })
})

describe('isRecentlyActive', () => {
  it('true within the window, false outside', () => {
    expect(isRecentlyActive('2026-07-21T11:59:00Z', NOW)).toBe(true) // 60s
    expect(isRecentlyActive('2026-07-21T11:57:00Z', NOW)).toBe(false) // 180s > 120s
    expect(isRecentlyActive(null, NOW)).toBe(false)
  })
})

describe('isRunning', () => {
  it('true within ~45s (accounts for report+poll lag), false outside', () => {
    expect(isRunning('2026-07-21T11:59:30Z', NOW)).toBe(true) // 30s ago
    expect(isRunning('2026-07-21T11:59:00Z', NOW)).toBe(false) // 60s ago
    expect(isRunning(null, NOW)).toBe(false)
  })
})
