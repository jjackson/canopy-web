/**
 * Reducer for the review scene/feature editor op-buffer.
 *
 * Pattern mirrors ace-web's videos/editorReducer.ts.
 */

import type { ReviewNarrationItem } from '../../api/reviews'
import type { PendingReviewOp, ReviewEditorState } from './reviewEditorTypes'
import { opCoalesceKey } from './reviewEditorTypes'

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export type ReviewEditorAction =
  | { type: 'APPEND_OP'; op: PendingReviewOp }
  | { type: 'UNDO_LAST_OP' }
  | { type: 'CLEAR_BUFFER' }
  | { type: 'SAVE_START' }
  | { type: 'SAVE_OK' }
  | { type: 'SAVE_ERROR'; message: string }
  | { type: 'SAVE_IDLE' }

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

export function initialReviewEditorState(
  original: ReviewNarrationItem[],
): ReviewEditorState {
  return { original, buffer: [], saveState: { status: 'idle' } }
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

export function reviewEditorReducer(
  state: ReviewEditorState,
  action: ReviewEditorAction,
): ReviewEditorState {
  switch (action.type) {
    case 'APPEND_OP': {
      const key = opCoalesceKey(action.op)
      const existingIdx = state.buffer.findIndex((o) => opCoalesceKey(o) === key)
      if (existingIdx >= 0) {
        const next = state.buffer.slice()
        next[existingIdx] = action.op
        return { ...state, buffer: next }
      }
      return { ...state, buffer: [...state.buffer, action.op] }
    }
    case 'UNDO_LAST_OP': {
      if (state.buffer.length === 0) return state
      return { ...state, buffer: state.buffer.slice(0, -1) }
    }
    case 'CLEAR_BUFFER':
      return { ...state, buffer: [] }
    case 'SAVE_START':
      return { ...state, saveState: { status: 'saving' } }
    case 'SAVE_OK':
      return { ...state, saveState: { status: 'saved' } }
    case 'SAVE_ERROR':
      return { ...state, saveState: { status: 'error', message: action.message } }
    case 'SAVE_IDLE':
      return { ...state, saveState: { status: 'idle' } }
  }
}
