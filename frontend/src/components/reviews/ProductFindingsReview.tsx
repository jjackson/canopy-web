/**
 * ProductFindingsReview — the first-class review surface for
 * `gate === 'product_findings'`.
 *
 * A run-child review (NOT a narrative version). It embeds the iteration clip at
 * the top, then renders one CARD per finding cluster: severity / fix_kind /
 * route / scene chips, the suggested fix, inline evidence thumbnails, a
 * "Watch @ m:ss" button that seeks the embedded clip to the evidence's
 * video_t, a deck deep-link, and a 3-way implement / skip / defer control.
 *
 * The footer carries an overall proceed/discuss choice + notes + Submit. Submit
 * is disabled until every cluster has a decision; on submit it produces the
 * response_json shape from CONTRACT-product-findings-review.md and hands it to
 * the caller (which reuses the existing review-submit endpoint).
 */
import { useCallback, useMemo, useRef, useState } from 'react'
import type {
  FindingsCluster,
  FindingsDecision,
  FindingsEvidence,
  FindingsFixKind,
  FindingsOverall,
  FindingsSeverity,
  ProductFindingsRequestJson,
  ProductFindingsResponseJson,
} from '../../api/reviews'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Seconds → "m:ss". */
function fmtTime(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}

/** mechanical → implement; options/redesign → no default (force a pick). */
function defaultDecisionFor(fixKind?: FindingsFixKind): FindingsDecision | '' {
  return fixKind === 'mechanical' ? 'implement' : ''
}

const SEVERITY_STYLES: Record<FindingsSeverity, string> = {
  high: 'bg-red-500/15 text-red-300 border-red-500/30',
  medium: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  low: 'bg-stone-500/15 text-stone-300 border-stone-600/40',
}

const DECISION_META: Record<
  FindingsDecision,
  { label: string; hint: string; accent: string }
> = {
  implement: {
    label: 'Implement',
    hint: 'Apply this fix in the next iteration.',
    accent: 'emerald',
  },
  skip: {
    label: 'Skip',
    hint: "Don't act on this finding.",
    accent: 'stone',
  },
  defer: {
    label: 'Defer',
    hint: 'Revisit later — not this iteration.',
    accent: 'sky',
  },
}

const DECISION_SELECTED: Record<string, string> = {
  emerald: 'border-emerald-500/60 bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/30',
  sky: 'border-sky-500/60 bg-sky-500/15 text-sky-200 ring-1 ring-sky-500/30',
  stone: 'border-stone-500 bg-stone-700 text-stone-100 ring-1 ring-stone-500/30',
}

// ---------------------------------------------------------------------------
// Chip
// ---------------------------------------------------------------------------

function Chip({
  children,
  className,
  title,
}: {
  children: React.ReactNode
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={[
        'inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-medium select-none border',
        className ?? 'bg-stone-800/60 text-stone-300 border-stone-700',
      ].join(' ')}
    >
      {children}
    </span>
  )
}

// ---------------------------------------------------------------------------
// 3-way decision control
// ---------------------------------------------------------------------------

