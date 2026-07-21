import { describe, it, expect } from 'vitest'
import { pairNarrationScenes, hasNarrativeChanges } from './narrativeScenePairing'
import type { DddNarration } from '../../api/ddd'

const scene = (id: string, text: string, extra: Partial<DddNarration> = {}): DddNarration => ({
  id,
  text,
  ...extra,
})

describe('pairNarrationScenes', () => {
  it('marks unchanged scenes (ignoring whitespace)', () => {
    const before = [scene('n1', 'The  study begins.')]
    const after = [scene('n1', 'The study begins.')]
    const pairs = pairNarrationScenes(before, after)
    expect(pairs).toHaveLength(1)
    expect(pairs[0].status).toBe('unchanged')
    expect(hasNarrativeChanges(pairs)).toBe(false)
  })

  it('marks changed scenes and keeps both texts', () => {
    const before = [scene('n1', 'measure the real effect')]
    const after = [scene('n1', 'measure differences in outcomes')]
    const pairs = pairNarrationScenes(before, after)
    expect(pairs[0].status).toBe('changed')
    expect(pairs[0].before).toBe('measure the real effect')
    expect(pairs[0].after).toBe('measure differences in outcomes')
    expect(hasNarrativeChanges(pairs)).toBe(true)
  })

  it('matches by id even when scenes are reordered', () => {
    const before = [scene('a', 'A'), scene('b', 'B')]
    const after = [scene('b', 'B'), scene('a', 'A2')]
    const pairs = pairNarrationScenes(before, after)
    // Output follows the after order: b first, then a.
    expect(pairs.map((p) => p.id)).toEqual(['b', 'a'])
    expect(pairs[0].status).toBe('unchanged')
    expect(pairs[1].status).toBe('changed')
  })

  it('flags added scenes (present only in after)', () => {
    const before = [scene('n1', 'one')]
    const after = [scene('n1', 'one'), scene('n2', 'brand new beat')]
    const pairs = pairNarrationScenes(before, after)
    expect(pairs[1].status).toBe('added')
    expect(pairs[1].before).toBeNull()
    expect(pairs[1].after).toBe('brand new beat')
  })

  it('flags removed scenes (present only in before) and appends them', () => {
    const before = [scene('n1', 'one'), scene('gone', 'dropped beat')]
    const after = [scene('n1', 'one')]
    const pairs = pairNarrationScenes(before, after)
    expect(pairs).toHaveLength(2)
    expect(pairs[1].status).toBe('removed')
    expect(pairs[1].before).toBe('dropped beat')
    expect(pairs[1].after).toBeNull()
  })

  it('falls back to positional pairing for id-less scenes', () => {
    const before = [{ text: 'first' }, { text: 'second' }]
    const after = [{ text: 'first' }, { text: 'second edited' }]
    const pairs = pairNarrationScenes(before, after)
    expect(pairs[0].status).toBe('unchanged')
    expect(pairs[1].status).toBe('changed')
  })
})
