import { describe, it, expect } from 'vitest'
import { normalizeRecentMessages } from './recentMessages'

describe('normalizeRecentMessages', () => {
  it('keeps well-formed {role,text} entries', () => {
    expect(
      normalizeRecentMessages([
        { role: 'user', text: 'hi' },
        { role: 'assistant', text: 'hello' },
      ]),
    ).toEqual([
      { role: 'user', text: 'hi' },
      { role: 'assistant', text: 'hello' },
    ])
  })

  it('drops malformed entries and defaults a missing role', () => {
    expect(
      normalizeRecentMessages([
        null,
        'nope',
        { text: 'orphan' },
        { role: 'user' }, // no text -> dropped
      ]),
    ).toEqual([{ role: 'assistant', text: 'orphan' }])
  })

  it('returns [] for an empty tail', () => {
    expect(normalizeRecentMessages([])).toEqual([])
  })
})
