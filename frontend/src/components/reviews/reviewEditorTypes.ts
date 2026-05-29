/**
 * Op-buffer types for the review scene/feature editor.
 *
 * Pattern mirrors ace-web's videos/types.ts:
 *  - PendingReviewOp = one typed edit that has not yet been saved
 *  - opCoalesceKey   = last-write-wins key per field (edit-narration per scene,
 *                      edit-feature per scene+feature+field, etc.)
 *  - ReviewEditorState  = original review + buffer + save status
 */

import type { ReviewNarrationItem } from '../../api/reviews'

// ---------------------------------------------------------------------------
// Op types
// ---------------------------------------------------------------------------

export type PendingReviewOp =
  | { op: 'edit-narration'; sceneId: string; text: string }
  | { op: 'edit-feature'; sceneId: string; featureId: string; field: 'description' | 'verify'; value: string }
  | { op: 'set-feature-feedback'; sceneId: string; featureId: string; text: string }
  | { op: 'add-feature'; sceneId: string; featureId: string }   // featureId = 'new-<n>'
  | { op: 'delete-feature'; sceneId: string; featureId: string }
  | { op: 'add-scene'; sceneId: string; title: string }          // sceneId = 'new-<n>'
  | { op: 'delete-scene'; sceneId: string }
  | { op: 'set-scene-feedback'; sceneId: string; text: string }
  | { op: 'set-overall-feedback'; text: string }

/** Coalescing key: same key → last op wins (in-place replacement in buffer). */
export function opCoalesceKey(op: PendingReviewOp): string {
  switch (op.op) {
    case 'edit-narration':
      return `edit-narration:${op.sceneId}`
    case 'edit-feature':
      return `edit-feature:${op.sceneId}:${op.featureId}:${op.field}`
    case 'set-feature-feedback':
      return `set-feature-feedback:${op.sceneId}:${op.featureId}`
    case 'add-feature':
      // Each add-feature is unique (different featureId), so key by featureId.
      return `add-feature:${op.sceneId}:${op.featureId}`
    case 'delete-feature':
      return `delete-feature:${op.sceneId}:${op.featureId}`
    case 'add-scene':
      return `add-scene:${op.sceneId}`
    case 'delete-scene':
      return `delete-scene:${op.sceneId}`
    case 'set-scene-feedback':
      return `set-scene-feedback:${op.sceneId}`
    case 'set-overall-feedback':
      return 'set-overall-feedback'
  }
}

// ---------------------------------------------------------------------------
// Editor state
// ---------------------------------------------------------------------------

export interface ReviewEditorState {
  /** The original review request narration (never mutated). */
  original: ReviewNarrationItem[]
  /** Buffer of pending ops — applied in order by applyReviewOps(). */
  buffer: PendingReviewOp[]
  saveState:
    | { status: 'idle' }
    | { status: 'saving' }
    | { status: 'saved' }
    | { status: 'error'; message: string }
}
