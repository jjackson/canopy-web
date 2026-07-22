import { describe, expect, it } from 'vitest'

import { agentsForKind, firstChoiceCount, ordinal } from './runnerPriority'
import type { AgentOut } from '@/api/agents'

// AgentOut has many fields; the helper only reads slug/name/runner_preference.
const agent = (slug: string, runner_preference: string[] | null): AgentOut =>
  ({ slug, name: slug, runner_preference } as unknown as AgentOut)

describe('agentsForKind', () => {
  it('ranks agents by the position of the kind in their preference', () => {
    const agents = [
      agent('a', ['cloud', 'emdash']), // cloud rank 1
      agent('b', ['emdash', 'cloud']), // cloud rank 2
    ]
    const { ranked } = agentsForKind(agents, 'cloud')
    expect(ranked.map((r) => [r.agent.slug, r.rank])).toEqual([
      ['a', 1],
      ['b', 2],
    ])
  })

  it('sorts ranked agents ascending by rank regardless of input order', () => {
    const agents = [
      agent('b', ['emdash', 'cloud']), // rank 2
      agent('a', ['cloud']), // rank 1
    ]
    const { ranked } = agentsForKind(agents, 'cloud')
    expect(ranked.map((r) => r.agent.slug)).toEqual(['a', 'b'])
  })

  it('treats an empty preference as accepts-all, not ranked', () => {
    const { ranked, acceptsAll } = agentsForKind([agent('a', [])], 'cloud')
    expect(ranked).toEqual([])
    expect(acceptsAll.map((x) => x.slug)).toEqual(['a'])
  })

  it('treats a null/absent preference as accepts-all', () => {
    const { acceptsAll } = agentsForKind([agent('a', null)], 'cloud')
    expect(acceptsAll.map((x) => x.slug)).toEqual(['a'])
  })

  it('excludes agents whose non-empty preference omits the kind', () => {
    const { ranked, acceptsAll } = agentsForKind([agent('a', ['emdash'])], 'cloud')
    expect(ranked).toEqual([])
    expect(acceptsAll).toEqual([])
  })
})

describe('firstChoiceCount', () => {
  it('counts only agents whose #1 kind matches', () => {
    const agents = [
      agent('a', ['cloud', 'emdash']),
      agent('b', ['cloud']),
      agent('c', ['emdash', 'cloud']), // cloud is 2nd — not counted
      agent('d', []), // no preference — not counted
    ]
    expect(firstChoiceCount(agents, 'cloud')).toBe(2)
  })
})

describe('ordinal', () => {
  it('formats common ordinals', () => {
    expect(ordinal(1)).toBe('1st')
    expect(ordinal(2)).toBe('2nd')
    expect(ordinal(3)).toBe('3rd')
    expect(ordinal(4)).toBe('4th')
  })
  it('handles the 11-13 teens exception', () => {
    expect(ordinal(11)).toBe('11th')
    expect(ordinal(12)).toBe('12th')
    expect(ordinal(13)).toBe('13th')
    expect(ordinal(21)).toBe('21st')
  })
})
