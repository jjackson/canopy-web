import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  getNarrative,
  listNarratives,
  type DddNarrativeDetail,
  type DddNarrativeListItem,
} from '@/api/ddd'
import { listReviews, type ReviewListItem } from '@/api/reviews'
import { useRunSectionNav } from './runSectionNav'

/**
 * Run-child product-findings review entry, nested under its run. These are NOT
 * narrative-version rows (the backend forces narrative_slug=None / version=0);
 * we surface them here so a run with an open findings review reads as "needs
 * input" right in the rail. Distinguished purely by gate === 'product_findings'.
 */
function FindingsReviewEntry({
  review,
  active,
}: {
  review: ReviewListItem
  active: boolean
}) {
  const pending = review.status !== 'resolved'
  return (
    <Link
      to={`/review/${encodeURIComponent(review.id)}`}
      className={clsx(
        'flex items-center gap-2 rounded-md px-3 py-0.5 text-[11px] transition-colors',
        active
          ? 'text-orange-300'
          : pending
            ? 'text-amber-300/90 hover:text-amber-200'
            : 'text-stone-500 hover:text-stone-300',
      )}
    >
      <span
        aria-hidden
        className={clsx(
          'h-1 w-1 shrink-0 rounded-full',
          pending ? 'bg-amber-400' : 'bg-stone-700',
        )}
      />
      <span className="truncate">
        Findings review · {pending ? 'needs input' : 'resolved'}
      </span>
    </Link>
  )
}

function runStamp(runId: string): string {
  // "microplans-2026-06-02-001" -> "2026-06-02-001"
  const m = runId.match(/(\d{4}-\d{2}-\d{2}-\d+)$/)
  return m ? m[1] : runId
}

/**
 * Jump-list of the active run's sections, nested under its run entry. The run
 * package registers these and reports the active one via scroll-spy (see
 * runSectionNav); clicking scrolls the package to that section so the rail
 * navigates a run instead of forcing one long scroll. Renders nothing until the
 * package has mounted and published its sections.
 */
function RunSectionList() {
  const nav = useRunSectionNav()
  if (!nav || nav.sections.length === 0) return null
  return (
    <div className="ml-6 mt-0.5 flex flex-col gap-0.5 border-l border-stone-800/70 pl-1">
      {nav.sections.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => nav.jump(s.id)}
          className={clsx(
            'flex items-center gap-2 rounded-md px-3 py-0.5 text-left text-[11px] transition-colors',
            s.id === nav.activeId
              ? 'text-orange-300'
              : 'text-stone-500 hover:text-stone-300',
          )}
        >
          <span
            aria-hidden
            className={clsx(
              'h-1 w-1 shrink-0 rounded-full',
              s.id === nav.activeId ? 'bg-orange-400' : 'bg-stone-700',
            )}
          />
          <span className="truncate">{s.label}</span>
        </button>
      ))}
    </div>
  )
}

/**
 * The active narrative's versions, each with its runs nested beneath — mirrors
 * the "Versions & runs" structure on the narrative page. Newest version first;
 * the current version carries a badge.
 */
