import { describe, it, expect } from 'vitest'
import { timeHashSeconds, withTimeFragment } from './timeHash'

describe('timeHashSeconds', () => {
  it('parses a #t=N hash into seconds', () => {
    expect(timeHashSeconds('#t=83')).toBe(83)
    expect(timeHashSeconds('#t=0')).toBe(0)
  })

  it('accepts decimals and a hash without the leading #', () => {
    expect(timeHashSeconds('#t=12.5')).toBe(12.5)
    expect(timeHashSeconds('t=7')).toBe(7)
  })

  it('ignores non-time hashes so unrelated anchors never seek the video', () => {
    expect(timeHashSeconds('#scene-3')).toBeNull()
    expect(timeHashSeconds('#t=')).toBeNull()
    expect(timeHashSeconds('#t=abc')).toBeNull()
    expect(timeHashSeconds('#t=-5')).toBeNull()
    expect(timeHashSeconds('#t=3&x=1')).toBeNull()
  })

  it('returns null for empty / null / undefined', () => {
    expect(timeHashSeconds('')).toBeNull()
    expect(timeHashSeconds(null)).toBeNull()
    expect(timeHashSeconds(undefined)).toBeNull()
  })
})

describe('withTimeFragment', () => {
  it('appends a media-fragment start time, preserving any query', () => {
    expect(withTimeFragment('/w/abc/content?t=tok', 83)).toBe('/w/abc/content?t=tok#t=83')
    expect(withTimeFragment('/w/abc/content', 12.5)).toBe('/w/abc/content#t=12.5')
  })
})
