import { describe, expect, it } from 'vitest'
import { buildDispatchPrompt, canDispatch } from './dispatchPrompt'

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
