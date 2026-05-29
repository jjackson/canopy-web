/**
 * Pure projection: given the original narration items + a buffer of ops,
 * returns a new array of EffectiveScene objects.
 *
 * - Deep-clones via JSON.parse/stringify (scenes are small).
 * - Never mutates the original.
 * - Ops are applied in buffer order; same-key ops already coalesced by
 *   the reducer, so each key appears at most once.
 */

import type { ReviewNarrationItem, ReviewFeature } from '../../api/reviews'
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
  /** 'new' scenes carry a user-editable title; original scenes use "Scene N". */
  title: string
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
    }
  }

  // Suppress TS unused warning on counter (used for ordering new scenes)
  void newSceneCounter

  return scenes
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function originalToEffective(items: ReviewNarrationItem[]): EffectiveScene[] {
  return items.map((item) => ({
    id: item.id,
    title: `Scene ${item.scene}`,
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
