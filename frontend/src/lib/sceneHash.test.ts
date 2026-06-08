import { describe, it, expect } from 'vitest'
import { sceneHashFragment, withSceneHash } from './sceneHash'

describe('sceneHashFragment', () => {
  it('normalizes a #scene-N hash to a canonical fragment', () => {
    expect(sceneHashFragment('#scene-3')).toBe('#scene-3')
    expect(sceneHashFragment('#scene-12')).toBe('#scene-12')
  })

  it('accepts a hash without the leading #', () => {
    expect(sceneHashFragment('scene-4')).toBe('#scene-4')
  })

  it('ignores non-scene hashes so unrelated anchors are not forwarded', () => {
    // The run page uses run-section-* anchors for its own scroll-spy; those
    // must never leak into the deck iframe.
    expect(sceneHashFragment('#run-section-slides')).toBe('')
    expect(sceneHashFragment('#scene-')).toBe('')
    expect(sceneHashFragment('#scene-3-extra')).toBe('')
    expect(sceneHashFragment('#section-3')).toBe('')
  })

  it('returns empty for empty / null / undefined', () => {
    expect(sceneHashFragment('')).toBe('')
    expect(sceneHashFragment(null)).toBe('')
    expect(sceneHashFragment(undefined)).toBe('')
  })
})

describe('withSceneHash', () => {
  const base = '/w/abc/content?t=tok'

  it('appends a valid scene fragment to the content URL', () => {
    expect(withSceneHash(base, '#scene-3')).toBe('/w/abc/content?t=tok#scene-3')
  })

  it('leaves the URL untouched when there is no scene hash', () => {
    expect(withSceneHash(base, '')).toBe(base)
    expect(withSceneHash(base, '#run-section-video')).toBe(base)
    expect(withSceneHash(base, null)).toBe(base)
  })

  it('works on a URL with no query string', () => {
    expect(withSceneHash('/w/abc/content', 'scene-2')).toBe('/w/abc/content#scene-2')
  })
})
