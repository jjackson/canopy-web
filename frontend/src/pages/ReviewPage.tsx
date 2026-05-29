import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  getReview,
  submitReview,
  type ReviewDetail,
  type ReviewDecision,
  type ReviewSceneActionability,
  type ReviewSubmitPayload,
  type ReviewSubmittedScene,
  type ReviewPersona,
  type ReviewWhyBrief,
} from '../api/reviews'
import { walkthroughContentUrl } from '../api/walkthroughs'
import {
  ReviewEditorProvider,
  useReviewEditor,
} from '../components/reviews/ReviewEditorContext'

// ---------------------------------------------------------------------------
// Small utility components
// ---------------------------------------------------------------------------

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

function DirtyBadge({ isDirty }: { isDirty: boolean }) {
  if (!isDirty) return null
  return (
    <span className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
      Edited
    </span>
  )
}

function PersonaChip({ persona, dim = false }: { persona: ReviewPersona; dim?: boolean }) {
  return (
    <span
      title={`${persona.name} — ${persona.role}`}
      className={[
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium select-none',
        dim ? 'border-stone-700 text-stone-400' : 'border-stone-600 text-stone-200',
      ].join(' ')}
    >
      <span
        className="inline-block h-2 w-2 rounded-full shrink-0"
        style={{ backgroundColor: persona.color || '#78716c' }}
      />
      {persona.name}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Decision tiles
// ---------------------------------------------------------------------------

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
// Feature row — editable description + verify + optional feedback
// ---------------------------------------------------------------------------

interface FeatureRowProps {
  feature: {
    id: string
    description: string
    verify: string
    feedback: string
    deleted: boolean
  }
  readOnly: boolean
  isMissed: boolean
  onEdit: (field: 'description' | 'verify', value: string) => void
  onFeedback: (text: string) => void
  onDelete: () => void
}

function FeatureRow({
  feature,
  readOnly,
  isMissed,
  onEdit,
  onFeedback,
  onDelete,
}: FeatureRowProps) {
  if (feature.deleted) return null

  return (
    <li
      className={[
        'rounded border px-3 py-2 space-y-2',
        isMissed
          ? 'border-amber-500/30 bg-amber-500/5'
          : 'border-stone-800 bg-stone-900/60',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">
          Feature
        </p>
        {!readOnly && (
          <button
            type="button"
            onClick={onDelete}
            title="Delete feature"
            className="text-stone-600 hover:text-red-400 transition-colors text-xs"
          >
            ✕
          </button>
        )}
      </div>

      {/* description */}
      <textarea
        className={[
          'w-full rounded border bg-stone-900 px-2 py-1.5 text-sm text-stone-200 resize-y min-h-[2.5rem]',
          'border-stone-700 focus:border-stone-500 focus:outline-none transition-colors',
          readOnly ? 'opacity-70 cursor-default' : '',
        ].join(' ')}
        value={feature.description}
        onChange={(e) => !readOnly && onEdit('description', e.target.value)}
        readOnly={readOnly}
        placeholder="Description"
        rows={2}
      />

      {/* verify */}
      <input
        type="text"
        className={[
          'w-full rounded border bg-stone-900 px-2 py-1.5 font-mono text-[11px] text-stone-400',
          'border-stone-700 focus:border-stone-500 focus:outline-none transition-colors',
          readOnly ? 'opacity-70 cursor-default' : '',
        ].join(' ')}
        value={feature.verify}
        onChange={(e) => !readOnly && onEdit('verify', e.target.value)}
        readOnly={readOnly}
        placeholder="verify: how to confirm"
      />

      {isMissed && (
        <p className="text-[11px] text-amber-400/80">⚠ eval flagged as under-specified</p>
      )}

      {/* optional feedback */}
      {!readOnly && (
        <input
          type="text"
          className="w-full rounded border bg-stone-900 px-2 py-1.5 text-[11px] text-stone-400 border-stone-700 focus:border-stone-500 focus:outline-none transition-colors"
          value={feature.feedback}
          onChange={(e) => onFeedback(e.target.value)}
          placeholder="Feedback on this feature (optional)"
        />
      )}
      {readOnly && feature.feedback && (
        <p className="text-[11px] text-stone-500 italic">Feedback: {feature.feedback}</p>
      )}
    </li>
  )
}

// ---------------------------------------------------------------------------
// Scene card — narration + features + add-feature + delete-scene + per-scene feedback
// ---------------------------------------------------------------------------

interface SceneCardProps {
  scene: {
    id: string
    title: string
    persona: string
    narration: string
    deleted: boolean
    features: Array<{
      id: string
      description: string
      verify: string
      feedback: string
      deleted: boolean
    }>
    feedback: string
  }
  sceneNumber?: number
  persona?: ReviewPersona
  readOnly: boolean
  sceneActionability?: ReviewSceneActionability
  onEditNarration: (text: string) => void
  onEditFeature: (featureId: string, field: 'description' | 'verify', value: string) => void
  onFeatureFeedback: (featureId: string, text: string) => void
  onDeleteFeature: (featureId: string) => void
  onAddFeature: () => void
  onDeleteScene: () => void
  onSceneFeedback: (text: string) => void
}

function SceneCard({
  scene,
  sceneNumber,
  persona,
  readOnly,
  sceneActionability,
  onEditNarration,
  onEditFeature,
  onFeatureFeedback,
  onDeleteFeature,
  onAddFeature,
  onDeleteScene,
  onSceneFeedback,
}: SceneCardProps) {
  if (scene.deleted) return null

  const missedIds = new Set(sceneActionability?.missed ?? [])
  const activeFeatures = scene.features.filter((f) => !f.deleted)

  return (
    <div className="rounded-lg border border-stone-700 bg-stone-950 p-4 space-y-3">
      {/* Scene header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {sceneNumber != null && (
            <span className="text-[11px] font-semibold text-stone-500 tabular-nums shrink-0">
              Scene {sceneNumber}
            </span>
          )}
          {persona && <PersonaChip persona={persona} />}
          <span className="text-sm font-medium text-stone-100">{scene.title}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {sceneActionability != null && (
            <ScoreBadge
              score={sceneActionability.score}
              tooltip="Scene actionability score (AI buildability estimate)"
            />
          )}
          {!readOnly && (
            <button
              type="button"
              onClick={onDeleteScene}
              title="Delete scene"
              className="text-stone-600 hover:text-red-400 transition-colors text-xs px-2 py-0.5 rounded border border-stone-700 hover:border-red-500/40"
            >
              Delete scene
            </button>
          )}
        </div>
      </div>

      {/* Editable narration */}
      <textarea
        className={[
          'w-full rounded border bg-stone-900 px-3 py-2 text-sm text-stone-200 resize-y min-h-[4rem]',
          'border-stone-700 focus:border-stone-500 focus:outline-none transition-colors',
          readOnly ? 'opacity-70 cursor-default' : '',
        ].join(' ')}
        value={scene.narration}
        onChange={(e) => !readOnly && onEditNarration(e.target.value)}
        readOnly={readOnly}
        rows={3}
        placeholder="Scene narration…"
      />

      {/* Features list */}
      {(activeFeatures.length > 0 || !readOnly) && (
        <div className="space-y-2">
          {activeFeatures.length > 0 && (
            <>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">
                Features this scene commits to
              </p>
              <ul className="space-y-2">
                {scene.features.map((f) => (
                  <FeatureRow
                    key={f.id}
                    feature={f}
                    readOnly={readOnly}
                    isMissed={missedIds.has(f.id)}
                    onEdit={(field, value) => onEditFeature(f.id, field, value)}
                    onFeedback={(text) => onFeatureFeedback(f.id, text)}
                    onDelete={() => onDeleteFeature(f.id)}
                  />
                ))}
              </ul>
            </>
          )}
          {!readOnly && (
            <button
              type="button"
              onClick={onAddFeature}
              className="mt-1 text-xs text-stone-500 hover:text-stone-300 border border-dashed border-stone-700 hover:border-stone-500 rounded px-3 py-1.5 transition-colors"
            >
              + Add feature
            </button>
          )}
        </div>
      )}

      {/* Per-scene feedback */}
      {!readOnly && (
        <input
          type="text"
          className="w-full rounded border bg-stone-900 px-3 py-1.5 text-xs text-stone-400 border-stone-700 focus:border-stone-500 focus:outline-none transition-colors"
          value={scene.feedback}
          onChange={(e) => onSceneFeedback(e.target.value)}
          placeholder="Scene-level feedback (optional)"
        />
      )}
      {readOnly && scene.feedback && (
        <p className="text-xs text-stone-500 italic">Feedback: {scene.feedback}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Build Sequence Section — reorder the tackle sequence independent of video order
// ---------------------------------------------------------------------------

interface BuildSequenceSectionProps {
  effectiveScenes: Array<{ id: string; title: string; deleted: boolean }>
  /** Effective build order — ordered list of scene ids from the op-buffer projection. */
  buildOrder: string[]
  readOnly: boolean
  onReorder: (orderedIds: string[]) => void
  /** Submitted build order (readOnly mode). */
  resolvedBuildOrder: string[] | null
}

function BuildSequenceSection({
  effectiveScenes,
  buildOrder,
  readOnly,
  onReorder,
  resolvedBuildOrder,
}: BuildSequenceSectionProps) {
  // Build a lookup from scene id → title (only active scenes)
  const sceneById = new Map(
    effectiveScenes
      .filter((s) => !s.deleted)
      .map((s) => [s.id, s.title]),
  )

  // The order to display — in readOnly mode prefer the submitted order.
  const displayOrder = readOnly && resolvedBuildOrder ? resolvedBuildOrder : buildOrder

  // Filter to only scenes that still exist (guard against stale ids in stored data).
  const orderedScenes = displayOrder
    .filter((id) => sceneById.has(id))
    .map((id) => ({ id, title: sceneById.get(id) ?? id }))

  function move(index: number, direction: 'up' | 'down') {
    const next = orderedScenes.map((s) => s.id)
    const target = direction === 'up' ? index - 1 : index + 1
    if (target < 0 || target >= next.length) return
    // Swap
    ;[next[index], next[target]] = [next[target], next[index]]
    onReorder(next)
  }

  if (orderedScenes.length === 0) return null

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider">
          Build sequence
        </h2>
        {!readOnly && (
          <p className="text-xs text-stone-500 mt-0.5">
            Order you'll tackle these when building — independent of the video order. Drag or use
            the arrows to rearrange.
          </p>
        )}
      </div>

      <ol className="space-y-2">
        {orderedScenes.map((scene, idx) => {
          // Also look up this scene's video (narrative) position for context.
          const narrativePos = effectiveScenes.filter((s) => !s.deleted).findIndex((s) => s.id === scene.id)
          return (
            <li
              key={scene.id}
              className="flex items-center gap-3 rounded-lg border border-stone-700 bg-stone-900 px-3 py-2"
            >
              {/* Build # badge */}
              <span className="shrink-0 w-6 h-6 rounded-full bg-orange-500/20 text-orange-300 border border-orange-500/30 flex items-center justify-center text-xs font-semibold select-none">
                {idx + 1}
              </span>

              {/* Title + narrative position hint */}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-stone-200 truncate">{scene.title}</p>
                {narrativePos !== idx && (
                  <p className="text-[10px] text-stone-600">
                    video position: {narrativePos + 1}
                  </p>
                )}
              </div>

              {/* Up / Down controls — edit mode only */}
              {!readOnly && (
                <div className="shrink-0 flex gap-1">
                  <button
                    type="button"
                    onClick={() => move(idx, 'up')}
                    disabled={idx === 0}
                    title="Move earlier in build sequence"
                    className={[
                      'rounded border px-1.5 py-0.5 text-xs transition-colors',
                      idx === 0
                        ? 'border-stone-800 text-stone-700 cursor-default'
                        : 'border-stone-700 text-stone-400 hover:border-stone-500 hover:text-stone-200',
                    ].join(' ')}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => move(idx, 'down')}
                    disabled={idx === orderedScenes.length - 1}
                    title="Move later in build sequence"
                    className={[
                      'rounded border px-1.5 py-0.5 text-xs transition-colors',
                      idx === orderedScenes.length - 1
                        ? 'border-stone-800 text-stone-700 cursor-default'
                        : 'border-stone-700 text-stone-400 hover:border-stone-500 hover:text-stone-200',
                    ].join(' ')}
                  >
                    ↓
                  </button>
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Personas section — the cast, visible + editable
// ---------------------------------------------------------------------------

function inputCls(readOnly: boolean): string {
  return [
    'w-full rounded border bg-stone-900 px-2.5 py-1.5 text-sm text-stone-200',
    'border-stone-700 focus:border-stone-500 focus:outline-none transition-colors',
    readOnly ? 'opacity-70 cursor-default' : '',
  ].join(' ')
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <span className="block text-[10px] uppercase tracking-wider text-stone-600 mb-0.5">{children}</span>
}

function PersonasSection({
  personas,
  readOnly,
  onEdit,
}: {
  personas: Record<string, ReviewPersona>
  readOnly: boolean
  onEdit: (key: string, field: 'name' | 'org' | 'role' | 'intro', value: string) => void
}) {
  const keys = Object.keys(personas)
  if (keys.length === 0) return null
  return (
    <section>
      <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-3">
        Personas
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {keys.map((key) => {
          const p = personas[key]
          return (
            <div key={key} className="rounded-lg border border-stone-700 bg-stone-950 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded-full shrink-0"
                  style={{ backgroundColor: p.color || '#78716c' }}
                />
                <span className="text-xs text-stone-600">persona: {key}</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <FieldLabel>Name</FieldLabel>
                  <input
                    className={inputCls(readOnly)}
                    value={p.name}
                    readOnly={readOnly}
                    onChange={(e) => !readOnly && onEdit(key, 'name', e.target.value)}
                  />
                </div>
                <div>
                  <FieldLabel>Org</FieldLabel>
                  <input
                    className={inputCls(readOnly)}
                    value={p.org ?? ''}
                    readOnly={readOnly}
                    placeholder="e.g. Dimagi"
                    onChange={(e) => !readOnly && onEdit(key, 'org', e.target.value)}
                  />
                </div>
              </div>
              <div>
                <FieldLabel>Role</FieldLabel>
                <input
                  className={inputCls(readOnly)}
                  value={p.role}
                  readOnly={readOnly}
                  onChange={(e) => !readOnly && onEdit(key, 'role', e.target.value)}
                />
              </div>
              <div>
                <FieldLabel>Intro</FieldLabel>
                <textarea
                  className={inputCls(readOnly) + ' resize-y min-h-[3rem]'}
                  value={p.intro}
                  readOnly={readOnly}
                  rows={2}
                  onChange={(e) => !readOnly && onEdit(key, 'intro', e.target.value)}
                />
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Why-brief section — the grounding doc, visible + editable
// ---------------------------------------------------------------------------

function WhyBriefSection({
  whyBrief,
  readOnly,
  onEditProblem,
  onEditSpine,
  onEditGap,
}: {
  whyBrief: ReviewWhyBrief
  readOnly: boolean
  onEditProblem: (value: string) => void
  onEditSpine: (id: string, field: 'claim' | 'rationale', value: string) => void
  onEditGap: (id: string, field: 'detail' | 'proposed_action', value: string) => void
}) {
  const spine = whyBrief.spine ?? []
  const gaps = whyBrief.gaps ?? []
  if (!whyBrief.problem && spine.length === 0 && gaps.length === 0) return null
  return (
    <section>
      <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-1">
        Why this matters (grounding)
      </h2>
      <p className="text-xs text-stone-600 mb-3">
        The why-brief grounds the demo. Editable here; ids / status / type are structural and fixed.
      </p>
      <div className="rounded-lg border border-stone-700 bg-stone-950 p-4 space-y-4">
        <div>
          <FieldLabel>Problem</FieldLabel>
          <textarea
            className={inputCls(readOnly) + ' resize-y min-h-[4rem]'}
            value={whyBrief.problem ?? ''}
            readOnly={readOnly}
            rows={3}
            onChange={(e) => !readOnly && onEditProblem(e.target.value)}
          />
        </div>

        {spine.length > 0 && (
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Spine</p>
            {spine.map((item) => (
              <div key={item.id} className="rounded border border-stone-800 p-3 space-y-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-stone-400">{item.id}</span>
                  {item.status && (
                    <span className="rounded bg-stone-800 px-1.5 py-0.5 text-stone-400">{item.status}</span>
                  )}
                </div>
                <div>
                  <FieldLabel>Claim</FieldLabel>
                  <textarea
                    className={inputCls(readOnly) + ' resize-y min-h-[3rem]'}
                    value={item.claim}
                    readOnly={readOnly}
                    rows={2}
                    onChange={(e) => !readOnly && onEditSpine(item.id, 'claim', e.target.value)}
                  />
                </div>
                <div>
                  <FieldLabel>Rationale</FieldLabel>
                  <textarea
                    className={inputCls(readOnly) + ' resize-y min-h-[3rem]'}
                    value={item.rationale ?? ''}
                    readOnly={readOnly}
                    rows={2}
                    onChange={(e) => !readOnly && onEditSpine(item.id, 'rationale', e.target.value)}
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {gaps.length > 0 && (
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Gaps</p>
            {gaps.map((gap) => (
              <div key={gap.id} className="rounded border border-stone-800 p-3 space-y-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-stone-400">{gap.id}</span>
                  {gap.type && (
                    <span className="rounded bg-amber-500/15 text-amber-300 px-1.5 py-0.5">{gap.type}</span>
                  )}
                  {gap.claim_ref && <span className="text-stone-600">→ {gap.claim_ref}</span>}
                </div>
                <div>
                  <FieldLabel>Detail</FieldLabel>
                  <textarea
                    className={inputCls(readOnly) + ' resize-y min-h-[3rem]'}
                    value={gap.detail}
                    readOnly={readOnly}
                    rows={2}
                    onChange={(e) => !readOnly && onEditGap(gap.id, 'detail', e.target.value)}
                  />
                </div>
                <div>
                  <FieldLabel>Proposed action</FieldLabel>
                  <textarea
                    className={inputCls(readOnly) + ' resize-y min-h-[3rem]'}
                    value={gap.proposed_action}
                    readOnly={readOnly}
                    rows={2}
                    onChange={(e) => !readOnly && onEditGap(gap.id, 'proposed_action', e.target.value)}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Inner editor — has access to the ReviewEditor context
// Owns all user interaction + submit logic.
// ---------------------------------------------------------------------------

interface ReviewEditorInnerProps {
  review: ReviewDetail
  readOnly: boolean
  /** Called after a successful submit with the updated review */
  onResolved: (updated: ReviewDetail) => void
}

function ReviewEditorInner({ review, readOnly, onResolved }: ReviewEditorInnerProps) {
  const {
    effectiveScenes,
    effectivePersonas,
    effectiveWhyBrief,
    overallFeedback,
    buildOrder,
    isDirty,
    dispatch,
  } = useReviewEditor()

  const shareToken = useRef(new URLSearchParams(window.location.search).get('t')).current

  const newFeatureCounterRef = useRef(0)
  const newSceneCounterRef = useRef(0)

  // Active tab — reflected in the URL (?tab=cuts) so it's shareable/linkable.
  const initialTab = new URLSearchParams(window.location.search).get('tab') === 'cuts' ? 'cuts' : 'narrative'
  const [tab, setTab] = useState<'narrative' | 'cuts'>(initialTab)
  const selectTab = useCallback((t: 'narrative' | 'cuts') => {
    setTab(t)
    const url = new URL(window.location.href)
    if (t === 'cuts') url.searchParams.set('tab', 'cuts')
    else url.searchParams.delete('tab')
    window.history.replaceState({}, '', url)
  }, [])

  const [choices, setChoices] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {}
    for (const dec of review.request_json.decisions ?? []) {
      initial[dec.id] = dec.recommended ?? dec.options[0] ?? ''
    }
    return initial
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [auditOpen, setAuditOpen] = useState(false)

  const req = review.request_json
  const decisions: ReviewDecision[] = req.decisions ?? []
  const autonomousAudit: string[] = req.autonomous_audit ?? []
  const actionability = req.actionability ?? null
  const overallScore = actionability?.overall_score ?? null
  const perScene = actionability?.per_scene ?? {}
  // Use the projected personas so chips + cards reflect in-flight edits.
  const personas = effectivePersonas

  // 1-based scene numbers among non-deleted scenes (renumbers as scenes are added/deleted).
  const sceneNumberById = new Map<string, number>()
  effectiveScenes
    .filter((s) => !s.deleted)
    .forEach((s, i) => sceneNumberById.set(s.id, i + 1))

  const narrativeVerdictDecision = decisions.find((d) => d.id === 'narrative-verdict') ?? null
  const otherDecisions = decisions.filter((d) => d.id !== 'narrative-verdict')

  // Resolved display: prefer submitted response_json values over local choices
  function resolvedChoice(decId: string): string {
    if (readOnly && review.response_json?.decisions) {
      return review.response_json.decisions[decId] ?? choices[decId] ?? ''
    }
    return choices[decId] ?? ''
  }

  // Submit — builds payload from op-buffer projection
  const handleSubmit = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      // Build edited_scenes from effectiveScenes (op-buffer projection)
      const editedScenes: ReviewSubmittedScene[] = effectiveScenes.map((scene) => ({
        id: scene.id,
        title: scene.title,
        narration: scene.narration,
        deleted: scene.deleted,
        features: scene.features.map((f) => ({
          id: f.id,
          description: f.description,
          verify: f.verify,
          feedback: f.feedback,
        })),
        feedback: scene.feedback,
      }))

      // Diff personas: send only changed fields per persona key.
      const origPersonas = review.request_json.personas ?? {}
      const editedPersonas: ReviewSubmitPayload['edited_personas'] = {}
      for (const [key, p] of Object.entries(effectivePersonas)) {
        const o = origPersonas[key]
        const delta: Record<string, string> = {}
        for (const f of ['name', 'org', 'role', 'intro'] as const) {
          if ((p[f] ?? '') !== (o?.[f] ?? '')) delta[f] = p[f] ?? ''
        }
        if (Object.keys(delta).length > 0) editedPersonas![key] = delta
      }

      // Diff why-brief prose fields.
      const origWb = review.request_json.why_brief ?? {}
      const wbDelta: ReviewSubmitPayload['edited_why_brief'] = {}
      if ((effectiveWhyBrief.problem ?? '') !== (origWb.problem ?? '')) {
        wbDelta!.problem = effectiveWhyBrief.problem ?? ''
      }
      const spineDelta: Record<string, { claim?: string; rationale?: string }> = {}
      for (const item of effectiveWhyBrief.spine ?? []) {
        const o = (origWb.spine ?? []).find((s) => s.id === item.id)
        const d: { claim?: string; rationale?: string } = {}
        if ((item.claim ?? '') !== (o?.claim ?? '')) d.claim = item.claim ?? ''
        if ((item.rationale ?? '') !== (o?.rationale ?? '')) d.rationale = item.rationale ?? ''
        if (Object.keys(d).length > 0) spineDelta[item.id] = d
      }
      if (Object.keys(spineDelta).length > 0) wbDelta!.spine = spineDelta
      const gapDelta: Record<string, { detail?: string; proposed_action?: string }> = {}
      for (const gap of effectiveWhyBrief.gaps ?? []) {
        const o = (origWb.gaps ?? []).find((g) => g.id === gap.id)
        const d: { detail?: string; proposed_action?: string } = {}
        if ((gap.detail ?? '') !== (o?.detail ?? '')) d.detail = gap.detail ?? ''
        if ((gap.proposed_action ?? '') !== (o?.proposed_action ?? '')) d.proposed_action = gap.proposed_action ?? ''
        if (Object.keys(d).length > 0) gapDelta[gap.id] = d
      }
      if (Object.keys(gapDelta).length > 0) wbDelta!.gaps = gapDelta

      const payload: ReviewSubmitPayload = {
        decisions: choices,
        edited_scenes: editedScenes,
        overall_feedback: overallFeedback,
        build_order: buildOrder,
      }
      if (Object.keys(editedPersonas!).length > 0) payload.edited_personas = editedPersonas
      if (Object.keys(wbDelta!).length > 0) payload.edited_why_brief = wbDelta

      const updated = await submitReview(review.id, payload, shareToken)
      onResolved(updated)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [effectiveScenes, effectivePersonas, effectiveWhyBrief, overallFeedback, buildOrder, choices, review.id, review.request_json, shareToken, onResolved])

  const canSubmit = !busy && decisions.every((d) => !!choices[d.id])

  // Video embed
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
      <video src={req.video.url} controls className="w-full max-h-[60vh] bg-black" />
    )
  } else {
    videoElement = (
      <div className="flex items-center justify-center h-40 text-stone-500 text-sm">
        No cut available yet
      </div>
    )
  }

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
        <div className="flex items-center gap-2">
          <DirtyBadge isDirty={isDirty} />
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

      {/* Undo bar */}
      {isDirty && !readOnly && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => dispatch({ type: 'UNDO_LAST_OP' })}
            className="text-xs text-stone-400 hover:text-stone-200 border border-stone-700 hover:border-stone-500 rounded px-3 py-1 transition-colors"
          >
            ↩ Undo last edit
          </button>
        </div>
      )}

      {/* Tabs — narrative review vs the rendered cut(s) */}
      <div className="flex items-center gap-1 border-b border-stone-800">
        {(['narrative', 'cuts'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => selectTab(t)}
            className={[
              'px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors',
              tab === t
                ? 'border-orange-500 text-stone-100'
                : 'border-transparent text-stone-500 hover:text-stone-300',
            ].join(' ')}
          >
            {t === 'narrative' ? 'Narrative' : 'Cuts'}
          </button>
        ))}
      </div>

      {/* Cuts tab — the rendered demo cut; kept off the main view so it isn't distracting */}
      {tab === 'cuts' && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-2">
            Current cut
          </h2>
          <div className="rounded-lg border border-stone-700 bg-black overflow-hidden">
            {videoElement}
          </div>
          <p className="text-xs text-stone-600 mt-2">
            This tab shows the rendered demo cut. Spec/yaml history lives in git — not version-controlled here.
          </p>
        </section>
      )}

      {/* Narrative tab — the story, personas, why-brief, scenes, decision */}
      {tab === 'narrative' && (
        <>
      {/* The demo narrative — the cohesive story the scenes decompose */}
      {req.narrative && req.narrative.trim() && (
        <section className="rounded-lg border border-stone-700 bg-stone-900/60 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider">
            The demo
          </h2>
          <p className="text-[15px] leading-relaxed text-stone-200 whitespace-pre-line">
            {req.narrative}
          </p>
          {Object.keys(personas).length > 0 && (
            <div className="flex items-center gap-2 flex-wrap pt-1">
              <span className="text-[11px] uppercase tracking-wider text-stone-600">Cast</span>
              {Object.values(personas).map((p) => (
                <PersonaChip key={p.name} persona={p} dim />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Personas — visible + editable */}
      <PersonasSection
        personas={personas}
        readOnly={readOnly}
        onEdit={(key, field, value) =>
          dispatch({ type: 'APPEND_OP', op: { op: 'edit-persona', key, field, value } })
        }
      />

      {/* Why-brief — visible + editable */}
      <WhyBriefSection
        whyBrief={effectiveWhyBrief}
        readOnly={readOnly}
        onEditProblem={(value) =>
          dispatch({ type: 'APPEND_OP', op: { op: 'edit-why-problem', value } })
        }
        onEditSpine={(id, field, value) =>
          dispatch({ type: 'APPEND_OP', op: { op: 'edit-why-spine', id, field, value } })
        }
        onEditGap={(id, field, value) =>
          dispatch({ type: 'APPEND_OP', op: { op: 'edit-why-gap', id, field, value } })
        }
      />

      {/* Narrative verdict decision tile */}
      {narrativeVerdictDecision && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-3">
            {readOnly ? 'Decision (submitted)' : 'Your decision'}
          </h2>
          <NarrativeVerdictControl
            decision={narrativeVerdictDecision}
            chosen={resolvedChoice('narrative-verdict')}
            onChange={(val) => setChoices((prev) => ({ ...prev, 'narrative-verdict': val }))}
            readOnly={readOnly}
          />
        </section>
      )}

      {/* Other decisions */}
      {otherDecisions.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-3">
            {readOnly ? 'Additional decisions (submitted)' : 'Additional decisions'}
          </h2>
          <div className="space-y-3">
            {otherDecisions.map((dec) => (
              <DecisionGroup
                key={dec.id}
                decision={dec}
                chosen={resolvedChoice(dec.id)}
                onChange={(val) => setChoices((prev) => ({ ...prev, [dec.id]: val }))}
                readOnly={readOnly}
              />
            ))}
          </div>
        </section>
      )}

      {/* Scene cards — driven by op-buffer projection */}
      {(effectiveScenes.length > 0 || !readOnly) && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-3">
            {readOnly ? 'Narration (submitted)' : 'Narration — edit inline'}
          </h2>
          <div className="space-y-4">
            {effectiveScenes.map((scene) => (
              <SceneCard
                key={scene.id}
                scene={scene}
                sceneNumber={sceneNumberById.get(scene.id)}
                persona={scene.persona ? personas[scene.persona] : undefined}
                readOnly={readOnly}
                sceneActionability={perScene[scene.id] ?? undefined}
                onEditNarration={(text) =>
                  dispatch({ type: 'APPEND_OP', op: { op: 'edit-narration', sceneId: scene.id, text } })
                }
                onEditFeature={(featureId, field, value) =>
                  dispatch({
                    type: 'APPEND_OP',
                    op: { op: 'edit-feature', sceneId: scene.id, featureId, field, value },
                  })
                }
                onFeatureFeedback={(featureId, text) =>
                  dispatch({
                    type: 'APPEND_OP',
                    op: { op: 'set-feature-feedback', sceneId: scene.id, featureId, text },
                  })
                }
                onDeleteFeature={(featureId) =>
                  dispatch({ type: 'APPEND_OP', op: { op: 'delete-feature', sceneId: scene.id, featureId } })
                }
                onAddFeature={() => {
                  newFeatureCounterRef.current += 1
                  const featureId = `new-${newFeatureCounterRef.current}`
                  dispatch({ type: 'APPEND_OP', op: { op: 'add-feature', sceneId: scene.id, featureId } })
                }}
                onDeleteScene={() =>
                  dispatch({ type: 'APPEND_OP', op: { op: 'delete-scene', sceneId: scene.id } })
                }
                onSceneFeedback={(text) =>
                  dispatch({ type: 'APPEND_OP', op: { op: 'set-scene-feedback', sceneId: scene.id, text } })
                }
              />
            ))}

            {/* Add scene */}
            {!readOnly && (
              <button
                type="button"
                onClick={() => {
                  newSceneCounterRef.current += 1
                  const sceneId = `new-${newSceneCounterRef.current}`
                  dispatch({
                    type: 'APPEND_OP',
                    op: { op: 'add-scene', sceneId, title: `New Scene ${newSceneCounterRef.current}` },
                  })
                }}
                className="w-full rounded-lg border border-dashed border-stone-700 hover:border-stone-500 text-stone-500 hover:text-stone-300 py-3 text-sm transition-colors"
              >
                + Add scene
              </button>
            )}
          </div>
        </section>
      )}

      {/* Build sequence — independent of the video order */}
      {effectiveScenes.filter((s) => !s.deleted).length > 0 && (
        <BuildSequenceSection
          effectiveScenes={effectiveScenes}
          buildOrder={buildOrder}
          readOnly={readOnly}
          onReorder={(orderedIds) =>
            dispatch({ type: 'APPEND_OP', op: { op: 'set-build-order', orderedSceneIds: orderedIds } })
          }
          resolvedBuildOrder={
            readOnly && review.response_json?.build_order
              ? review.response_json.build_order
              : null
          }
        />
      )}

      {/* Overall feedback */}
      {!readOnly && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-2">
            Overall feedback
          </h2>
          <textarea
            className="w-full rounded border bg-stone-900 px-3 py-2 text-sm text-stone-200 resize-y min-h-[3rem] border-stone-700 focus:border-stone-500 focus:outline-none transition-colors"
            value={overallFeedback}
            onChange={(e) =>
              dispatch({ type: 'APPEND_OP', op: { op: 'set-overall-feedback', text: e.target.value } })
            }
            rows={2}
            placeholder="Any overall feedback for the re-draft (optional)"
          />
        </section>
      )}
      {readOnly && review.response_json?.overall_feedback && (
        <section>
          <h2 className="text-sm font-semibold text-stone-400 uppercase tracking-wider mb-2">
            Overall feedback (submitted)
          </h2>
          <p className="text-sm text-stone-400 italic">{review.response_json.overall_feedback}</p>
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
              className={['h-4 w-4 transition-transform', auditOpen ? 'rotate-90' : ''].join(' ')}
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

      {/* Error */}
      {error && (
        <p className="text-sm text-red-400 rounded border border-red-500/30 bg-red-500/10 px-3 py-2">
          {error}
        </p>
      )}

      {/* Submit / resolved state */}
      {readOnly ? (
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
            disabled={!canSubmit}
            className={[
              'px-6 py-2 rounded font-medium text-sm transition-colors',
              !canSubmit
                ? 'bg-stone-700 text-stone-400 cursor-not-allowed'
                : 'bg-orange-500 hover:bg-orange-400 text-white',
            ].join(' ')}
          >
            {busy ? 'Submitting…' : 'Submit review'}
          </button>
        </div>
      )}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Outer page shell — fetches data, owns resolved state, wraps provider
// ---------------------------------------------------------------------------

export function ReviewPage() {
  const { id } = useParams<{ id: string }>()

  // ?t= share-token (stable for page lifetime — intentionally not in deps)
  const shareToken = useRef(new URLSearchParams(window.location.search).get('t')).current

  const [review, setReview] = useState<ReviewDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getReview(id, shareToken)
      .then((d) => { if (!cancelled) setReview(d) })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)) })
    return () => { cancelled = true }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

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

  const isResolved = review.status === 'resolved'

  return (
    <ReviewEditorProvider
      original={review.request_json.narration ?? []}
      initialBuildOrder={review.request_json.build_order ?? null}
      personas={review.request_json.personas ?? {}}
      whyBrief={review.request_json.why_brief ?? null}
    >
      <ReviewEditorInner
        review={review}
        readOnly={isResolved}
        onResolved={(updated) => setReview(updated)}
      />
    </ReviewEditorProvider>
  )
}