function DecisionControl({
  clusterId,
  chosen,
  readOnly,
  onChange,
}: {
  clusterId: string
  chosen: FindingsDecision | ''
  readOnly: boolean
  onChange: (value: FindingsDecision) => void
}) {
  const options: FindingsDecision[] = ['implement', 'skip', 'defer']
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="sr-only">Decision for {clusterId}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => {
          const meta = DECISION_META[opt]
          const isSelected = chosen === opt
          return (
            <label
              key={opt}
              title={meta.hint}
              className={[
                'flex items-center gap-2 cursor-pointer rounded border px-3 py-1.5 text-sm transition-colors',
                isSelected
                  ? DECISION_SELECTED[meta.accent] ?? DECISION_SELECTED.stone
                  : 'border-stone-700 text-stone-400 hover:border-stone-500 hover:text-stone-200',
                readOnly ? 'pointer-events-none opacity-80' : '',
              ].join(' ')}
            >
              <input
                type="radio"
                name={`finding-${clusterId}`}
                value={opt}
                checked={isSelected}
                onChange={() => !readOnly && onChange(opt)}
                disabled={readOnly}
                className="sr-only"
              />
              {meta.label}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

// ---------------------------------------------------------------------------
// Evidence row — thumbnail + watch + deck deep-link
// ---------------------------------------------------------------------------

function EvidenceCard({
  evidence,
  deckUrl,
  onWatch,
}: {
  evidence: FindingsEvidence
  deckUrl?: string
  onWatch: (videoT: number) => void
}) {
  const deckHref = deckUrl ? `${deckUrl}${evidence.deck_anchor ?? ''}` : null
  return (
    <figure className="flex flex-col gap-1.5 rounded-lg border border-stone-800 bg-stone-900/60 p-2">
      {evidence.thumb ? (
        <img
          src={evidence.thumb}
          alt={`Scene ${evidence.scene} evidence`}
          className="w-full rounded border border-stone-800 bg-black object-contain"
          loading="lazy"
        />
      ) : (
        <div className="flex h-24 items-center justify-center rounded border border-stone-800 text-[11px] text-stone-600">
          No thumbnail
        </div>
      )}
      <figcaption className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-stone-600">
          Scene {evidence.scene}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onWatch(evidence.video_t)}
            className="rounded border border-stone-700 px-2 py-0.5 text-[11px] text-stone-300 hover:border-stone-500 hover:text-stone-100 transition-colors"
            title={`Seek the clip to ${fmtTime(evidence.video_t)}`}
          >
            ▶ Watch @ {fmtTime(evidence.video_t)}
          </button>
          {deckHref && (
            <a
              href={deckHref}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded border border-stone-700 px-2 py-0.5 text-[11px] text-stone-400 hover:border-stone-500 hover:text-stone-200 transition-colors"
              title="Open this scene in the deck"
            >
              Deck ↗
            </a>
          )}
        </div>
      </figcaption>
    </figure>
  )
}

// ---------------------------------------------------------------------------
// Cluster card
// ---------------------------------------------------------------------------

function ClusterCard({
  cluster,
  index,
  chosen,
  readOnly,
  deckUrl,
  onChoose,
  onWatch,
}: {
  cluster: FindingsCluster
  index: number
  chosen: FindingsDecision | ''
  readOnly: boolean
  deckUrl?: string
  onChoose: (value: FindingsDecision) => void
  onWatch: (videoT: number) => void
}) {
  const evidence = cluster.evidence ?? []
  const scenes = cluster.scenes ?? []
  return (
    <div className="rounded-lg border border-stone-700 bg-stone-950 p-4 space-y-3">
      {/* Chips */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold text-stone-500 tabular-nums">
          #{index + 1}
        </span>
        {cluster.severity && (
          <Chip className={SEVERITY_STYLES[cluster.severity]} title="Severity">
            {cluster.severity}
          </Chip>
        )}
        {cluster.fix_kind && (
          <Chip title="Fix kind">{cluster.fix_kind}</Chip>
        )}
        {cluster.route && (
          <Chip className="bg-violet-500/15 text-violet-300 border-violet-500/30" title="Route">
            {cluster.route}
          </Chip>
        )}
        {scenes.length > 0 && (
          <Chip title="Scenes referenced">
            {scenes.length === 1 ? `scene ${scenes[0]}` : `scenes ${scenes.join(', ')}`}
          </Chip>
        )}
        {typeof cluster.count === 'number' && cluster.count > 1 && (
          <Chip title="Occurrences">×{cluster.count}</Chip>
        )}
      </div>

      {/* Title */}
      <h3 className="text-sm font-medium text-stone-100 leading-snug">{cluster.title}</h3>

      {/* Suggested fix */}
      {cluster.suggested_fix && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-stone-600 mb-0.5">
            Suggested fix
          </p>
          <p className="text-sm text-stone-300 leading-relaxed">{cluster.suggested_fix}</p>
        </div>
      )}

      {/* Evidence */}
      {evidence.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-stone-600 mb-1.5">Evidence</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {evidence.map((ev, i) => (
              <EvidenceCard
                key={`${ev.scene}-${i}`}
                evidence={ev}
                deckUrl={deckUrl}
                onWatch={onWatch}
              />
            ))}
          </div>
        </div>
      )}

      {/* Decision */}
      <div className="pt-1">
        <p className="text-[10px] uppercase tracking-wider text-stone-600 mb-1.5">
          {readOnly ? 'Decision' : 'What should we do?'}
        </p>
        <DecisionControl
          clusterId={cluster.id}
          chosen={chosen}
          readOnly={readOnly}
          onChange={onChoose}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface ProductFindingsReviewProps {
  review: ProductFindingsRequestJson
  /** Submit handler — receives the assembled response_json. */
  onSubmit: (response: ProductFindingsResponseJson) => Promise<void> | void
  /** Read-only once resolved (or for anonymous viewers). */
  readOnly?: boolean
  /** Pre-filled response when the review is already resolved. */
  resolved?: ProductFindingsResponseJson | null
  /** Stamp shown in the resolved banner. */
  resolvedAt?: string | null
}