function NarrativeRuns({
  slug,
  activeRunId,
}: {
  slug: string
  activeRunId?: string
}) {
  const [detail, setDetail] = useState<DddNarrativeDetail | null>(null)
  // Run-child product-findings reviews for this narrative, grouped by run_id.
  // Sourced from the reviews list (the narrative API doesn't carry run-children),
  // filtered to gate === 'product_findings' so they never show as version rows.
  const [findingsByRun, setFindingsByRun] = useState<Map<string, ReviewListItem[]>>(new Map())

  useEffect(() => {
    let cancelled = false
    setDetail(null)
    getNarrative(slug)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => !cancelled && setDetail(null))
    return () => {
      cancelled = true
    }
  }, [slug])

  useEffect(() => {
    let cancelled = false
    listReviews({ q: slug })
      .then((reviews) => {
        if (cancelled) return
        const byRun = new Map<string, ReviewListItem[]>()
        for (const r of reviews) {
          if (r.gate !== 'product_findings') continue
          if (r.narrative_slug !== slug) continue
          const list = byRun.get(r.run_id) ?? []
          list.push(r)
          byRun.set(r.run_id, list)
        }
        setFindingsByRun(byRun)
      })
      .catch(() => !cancelled && setFindingsByRun(new Map()))
    return () => {
      cancelled = true
    }
  }, [slug])

  if (!detail) {
    return <div className="px-3 py-1 text-[11px] text-stone-600">Loading runs…</div>
  }

  // Highlight a findings-review entry when its /review/:id page is open.
  const reviewMatch = window.location.pathname.match(/^\/review\/([^/]+)/)
  const activeReviewId = reviewMatch ? decodeURIComponent(reviewMatch[1]) : undefined

  const currentVersion = detail.current_version?.version ?? null
  // Newest version first, matching the narrative page ordering.
  const versions = [...detail.versions].sort(
    (a, b) => (b.version ?? 0) - (a.version ?? 0),
  )
  if (versions.length === 0) {
    return <div className="px-3 py-1 text-[11px] text-stone-600">No versions yet</div>
  }

  return (
    <div className="ml-2 flex flex-col gap-1 border-l border-stone-800 pl-1">
      {versions.map((v) => {
        const isCurrent = v.version != null && v.version === currentVersion
        const label = v.version != null ? `v${v.version}` : 'no narrative'
        const runs = [...v.runs].sort((a, b) =>
          (b.latest_at || '').localeCompare(a.latest_at || ''),
        )
        return (
          <div key={v.review_id ?? `v${v.version ?? 'none'}`} className="flex flex-col gap-0.5">
            <div className="flex items-center gap-1.5 px-3 py-0.5">
              <span className="font-mono text-[11px] font-medium text-stone-300">{label}</span>
              {isCurrent && (
                <span className="rounded bg-orange-500/15 px-1 py-px text-[9px] font-medium uppercase tracking-wide text-orange-300">
                  current
                </span>
              )}
            </div>
            {runs.length === 0 ? (
              <div className="px-3 py-0.5 pl-5 text-[11px] text-stone-600">No runs</div>
            ) : (
              <div className="ml-3 flex flex-col gap-0.5 border-l border-stone-800/70 pl-1">
                {runs.map((r) => (
                  <div key={r.run_id} className="flex flex-col gap-0.5">
                    <Link
                      to={`/ddd/${encodeURIComponent(slug)}/${encodeURIComponent(r.run_id)}`}
                      className={clsx(
                        'flex items-center gap-2 rounded-md px-3 py-1 text-xs transition-colors',
                        r.run_id === activeRunId
                          ? 'bg-orange-500/10 text-orange-300 border border-orange-500/30'
                          : 'text-stone-400 hover:bg-stone-800/60 hover:text-stone-200 border border-transparent',
                      )}
                    >
                      <span aria-hidden className="text-stone-600">
                        {r.run_id === activeRunId ? '●' : '○'}
                      </span>
                      <span className="truncate font-mono">{runStamp(r.run_id)}</span>
                    </Link>
                    {r.run_id === activeRunId && <RunSectionList />}
                    {(findingsByRun.get(r.run_id) ?? []).length > 0 && (
                      <div className="ml-6 mt-0.5 flex flex-col gap-0.5 border-l border-stone-800/70 pl-1">
                        {(findingsByRun.get(r.run_id) ?? []).map((fr) => (
                          <FindingsReviewEntry
                            key={fr.id}
                            review={fr}
                            active={activeReviewId === fr.id}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function DddLeftNav({
  activeSlug,
  activeRunId,
}: {
  activeSlug?: string
  activeRunId?: string
}) {
  const [narratives, setNarratives] = useState<DddNarrativeListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mine, setMine] = useState(false)
  const [project, setProject] = useState('')

  useEffect(() => {
    let cancelled = false
    setNarratives(null)
    listNarratives({ project: project || undefined, mine })
      .then((d) => !cancelled && setNarratives(d))
      .catch((e) => !cancelled && setError(String(e.message || e)))
    return () => {
      cancelled = true
    }
  }, [mine, project])

  const projects = Array.from(
    new Set((narratives ?? []).map((n) => n.project_slug).filter(Boolean) as string[]),
  ).sort()

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-stone-800 bg-stone-950/40">
      <div className="border-b border-stone-800 px-4 py-3">
        <Link to="/ddd" className="text-sm font-semibold text-stone-200 hover:text-stone-100">
          Narratives
        </Link>
        <p className="text-[11px] text-stone-500">DDD runs, grouped by narrative</p>
      </div>

      <div className="flex flex-col gap-2 border-b border-stone-800 px-3 py-2">
        <select
          value={project}
          onChange={(e) => setProject(e.target.value)}
          className="rounded-md border border-stone-800 bg-stone-900 px-2 py-1 text-xs text-stone-300"
        >
          <option value="">All projects</option>
          {projects.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-[11px] text-stone-400">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => setMine(e.target.checked)}
          />
          Mine only
        </label>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {error && <div className="px-3 py-2 text-xs text-red-400/90">{error}</div>}
        {!narratives && !error && (
          <div className="px-3 py-2 text-xs text-stone-600">Loading…</div>
        )}
        {narratives && narratives.length === 0 && (
          <div className="px-3 py-2 text-xs text-stone-600">No narratives yet</div>
        )}
        <div className="flex flex-col gap-1">
          {(narratives ?? []).map((n) => {
            const isActive = n.slug === activeSlug
            return (
              <div key={n.slug}>
                <Link
                  to={`/ddd/${encodeURIComponent(n.slug)}`}
                  className={clsx(
                    'flex items-center justify-between gap-2 rounded-md px-3 py-1.5 text-sm transition-colors',
                    isActive
                      ? 'bg-stone-800/70 text-stone-100'
                      : 'text-stone-300 hover:bg-stone-800/40',
                  )}
                >
                  <span className="truncate font-medium">{n.slug}</span>
                  <span className="shrink-0 text-[10px] text-stone-500">
                    {n.run_count}
                  </span>
                </Link>
                {isActive && (
                  <NarrativeRuns slug={n.slug} activeRunId={activeRunId} />
                )}
              </div>
            )
          })}
        </div>
      </nav>
    </aside>
  )
}
