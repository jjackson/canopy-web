import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  getReview,
  submitReview,
  type ReviewDetail,
  type ReviewDecision,
  type ReviewNarrationItem,
  type ReviewFeature,
  type ReviewSceneActionability,
  type ReviewSubmitPayload,
} from '../api/reviews'
import { walkthroughContentUrl } from '../api/walkthroughs'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Small badge for numeric scores (e.g. "4.2 / 5") */
function ScoreBadge({
  score,
  total = 5,
  tooltip,
}: {
  score: number
  total?: number
  tooltip?: string
}) {
  const formatted = Number.isInteger(score) ? String(score) : score.toFixed(1)
  return (
    <span
      title={tooltip}
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold bg-violet-500/20 text-violet-300 border border-violet-500/30 cursor-default select-none"
    >
      {formatted}
      <span className="text-violet-500 font-normal">/ {total}</span>
    </span>
  )
}

/** List of features for one narration chunk */
function FeatureList({
  features,
  sceneActionability,
}: {
  features: ReviewFeature[]
  sceneActionability?: ReviewSceneActionability
}) {
  if (features.length === 0) return null

  const missedIds = new Set(sceneActionability?.missed ?? [])

  return (
    <div className="mt-3 space-y-2">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">
        Features this scene commits to
      </p>
      <ul className="space-y-2">
        {features.map((f) => {
          const isMissed = missedIds.has(f.id)
          return (
            <li
              key={f.id}
              className={[
                'rounded border px-3 py-2 text-sm',
                isMissed
                  ? 'border-amber-500/30 bg-amber-500/5'
                  : 'border-stone-800 bg-stone-900/60',
              ].join(' ')}
            >
              <p className="text-stone-200 leading-snug">{f.description}</p>
              {f.verify && (
                <p className="mt-1 font-mono text-[11px] text-stone-500 leading-snug">
                  verify: {f.verify}
                </p>
              )}
              {isMissed && (
                <p className="mt-1.5 text-[11px] text-amber-400/80">
                  ⚠ eval flagged as under-specified
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** One narration chunk: editable textarea + features list + optional scene score */
interface NarrationCardProps {
  item: ReviewNarrationItem
  value: string
  onChange: (value: string) => void
  readOnly: boolean
  sceneActionability?: ReviewSceneActionability
}

function NarrationCard({
  item,
  value,
  onChange,
  readOnly,
  sceneActionability,
}: NarrationCardProps) {
  const features: ReviewFeature[] = item.features ?? []

  return (
    <div className="rounded-lg border border-stone-700 bg-stone-950 p-4 space-y-3">
      {/* Scene header row */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">
          Scene {item.scene}
        </span>
        {sceneActionability != null && (
          <ScoreBadge score={sceneActionability.score} tooltip="Scene actionability score (AI buildability estimate)" />
        )}
      </div>

      {/* Editable narration text */}
      <textarea
        className={[
          'w-full rounded border bg-stone-900 px-3 py-2 text-sm text-stone-200 resize-y min-h-[4rem]',
          'border-stone-700 focus:border-stone-500 focus:outline-none transition-colors',
          readOnly ? 'opacity-70 cursor-default' : '',
        ].join(' ')}
        value={value}
        onChange={(e) => !readOnly && onChange(e.target.value)}
        readOnly={readOnly}
        rows={3}
      />

      {/* Features */}
      {features.length > 0 && (
        <FeatureList
          features={features}
          sceneActionability={sceneActionability}
        />
      )}
    </div>
  )
}

/**
 * The approve / redraft decision block.
 *
 * Replaces the old generic DecisionGroup for the "narrative-verdict" decision.
 * Two clearly-labeled action buttons, each with a one-line explanation.
 */
interface NarrativeVerdictProps {
  decision: ReviewDecision
  chosen: string
  onChange: (value: string) => void
  readOnly: boolean
}

function NarrativeVerdictControl({
  decision,
  chosen,
  onChange,
  readOnly,
}: NarrativeVerdictProps) {
  const LABELS: Record<string, { label: string; explanation: string; accent: string }> = {
    approve: {
      label: 'Approve & continue',
      explanation:
        'Lock this narrative as the build plan (including any edits I made); proceed to build the features.',
      accent: 'emerald',
    },
    redraft: {
      label: 'Send back to re-draft',
      explanation:
        'The framing/approach is wrong — re-author the narrative from scratch.',
      accent: 'amber',
    },
  }

  return (
    <div className="rounded-lg border border-stone-700 bg-stone-900 p-4 space-y-3">
      <p className="text-sm text-stone-200 leading-snug">{decision.prompt}</p>
      <div className="flex flex-col sm:flex-row gap-3">
        {decision.options.map((opt) => {
          const meta = LABELS[opt] ?? { label: opt, explanation: '', accent: 'stone' }
          const isSelected = chosen === opt
          const accent = meta.accent

          const selectedStyles: Record<string, string> = {
            emerald:
              'border-emerald-500/60 bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/30',
            amber:
              'border-amber-500/60 bg-amber-500/15 text-amber-200 ring-1 ring-amber-500/30',
            stone:
              'border-stone-500 bg-stone-700 text-stone-100 ring-1 ring-stone-500/30',
          }
          const unselectedStyles =
            'border-stone-700 text-stone-400 hover:border-stone-500 hover:text-stone-200 hover:bg-stone-800/50'

          return (
            <button
              key={opt}
              type="button"
              disabled={readOnly}
              onClick={() => !readOnly && onChange(opt)}
              className={[
                'flex-1 text-left rounded-lg border px-4 py-3 transition-all',
                isSelected
                  ? (selectedStyles[accent] ?? selectedStyles.stone)
                  : unselectedStyles,
                readOnly ? 'pointer-events-none opacity-80' : 'cursor-pointer',
              ].join(' ')}
            >
              <p className="font-semibold text-sm leading-tight">{meta.label}</p>
              {meta.explanation && (
                <p
                  className={[
                    'mt-1 text-xs leading-snug',
                    isSelected ? 'opacity-80' : 'text-stone-500',
                  ].join(' ')}
                >
                  {meta.explanation}
                </p>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

/** Generic radio-button decision group for non-narrative-verdict decisions */
interface DecisionGroupProps {
  decision: ReviewDecision
  chosen: string
  onChange: (value: string) => void
  readOnly: boolean
}

function DecisionGroup({ decision, chosen, onChange, readOnly }: DecisionGroupProps) {
  const classLabel = decision.class ? decision.class.replace(/_/g, ' ') : ''

  return (
    <div className="rounded-lg border border-stone-700 bg-stone-900 p-4">
      <div className="flex items-start gap-2 mb-3">
        {classLabel && (
          <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider bg-orange-500/20 text-orange-300 border border-orange-500/30">
            {classLabel}
          </span>
        )}
        <p className="text-sm text-stone-200 leading-snug">{decision.prompt}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {decision.options.map((opt) => {
          const isSelected = chosen === opt
          const isRecommended = decision.recommended === opt
          return (
            <label
              key={opt}
              className={[
                'flex items-center gap-2 cursor-pointer rounded px-3 py-1.5 text-sm border transition-colors',
                isSelected
                  ? 'bg-orange-500/20 border-orange-500/50 text-orange-200'
                  : 'border-stone-700 text-stone-400 hover:border-stone-500 hover:text-stone-200',
                readOnly ? 'pointer-events-none opacity-80' : '',
              ].join(' ')}
            >
              <input
                type="radio"
                name={`decision-${decision.id}`}
                value={opt}
                checked={isSelected}
                onChange={() => !readOnly && onChange(opt)}
                className="sr-only"
                disabled={readOnly}
              />
              {opt}
              {isRecommended && !isSelected && (
                <span className="text-[10px] text-stone-500">(recommended)</span>
              )}
              {isRecommended && isSelected && (
                <span className="text-[10px] text-orange-400/70">(recommended)</span>
              )}
            </label>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ReviewPage() {
  const { id } = useParams<{ id: string }>()

  // Read ?t= from query string — same pattern as WalkthroughViewerPage
  const params = new URLSearchParams(window.location.search)
  const shareToken = params.get('t') ?? null

  const [review, setReview] = useState<ReviewDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  // Local state for decision choices (keyed by decision.id)
  const [choices, setChoices] = useState<Record<string, string>>({})
  // Local state for narration edits (keyed by narration item id)
  const [narrationEdits, setNarrationEdits] = useState<Record<string, string>>({})

  // Collapsed/expanded state for the autonomous audit section
  const [auditOpen, setAuditOpen] = useState(false)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getReview(id, shareToken)
      .then((d) => {
        if (cancelled) return
        setReview(d)
        // Initialise local decision choices from recommended values
        const initialChoices: Record<string, string> = {}
        for (const dec of d.request_json.decisions ?? []) {
          initialChoices[dec.id] = dec.recommended ?? dec.options[0] ?? ''
        }
        setChoices(initialChoices)
        // Initialise narration edits from existing text
        const initialNarration: Record<string, string> = {}
        for (const n of d.request_json.narration ?? []) {
          initialNarration[n.id] = n.text
        }
        setNarrationEdits(initialNarration)
        // If already resolved, show the read-only resolved state immediately
        if (d.status === 'resolved') setSubmitted(true)
      })
      .catch((e) => !cancelled && setError(String(e?.message ?? e)))
    return () => {
      cancelled = true
    }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps
  // (shareToken is stable for the page lifetime — intentionally omitted from deps)

  async function handleSubmit() {
    if (!id || !review) return
    setBusy(true)
    setError(null)
    try {
      const payload: ReviewSubmitPayload = {
        decisions: choices,
        narration_edits: narrationEdits,
      }
      const updated = await submitReview(id, payload, shareToken)
      setReview(updated)
      setSubmitted(true)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  // -------------------------------------------------------------------
  // Loading / error states
  // -------------------------------------------------------------------

  if (error && !review) {
    return (
      <div className="max-w-4xl mx-auto p-6 text-red-500">
        <p className="font-semibold">Error loading review</p>
        <p className="text-sm mt-1 text-red-400">{error}</p>
      </div>
    )
  }

  if (!review) {
    return <div className="max-w-4xl mx-auto p-6 text-stone-500">Loading…</div>
  }

  const req = review.request_json
  const isResolved = review.status === 'resolved' || submitted
  const decisions: ReviewDecision[] = req.decisions ?? []
  const narration: ReviewNarrationItem[] = req.narration ?? []
  const autonomousAudit: string[] = req.autonomous_audit ?? []
  const actionability = req.actionability ?? null
  const overallScore = actionability?.overall_score ?? null
  const perScene = actionability?.per_scene ?? {}

  // Separate narrative-verdict decision from other decisions
  const narrativeVerdictDecision = decisions.find((d) => d.id === 'narrative-verdict') ?? null
  const otherDecisions = decisions.filter((d) => d.id !== 'narrative-verdict')

  // -------------------------------------------------------------------
  // Video / iframe embed — mirrors WalkthroughViewerPage mechanism
  // -------------------------------------------------------------------

  let videoElement: React.ReactNode = null
  if (req.video?.walkthrough_id) {
    const contentSrc = walkthroughContentUrl(req.video.walkthrough_id, shareToken)
    videoElement = (
      <iframe
        src={contentSrc}
        title="Review cut"
        sandbox="allow-scripts allow-same-origin"
        className="w-full h-[60vh]"
      />
    )
  } else if (req.video?.url) {
    videoElement = (
      <video
        src={req.video.url}
        controls
        className="w-full max-h-[60vh] bg-black"
      />
    )
  } else {
    videoElement = (
      <div className="flex items-center justify-center h-40 text-stone-500 text-sm">
        No cut available yet
      </div>
    )
  }

  // Helper to get the resolved decision value for a decision id
  function resolvedChoice(decId: string): string {
    if (isResolved && review?.response_json?.decisions) {
      return review.response_json.decisions[decId] ?? choices[decId] ?? ''
    }
    return choices[decId] ?? ''
  }

  // -------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 space-y-8">
      {/* Header */}
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3 flex-wrap">
          <div>
            <h1 className="text-xl font-semibold text-stone-100">Review gate: {req.gate}</h1>
            <p className="text-sm text-stone-500 mt-0.5">Run {req.run_id}</p>
          </div>
          {overallScore != null && (
            <div className="mt-0.5">
              <ScoreBadge
                score={overallScore}
                tooltip="Actionability score — how confidently an AI could build this narrative as written (out of 5)"
              />
              <p className="text-[10px] text-stone-600 mt-0.5 text-center">Actionability</p>
            </div>
          )}
        </div>
        <span
          className={[
            'shrink-0 rounded px-2 py-0.5 text-xs font-medium',
            isResolved
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              : 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
          ].join(' ')}
        >
          {isResolved ? 'Resolved' : 'Needs your input'}
        </span>
      </header>

      {/* Current cut */}
      <section>
        <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-2">
          Current cut
        </h2>
        <div className="rounded-lg border border-stone-700 bg-black overflow-hidden">
          {videoElement}
        </div>
      </section>

      {/* Narrative verdict — the primary decision, shown before narration */}
      {narrativeVerdictDecision && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-3">
            {isResolved ? 'Decision (submitted)' : 'Your decision'}
          </h2>
          <NarrativeVerdictControl
            decision={narrativeVerdictDecision}
            chosen={resolvedChoice('narrative-verdict')}
            onChange={(val) => setChoices((prev) => ({ ...prev, 'narrative-verdict': val }))}
            readOnly={isResolved}
          />
        </section>
      )}

      {/* Other decisions (non-narrative-verdict) */}
      {otherDecisions.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-3">
            {isResolved ? 'Additional decisions (submitted)' : 'Additional decisions'}
          </h2>
          <div className="space-y-3">
            {otherDecisions.map((dec) => (
              <DecisionGroup
                key={dec.id}
                decision={dec}
                chosen={resolvedChoice(dec.id)}
                onChange={(val) => setChoices((prev) => ({ ...prev, [dec.id]: val }))}
                readOnly={isResolved}
              />
            ))}
          </div>
        </section>
      )}

      {/* Narration cards — editable text + features + per-scene scores */}
      {narration.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-3">
            {isResolved ? 'Narration (submitted)' : 'Narration — edit inline'}
          </h2>
          <div className="space-y-4">
            {narration.map((item) => {
              const editedValue = isResolved && review.response_json?.narration_edits
                ? (review.response_json.narration_edits[item.id] ?? narrationEdits[item.id] ?? item.text)
                : (narrationEdits[item.id] ?? item.text)
              const sceneScore = perScene[item.id] ?? undefined
              return (
                <NarrationCard
                  key={item.id}
                  item={item}
                  value={editedValue}
                  onChange={(val) =>
                    setNarrationEdits((prev) => ({ ...prev, [item.id]: val }))
                  }
                  readOnly={isResolved}
                  sceneActionability={sceneScore}
                />
              )
            })}
          </div>
        </section>
      )}

      {/* Autonomous audit — collapsed by default */}
      {autonomousAudit.length > 0 && (
        <section>
          <button
            type="button"
            onClick={() => setAuditOpen((o) => !o)}
            className="flex items-center gap-2 text-sm text-stone-500 hover:text-stone-300 transition-colors"
          >
            <svg
              className={[
                'h-4 w-4 transition-transform',
                auditOpen ? 'rotate-90' : '',
              ].join(' ')}
              viewBox="0 0 12 12"
              fill="none"
            >
              <path
                d="M4 3l4 3-4 3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            What I did autonomously ({autonomousAudit.length} step
            {autonomousAudit.length === 1 ? '' : 's'})
          </button>
          {auditOpen && (
            <ul className="mt-3 space-y-1.5 pl-4 border-l border-stone-800">
              {autonomousAudit.map((entry, i) => (
                <li key={i} className="text-sm text-stone-400">
                  {entry}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* Action / resolved state */}
      {error && (
        <p className="text-sm text-red-400 rounded border border-red-500/30 bg-red-500/10 px-3 py-2">
          {error}
        </p>
      )}

      {isResolved ? (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
          <p className="text-sm text-emerald-300 font-medium">
            Review resolved — the loop will continue.
          </p>
          {review.resolved_at && (
            <p className="text-xs text-emerald-500 mt-0.5">
              Submitted {new Date(review.resolved_at).toLocaleString()}
            </p>
          )}
        </div>
      ) : (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={busy || decisions.some((d) => !choices[d.id])}
            className={[
              'px-6 py-2 rounded font-medium text-sm transition-colors',
              busy
                ? 'bg-stone-700 text-stone-400 cursor-not-allowed'
                : 'bg-orange-500 hover:bg-orange-400 text-white',
            ].join(' ')}
          >
            {busy ? 'Submitting…' : 'Submit review'}
          </button>
        </div>
      )}
    </div>
  )
}
