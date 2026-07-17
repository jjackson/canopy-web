import { describe, expect, it } from 'vitest'

import { mergeEvents } from './useLiveTurn'
import type { TurnEventFrame } from '@/api/types.ws'

const ev = (seq: number, text = ''): TurnEventFrame => ({
  seq,
  kind: 'assistant',
  payload: { text },
  ts: '2026-07-16T00:00:00Z',
})

describe('mergeEvents', () => {
  it('appends new events in seq order', () => {
    const out = mergeEvents([ev(1)], [ev(2), ev(3)])
    expect(out.map((e) => e.seq)).toEqual([1, 2, 3])
  })

  it('de-dupes by seq (replay + live overlap is idempotent)', () => {
    const out = mergeEvents([ev(1), ev(2)], [ev(2), ev(3)])
    expect(out.map((e) => e.seq)).toEqual([1, 2, 3])
  })

  it('sorts out-of-order arrivals', () => {
    const out = mergeEvents([], [ev(3), ev(1), ev(2)])
    expect(out.map((e) => e.seq)).toEqual([1, 2, 3])
  })

  it('does not mutate the previous array', () => {
    const prev = [ev(1)]
    mergeEvents(prev, [ev(2)])
    expect(prev.map((e) => e.seq)).toEqual([1])
  })
})
