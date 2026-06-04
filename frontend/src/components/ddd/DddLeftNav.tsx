import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  getNarrative,
  listNarratives,
  type DddNarrativeDetail,
  type DddNarrativeListItem,
} from '@/api/ddd'

function runStamp(runId: string): string {
  // "microplans-2026-06-02-001" -> "2026-06-02-001"
  const m = runId.match(/(\d{4}-\d{2}-\d{2}-\d+)$/)
  return m ? m[1] : runId
}

/** The runs of the active narrative: latest expanded, older under a disclosure. */
function NarrativeRuns({
  slug,
  activeRunId,
}: {
  slug: string
  activeRunId?: string
}) {
  const [detail, setDetail] = useState<DddNarrativeDetail | null>(null)
  const [showPrev, setShowPrev] = useState(false)

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

  if (!detail) {
    return <div className="px-3 py-1 text-[11px] text-stone-600">Loading runs…</div>
  }
  // Flatten runs across versions for the rail (newest first); the version
  // structure itself lives on the narrative page.
  const allRuns = detail.versions
    .flatMap((v) => v.runs)
    .sort((a, b) => (b.latest_at || '').localeCompare(a.latest_at || ''))
  if (allRuns.length === 0) {
    return <div className="px-3 py-1 text-[11px] text-stone-600">No runs yet</div>
  }

  const [latest, ...previous] = allRuns

  const runRow = (runId: string, isLatest: boolean) => (
    <Link
      key={runId}
      to={`/ddd/${encodeURIComponent(slug)}/${encodeURIComponent(runId)}`}
      className={clsx(
        'flex items-center gap-2 rounded-md px-3 py-1 text-xs transition-colors',
        runId === activeRunId
          ? 'bg-orange-500/10 text-orange-300 border border-orange-500/30'
          : 'text-stone-400 hover:bg-stone-800/60 hover:text-stone-200 border border-transparent',
      )}
    >
      <span aria-hidden className="text-stone-600">
        {isLatest ? '●' : '○'}
      </span>
      <span className="truncate font-mono">{runStamp(runId)}</span>
    </Link>
  )

  return (
    <div className="ml-2 flex flex-col gap-0.5 border-l border-stone-800 pl-1">
      {runRow(latest.run_id, true)}
      {previous.length > 0 && (
        <>
          {showPrev && previous.map((r) => runRow(r.run_id, false))}
          <button
            onClick={() => setShowPrev((s) => !s)}
            className="px-3 py-1 text-left text-[11px] text-stone-500 hover:text-stone-300"
          >
            {showPrev ? '▾ hide previous' : `▸ previous runs (${previous.length})`}
          </button>
        </>
      )}
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
  const location = useLocation()
  const plansActive = location.pathname === '/ddd-plans'

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
      <div className="border-b border-stone-800 px-2 py-2">
        <Link
          to="/ddd-plans"
          className={clsx(
            'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
            plansActive
              ? 'bg-stone-800/70 text-stone-100'
              : 'text-stone-300 hover:bg-stone-800/40',
          )}
        >
          <span aria-hidden>📋</span>
          Plans
        </Link>
      </div>

      <div className="border-b border-stone-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-stone-200">Narratives</h2>
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
