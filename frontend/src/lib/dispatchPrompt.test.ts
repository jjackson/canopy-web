import { describe, expect, it } from 'vitest'
import { buildDispatchPrompt, canDispatch, phoneThreadKey } from './dispatchPrompt'

describe('buildDispatchPrompt', () => {
  it('builds a namespaced command with args', () => {
    expect(buildDispatchPrompt('echo', 'story-ideation', 'bednets')).toBe(
      '/echo:story-ideation bednets',
    )
  })

  it('drops the trailing space when a skill takes no args', () => {
    expect(buildDispatchPrompt('echo', 'story-ideation', '')).toBe('/echo:story-ideation')
    expect(buildDispatchPrompt('echo', 'story-ideation', '   ')).toBe('/echo:story-ideation')
  })

  it('sends a free prompt verbatim when no skill is picked', () => {
    expect(buildDispatchPrompt('echo', '', 'summarize the week')).toBe('summarize the week')
  })

  it('trims args so a stray space never reaches the session', () => {
    expect(buildDispatchPrompt('echo', 'x', '  y  ')).toBe('/echo:x y')
    expect(buildDispatchPrompt('echo', '', '  hello  ')).toBe('hello')
  })
})

describe('canDispatch', () => {
  it('requires both an agent and a non-empty prompt', () => {
    expect(canDispatch('echo', '/echo:turn')).toBe(true)
    expect(canDispatch('', '/echo:turn')).toBe(false)
    expect(canDispatch('echo', '')).toBe(false)
    expect(canDispatch('echo', '   ')).toBe(false)
  })
})

describe('phoneThreadKey', () => {
  it('is stable per user+target so dispatches continue one session', () => {
    const a = phoneThreadKey('jj@dimagi.com', 'canopy-web')
    const b = phoneThreadKey('jj@dimagi.com', 'canopy-web')
    expect(a).toBe(b)
    expect(a).toBe('phone:jj@dimagi.com:canopy-web')
  })

  it('separates users and targets into distinct threads', () => {
    expect(phoneThreadKey('jj@dimagi.com', 'canopy-web')).not.toBe(
      phoneThreadKey('other@dimagi.com', 'canopy-web'),
    )
    expect(phoneThreadKey('jj@dimagi.com', 'canopy-web')).not.toBe(
      phoneThreadKey('jj@dimagi.com', 'ace-web'),
    )
  })
})
