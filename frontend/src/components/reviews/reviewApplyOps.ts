/**
 * Pure projection: given the original narration items + a buffer of ops,
 * returns a new array of EffectiveScene objects.
 *
 * Also exports projectBuildOrder() which derives the effective tackle sequence
 * from the op-buffer, falling back to the supplied initial order (or the
 * narration order when neither is available).
 *
 * - Deep-clones via JSON.parse/stringify (scenes are small).
 * - Never mutates the original.
 * - Ops are applied in buffer order; same-key ops already coalesced by
 *   the reducer, so each key appears at most once.
 */

import type {
  ReviewNarrationItem,
  ReviewFeature,
  ReviewPersona,
  ReviewWhyBrief,
} from '../../api/reviews'
import type { PendingReviewOp } from './reviewEditorTypes'

// ---------------------------------------------------------------------------
// Output shape — what the editor renders and the submit payload is built from.
// ---------------------------------------------------------------------------

export interface EffectiveFeature {
  id: string
  description: string
  verify: string
  feedback: string
  deleted: boolean
}

export interface EffectiveScene {
  id: string
  /** Story-beat title. Original scenes carry the spec title; falls back to
   * "Scene N" only when the backend sent no title. New scenes carry the
   * user-entered title. */
  title: string
  /** Persona key on screen this beat (DDD v3). Empty for new/unassigned scenes. */
  persona: string
  /** Spine id this beat grounds — joins to the why-brief grounding. Empty for new scenes. */
  provenance: string
  narration: string
  deleted: boolean
  features: EffectiveFeature[]
  feedback: string
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function applyReviewOps(
  original: ReviewNarrationItem[],
  ops: PendingReviewOp[],
): EffectiveScene[] {
  if (ops.length === 0) return originalToEffective(original)

  // Start from a deep clone of the original as EffectiveScene[]
  const scenes: EffectiveScene[] = JSON.parse(
    JSON.stringify(originalToEffective(original)),
  ) as EffectiveScene[]

  // Index for O(1) lookup
  const byId = new Map<string, EffectiveScene>()
  for (const s of scenes) byId.set(s.id, s)

  // Track insertion order for new scenes (append to end)
  let newSceneCounter = 0

  for (const op of ops) {
    switch (op.op) {
      case 'edit-narration': {
        const s = byId.get(op.sceneId)
        if (s) s.narration = op.text
        break
      }
      case 'edit-feature': {
        const s = byId.get(op.sceneId)
        if (!s) break
        const f = s.features.find((x) => x.id === op.featureId)
        if (f) {
          if (op.field === 'description') f.description = op.value
          else f.verify = op.value
        }
        break
      }
      case 'set-feature-feedback': {
        const s = byId.get(op.sceneId)
        if (!s) break
        const f = s.features.find((x) => x.id === op.featureId)
        if (f) f.feedback = op.text
        break
      }
      case 'add-feature': {
        const s = byId.get(op.sceneId)
        if (!s) break
        // Idempotent: only add if not already in list
        if (!s.features.find((x) => x.id === op.featureId)) {
          s.features.push({
            id: op.featureId,
            description: '',
            verify: '',
            feedback: '',
            deleted: false,
          })
        }
        break
      }
      case 'delete-feature': {
        const s = byId.get(op.sceneId)
        if (!s) break
        const f = s.features.find((x) => x.id === op.featureId)
        if (f) f.deleted = true
        break
      }
      case 'add-scene': {
        if (!byId.has(op.sceneId)) {
          newSceneCounter++
          const newScene: EffectiveScene = {
            id: op.sceneId,
            title: op.title,
            persona: '',
            provenance: '',
            narration: '',
            deleted: false,
            features: [],
            feedback: '',
          }
          scenes.push(newScene)
          byId.set(op.sceneId, newScene)
        }
        break
      }
      case 'delete-scene': {
        const s = byId.get(op.sceneId)
        if (s) s.deleted = true
        break
      }
      case 'set-scene-feedback': {
        const s = byId.get(op.sceneId)
        if (s) s.feedback = op.text
        break
      }
      case 'set-overall-feedback':
        // overall_feedback is handled separately by the caller; noop here.
        break
      case 'set-build-order':
        // build_order is handled separately by projectBuildOrder(); noop here.
        break
    }
  }

  // Suppress TS unused warning on counter (used for ordering new scenes)
  void newSceneCounter

  return scenes
}

// ---------------------------------------------------------------------------
// Build-order projection
// ---------------------------------------------------------------------------

/**
 * Derives the effective build order (a list of scene ids in tackle sequence).
 *
 * Rules:
 *  1. If the op-buffer contains a `set-build-order` op, its orderedSceneIds
 *     wins (last-write-wins via coalescing).
 *  2. Else fall back to `initialBuildOrder` (from request_json.build_order).
 *  3. Else fall back to the narration order (scene id array from `original`).
 *
 * After determining the base order, the result is reconciled against the
 * current effective scenes so that:
 *  - newly added scenes are appended to the end,
 *  - deleted scenes are dropped.
 *
 * @param original      The original narration items (never mutated).
 * @param ops           The pending op buffer.
 * @param initialBuildOrder  From request_json.build_order (null = absent).
 * @param effectiveScenes   The applyReviewOps() projection (used for reconcile).
 */
export function projectBuildOrder(
  original: ReviewNarrationItem[],
  ops: PendingReviewOp[],
  initialBuildOrder: string[] | null,
  effectiveScenes: EffectiveScene[],
): string[] {
  // Step 1 — find last set-build-order op in buffer (already coalesced to 1).
  let baseOrder: string[] | null = null
  for (let i = ops.length - 1; i >= 0; i--) {
    const op = ops[i]
    if (op.op === 'set-build-order') {
      baseOrder = op.orderedSceneIds
      break
    }
  }

  // Step 2 — fall back to initialBuildOrder.
  if (baseOrder === null) {
    baseOrder = initialBuildOrder ?? original.map((item) => item.id)
  }

  // Step 3 — reconcile: keep only ids that still exist (non-deleted) in
  // effectiveScenes, then append any new scenes not yet in the order.
  const activeIds = new Set(
    effectiveScenes.filter((s) => !s.deleted).map((s) => s.id),
  )
  const reconciled = baseOrder.filter((id) => activeIds.has(id))
  const alreadyOrdered = new Set(reconciled)
  for (const scene of effectiveScenes) {
    if (!scene.deleted && !alreadyOrdered.has(scene.id)) {
      reconciled.push(scene.id)
    }
  }
  return reconciled
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function originalToEffective(items: ReviewNarrationItem[]): EffectiveScene[] {
  return items.map((item) => ({
    id: item.id,
    title: item.title && item.title.trim() ? item.title : `Scene ${item.scene}`,
    persona: item.persona ?? '',
    provenance: item.provenance ?? '',
    narration: item.text,
    deleted: false,
    features: (item.features ?? []).map((f: ReviewFeature) => ({
      id: f.id,
      description: f.description,
      verify: f.verify ?? '',
      feedback: '',
      deleted: false,
    })),
    feedback: '',
  }))
}

// ---------------------------------------------------------------------------
// Persona projection — apply edit-persona ops over the original personas dict.
// ---------------------------------------------------------------------------

export type EffectivePersonas = Record<string, ReviewPersona>

export function projectPersonas(
  original: Record<string, ReviewPersona> | undefined,
  ops: PendingReviewOp[],
): EffectivePersonas {
  const personas: EffectivePersonas = JSON.parse(JSON.stringify(original ?? {}))
  for (const op of ops) {
    if (op.op !== 'edit-persona') continue
    const p = personas[op.key]
    if (!p) continue
    p[op.field] = op.value
  }
  return personas
}

// ---------------------------------------------------------------------------
// Why-brief projection — apply edit-why-* ops over the original why-brief.
// ---------------------------------------------------------------------------

export function projectWhyBrief(
  original: ReviewWhyBrief | undefined | null,
  ops: PendingReviewOp[],
): ReviewWhyBrief {
  const wb: ReviewWhyBrief = JSON.parse(
    JSON.stringify(original ?? { problem: '', spine: [], gaps: [] }),
  )
  for (const op of ops) {
    if (op.op === 'edit-why-problem') {
      wb.problem = op.value
    } else if (op.op === 'edit-why-spine') {
      const item = (wb.spine ?? []).find((s) => s.id === op.id)
      if (item) item[op.field] = op.value
    } else if (op.op === 'edit-why-gap') {
      const gap = (wb.gaps ?? []).find((g) => g.id === op.id)
      if (gap) gap[op.field] = op.value
    }
  }
  return wb
}
