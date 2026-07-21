import type { DddNarration } from '../../api/ddd'

/**
 * A before/after pairing of one scene across two narrative versions.
 *
 * `before` is the prior version's narration text (null when the scene is new);
 * `after` is the proposed version's text (null when the scene was removed).
 */
export interface NarrativeScenePair {
  id: string | null
  title: string | null
  before: string | null
  after: string | null
  status: 'unchanged' | 'changed' | 'added' | 'removed'
}

function keyOf(n: DddNarration, i: number): string {
  // Scenes reused across versions keep a stable `id` — match on it so a diff is
  // robust to reordering. Id-less scenes fall back to positional pairing.
  const id = n.id != null ? String(n.id).trim() : ''
  return id || `#${i}`
}

function textOf(n: DddNarration): string {
  return typeof n.text === 'string' ? n.text : ''
}

function norm(s: string): string {
  return s.replace(/\s+/g, ' ').trim()
}

/**
 * Pair the scenes of two narrative versions for a plain-language before/after.
 *
 * Output order follows the `after` (proposed) version — the story the reviewer is
 * being asked to approve — with any removed scenes appended at the end. Scenes are
 * matched by `id` where present (reorder-safe), else by position.
 */
export function pairNarrationScenes(
  before: DddNarration[],
  after: DddNarration[],
): NarrativeScenePair[] {
  const beforeByKey = new Map<string, DddNarration>()
  before.forEach((n, i) => {
    const k = keyOf(n, i)
    if (!beforeByKey.has(k)) beforeByKey.set(k, n)
  })

  const consumed = new Set<string>()
  const pairs: NarrativeScenePair[] = []

  after.forEach((n, i) => {
    const k = keyOf(n, i)
    const b = beforeByKey.get(k)
    if (b && !consumed.has(k)) {
      consumed.add(k)
      const beforeText = textOf(b)
      const afterText = textOf(n)
      pairs.push({
        id: n.id != null ? String(n.id) : null,
        title: n.title ?? b.title ?? null,
        before: beforeText,
        after: afterText,
        status: norm(beforeText) === norm(afterText) ? 'unchanged' : 'changed',
      })
    } else {
      pairs.push({
        id: n.id != null ? String(n.id) : null,
        title: n.title ?? null,
        before: null,
        after: textOf(n),
        status: 'added',
      })
    }
  })

  before.forEach((n, i) => {
    const k = keyOf(n, i)
    if (!consumed.has(k)) {
      pairs.push({
        id: n.id != null ? String(n.id) : null,
        title: n.title ?? null,
        before: textOf(n),
        after: null,
        status: 'removed',
      })
    }
  })

  return pairs
}

/** True when any scene differs between the two versions. */
export function hasNarrativeChanges(pairs: NarrativeScenePair[]): boolean {
  return pairs.some((p) => p.status !== 'unchanged')
}
