import { describe, expect, it } from 'vitest'
import { sessionTargetLabel } from './sessionTargetLabel'

describe('sessionTargetLabel', () => {
  it('labels an agent session', () => {
    expect(sessionTargetLabel('Echo', '')).toBe('with Echo')
  })
  it('labels a project session by repo name', () => {
    expect(sessionTargetLabel(null, 'canopy-web')).toBe('canopy-web')
  })
  it('labels an agentless, projectless session', () => {
    expect(sessionTargetLabel(null, '')).toBe('no agent')
  })
})