export function ProductFindingsReview({
  review,
  onSubmit,
  readOnly = false,
  resolved = null,
  resolvedAt = null,
}: ProductFindingsReviewProps) {
  const clusters = useMemo(() => review.clusters ?? [], [review.clusters])
  const videoRef = useRef<HTMLVideoElement | null>(null)

  // Per-cluster decision. Resolved reviews show the submitted decisions; live
  // reviews seed mechanical → implement and leave the rest blank (force a pick).
  const [decisions, setDecisions] = useState<Record<string, FindingsDecision | ''>>(() => {
    const initial: Record<string, FindingsDecision | ''> = {}
    for (const c of clusters) {
      initial[c.id] = resolved?.decisions?.[c.id] ?? defaultDecisionFor(c.fix_kind)
    }
    return initial
  })

  const [overall, setOverall] = useState<FindingsOverall | ''>(resolved?.overall ?? '')
  const [notes, setNotes] = useState<string>(resolved?.notes ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Seek the embedded clip; fall back to opening the clip at #t when no element.
  const handleWatch = useCallback(
    (videoT: number) => {
      const el = videoRef.current
      if (el) {
        try {
          el.currentTime = videoT
          el.scrollIntoView({ behavior: 'smooth', block: 'start' })
          void el.play().catch(() => {})
          return
        } catch {
          // fall through to the deep-link fallback
        }
      }
      if (review.video?.url) {
        window.open(`${review.video.url}#t=${videoT}`, '_blank', 'noopener,noreferrer')
      }
    },
    [review.video],
  )

  const allDecided = useMemo(
    () => clusters.length > 0 && clusters.every((c) => !!decisions[c.id]),
    [clusters, decisions],
  )
  const canSubmit = !busy && !readOnly && allDecided && !!overall

  const handleSubmit = useCallback(async () => {
    if (!overall) return
    setBusy(true)
    setError(null)
    try {
      const cleanDecisions: Record<string, FindingsDecision> = {}
      for (const c of clusters) {
        const d = decisions[c.id]
        if (d) cleanDecisions[c.id] = d
      }
      await onSubmit({ decisions: cleanDecisions, overall, notes })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [clusters, decisions, overall, notes, onSubmit])

  const summary = review.summary
  const undecidedCount = clusters.filter((c) => !decisions[c.id]).length

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 space-y-6">
      {/* Header */}
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-stone-100">
            Findings review
            {review.feature ? <span className="text-stone-400"> · {review.feature}</span> : null}
            {review.iteration != null ? (
              <span className="text-stone-500"> · iteration {review.iteration}</span>
            ) : null}
          </h1>
          <p className="text-sm text-stone-500 mt-0.5">{review.run_id}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {summary?.verdict && (
            <Chip
              className={
                /fail/i.test(summary.verdict)
                  ? 'bg-red-500/15 text-red-300 border-red-500/30'
                  : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
              }
              title="Eval verdict"
            >
              {summary.verdict}
            </Chip>
          )}
          {summary?.concept_score != null && (
            <Chip
              className="bg-violet-500/15 text-violet-300 border-violet-500/30"
              title="Concept eval score"
            >
              concept {summary.concept_score}
            </Chip>
          )}
          {summary?.user_score != null && (
            <Chip
              className="bg-violet-500/15 text-violet-300 border-violet-500/30"
              title="User-artifact eval score"
            >
              user {summary.user_score}
            </Chip>
          )}
          <span
            className={[
              'shrink-0 rounded px-2 py-0.5 text-xs font-medium',
              readOnly
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
            ].join(' ')}
          >
            {readOnly ? 'Resolved' : 'Needs your input'}
          </span>
        </div>
      </header>

      {/* Embedded iteration clip */}
      {review.video?.url ? (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-2">
            Iteration clip
          </h2>
          <div className="rounded-lg border border-stone-700 bg-black overflow-hidden">
            <video
              ref={videoRef}
              src={review.video.url}
              controls
              preload="metadata"
              className="w-full max-h-[60vh] bg-black"
            />
          </div>
          <p className="text-xs text-stone-600 mt-2">
            Each finding's “Watch @ m:ss” seeks this clip to that scene.
          </p>
        </section>
      ) : null}

      {/* Clusters */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider">
          Findings ({clusters.length})
        </h2>
        {clusters.length === 0 ? (
          <p className="text-sm text-stone-500 rounded border border-stone-800 bg-stone-900/40 px-3 py-2">
            No findings in this review.
          </p>
        ) : (
          clusters.map((cluster, i) => (
            <ClusterCard
              key={cluster.id}
              cluster={cluster}
              index={i}
              chosen={decisions[cluster.id] ?? ''}
              readOnly={readOnly}
              deckUrl={review.deck_url}
              onChoose={(value) =>
                setDecisions((prev) => ({ ...prev, [cluster.id]: value }))
              }
              onWatch={handleWatch}
            />
          ))
        )}
      </section>

      {/* Error */}
      {error && (
        <p className="text-sm text-red-400 rounded border border-red-500/30 bg-red-500/10 px-3 py-2">
          {error}
        </p>
      )}

      {/* Footer — overall + notes + submit */}
      <section className="space-y-4 border-t border-stone-800 pt-6">
        <div>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-2">
            {readOnly ? 'Overall (submitted)' : 'Overall'}
          </h2>
          <div className="flex flex-col sm:flex-row gap-3">
            {(['proceed', 'discuss'] as const).map((opt) => {
              const isSelected = overall === opt
              const accent = opt === 'proceed' ? 'emerald' : 'amber'
              const selectedStyles: Record<string, string> = {
                emerald:
                  'border-emerald-500/60 bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/30',
                amber:
                  'border-amber-500/60 bg-amber-500/15 text-amber-200 ring-1 ring-amber-500/30',
              }
              return (
                <button
                  key={opt}
                  type="button"
                  disabled={readOnly}
                  onClick={() => !readOnly && setOverall(opt)}
                  className={[
                    'flex-1 text-left rounded-lg border px-4 py-3 transition-all',
                    isSelected
                      ? selectedStyles[accent]
                      : 'border-stone-700 text-stone-400 hover:border-stone-500 hover:text-stone-200 hover:bg-stone-800/50',
                    readOnly ? 'pointer-events-none opacity-80' : 'cursor-pointer',
                  ].join(' ')}
                >
                  <p className="font-semibold text-sm leading-tight">
                    {opt === 'proceed' ? 'Proceed' : 'Discuss'}
                  </p>
                  <p
                    className={[
                      'mt-1 text-xs leading-snug',
                      isSelected ? 'opacity-80' : 'text-stone-500',
                    ].join(' ')}
                  >
                    {opt === 'proceed'
                      ? 'Apply the implement decisions and continue the loop.'
                      : "Let's talk before acting on these findings."}
                  </p>
                </button>
              )
            })}
          </div>
        </div>

        <div>
          <label
            htmlFor="findings-notes"
            className="block text-sm font-semibold text-stone-400 uppercase tracking-wider mb-2"
          >
            Notes
          </label>
          <textarea
            id="findings-notes"
            value={notes}
            readOnly={readOnly}
            onChange={(e) => !readOnly && setNotes(e.target.value)}
            rows={3}
            placeholder="Optional notes for the iteration…"
            className={[
              'w-full rounded border bg-stone-900 px-3 py-2 text-sm text-stone-200 min-h-[3rem]',
              'border-stone-700 focus:border-stone-500 focus:outline-none transition-colors',
              readOnly ? 'opacity-70 cursor-default' : '',
            ].join(' ')}
          />
        </div>

        {readOnly ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
            <p className="text-sm text-emerald-300 font-medium">
              Findings review resolved — the loop will continue.
            </p>
            {resolvedAt && (
              <p className="text-xs text-emerald-500 mt-0.5">
                Submitted {new Date(resolvedAt).toLocaleString()}
              </p>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-end gap-1">
            {!allDecided && (
              <p className="text-[11px] text-amber-300/90 text-right">
                {undecidedCount} finding{undecidedCount === 1 ? '' : 's'} still need a decision.
              </p>
            )}
            {allDecided && !overall && (
              <p className="text-[11px] text-amber-300/90 text-right">
                Pick an overall outcome to submit.
              </p>
            )}
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={!canSubmit}
              className={[
                'px-6 py-2 rounded font-medium text-sm transition-colors',
                !canSubmit
                  ? 'bg-stone-700 text-stone-400 cursor-not-allowed'
                  : 'bg-orange-500 hover:bg-orange-400 text-white',
              ].join(' ')}
            >
              {busy ? 'Submitting…' : 'Submit findings review'}
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
