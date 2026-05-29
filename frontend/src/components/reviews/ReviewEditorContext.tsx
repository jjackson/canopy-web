/**
 * Context + provider for the review scene/feature editor.
 *
 * Pattern mirrors ace-web's videos/BeatEditorContext.tsx.
 * Consumers call useReviewEditor() to get:
 *   - state.buffer         (pending ops)
 *   - effectiveScenes      (applyReviewOps projection — pure, no mutation)
 *   - overallFeedback      (derived from the buffer's set-overall-feedback op)
 *   - isDirty              (buffer.length > 0)
 *   - dispatch             (append ops, undo, etc.)
 */

import {
  createContext,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react'
import { applyReviewOps, projectBuildOrder, type EffectiveScene } from './reviewApplyOps'
import {
  reviewEditorReducer,
  initialReviewEditorState,
  type ReviewEditorAction,
} from './reviewEditorReducer'
import type { ReviewEditorState, PendingReviewOp } from './reviewEditorTypes'
import type { ReviewNarrationItem } from '../../api/reviews'

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

interface ReviewEditorContextValue {
  state: ReviewEditorState
  effectiveScenes: EffectiveScene[]
  /** Current value of the overall_feedback field (from buffer or ''). */
  overallFeedback: string
  /**
   * Effective build order — ordered list of scene ids in the reviewer's chosen
   * tackle sequence. Derived from set-build-order ops, falling back to
   * initialBuildOrder from the request, then to narration order.
   * Already reconciled: added scenes are appended, deleted scenes are dropped.
   */
  buildOrder: string[]
  isDirty: boolean
  dispatch: (a: ReviewEditorAction) => void
}

const Ctx = createContext<ReviewEditorContextValue | null>(null)

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface Props {
  original: ReviewNarrationItem[]
  /** From request_json.build_order — null/undefined = absent, fall back to narration order. */
  initialBuildOrder?: string[] | null
  children: ReactNode
}

export function ReviewEditorProvider({ original, initialBuildOrder, children }: Props) {
  const [state, dispatch] = useReducer(
    reviewEditorReducer,
    undefined,
    () => initialReviewEditorState(original, initialBuildOrder ?? null),
  )

  const effectiveScenes = useMemo(
    () => applyReviewOps(state.original, state.buffer),
    [state.original, state.buffer],
  )

  const overallFeedback = useMemo(() => {
    // Last set-overall-feedback op in buffer wins.
    for (let i = state.buffer.length - 1; i >= 0; i--) {
      const op = state.buffer[i] as PendingReviewOp
      if (op.op === 'set-overall-feedback') return op.text
    }
    return ''
  }, [state.buffer])

  const buildOrder = useMemo(
    () => projectBuildOrder(state.original, state.buffer, state.initialBuildOrder, effectiveScenes),
    [state.original, state.buffer, state.initialBuildOrder, effectiveScenes],
  )

  const isDirty = state.buffer.length > 0

  const value: ReviewEditorContextValue = {
    state,
    effectiveScenes,
    overallFeedback,
    buildOrder,
    isDirty,
    dispatch,
  }

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useReviewEditor(): ReviewEditorContextValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useReviewEditor must be used inside <ReviewEditorProvider>')
  return v
}
