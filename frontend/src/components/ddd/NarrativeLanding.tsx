import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getNarrative,
  type DddNarrativeDetail,
  type DddNarrativeRun,
  type DddNarrativeVersion,
} from '@/api/ddd'

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}

function RunCard({ slug, run, latest }: { slug: string; run: DddNarrativeRun; latest: boolean }) {
  return (
    <Link
      to={`/ddd/${encodeURIComponent(slug)}/${encodeURIComponent(run.run_id)}`}
      className="group rounded-xl border border-stone-800 bg-stone-900 p-4 transition-colors hover:border-stone-700"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm text-stone-200">{run.run_id}</span>
        {latest && (
          <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-[9px] text-orange-300">
            latest
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-stone-500">
        {run.gate && <span>{run.gate}</span>}
        {run.status && (
          <span className="rounded bg-stone-800 px-1.5 py-0.5 text-stone-400">{run.status}</span>
        )}
        <span>· {run.scene_count} scenes</span>
        {run.has_video && <span title="has video">🎬</span>}
        {run.has_deck && <span title="has deck">🖼️</span>}
        <span className="ml-auto">{fmtDate(run.latest_at)}</span>
      </div>
    </Link>
  )
}

function VersionBlock({
  slug,
  version,
  isCurrent,
}: {
  slug: string
  version: DddNarrativeVersion
  isCurrent: boolean
}) {
  const [open, setOpen] = useState(isCurrent)
  const label = version.version != null ? `v${version.version}` : 'no narrative'
  return (
    <section className="rounded-xl border border-stone-800 bg-stone-950/30">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        <span aria-hidden className="text-stone-600">{open ? '▾' : '▸'}</span>
        <span className="font-mono text-xs text-orange-300">{label}</span>
        {isCurrent && (
          <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-[9px] text-orange-300">
            current
          </span>
        )}
        <span className="truncate text-sm text-stone-300">{version.title || ''}</span>
        <span className="ml-auto shrink-0 text-[11px] text-stone-600">
          {version.runs.length} run{version.runs.length === 1 ? '' : 's'} · {fmtDate(version.created_at)}
        </span>
      </button>

      {open && (
        <div className="border-t border-stone-800 px-4 py-3">
          {version.story && (
            <p className="mb-3 whitespace-pre-line text-sm leading-relaxed text-stone-300">
              {version.story}
            </p>
          )}
          {version.review_id && (
            <a
              href={`/review/${version.review_id}`}
              className="mb-3 inline-flex items-center gap-1.5 rounded-md border border-orange-500/30 bg-orange-500/10 px-3 py-1 text-xs text-orange-300 transition-colors hover:bg-orange-500/20"
            >
              Edit narrative <span aria-hidden>→</span>
            </a>
          )}
          {version.runs.length > 0 ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {version.runs.map((r, i) => (
                <RunCard key={r.run_id} slug={slug} run={r} latest={isCurrent && i === 0} />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-stone-800 px-4 py-4 text-center text-xs text-stone-600">
              No runs rendered from this version yet.
            </div>
          )}
        </div>
      )}
    </section>
  )
}

export function NarrativeLanding({ slug }: { slug: string }) {
  const [detail, setDetail] = useState<DddNarrativeDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setDetail(null)
    setError(null)
    getNarrative(slug)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(String(e.message || e)))
    return () => {
      cancelled = true
    }
  }, [slug])

  if (error) return <div className="p-8 text-sm text-red-400/90">Error: {error}</div>
  if (!detail) return <div className="p-8 text-sm text-stone-500">Loading…</div>

  const currentVersion = detail.current_version?.version ?? null

  return (
    <div className="mx-auto max-w-4xl px-8 py-6">
      <header>
        <div className="text-[11px] uppercase tracking-wider text-stone-500">Narrative</div>
        <h1 className="text-2xl font-semibold text-stone-100">{detail.title || detail.slug}</h1>
        <div className="mt-1 flex items-center gap-3 text-xs text-stone-500">
          <span className="font-mono">{detail.slug}</span>
          {detail.phase && (
            <span className="rounded border border-stone-700 bg-stone-800/60 px-2 py-0.5 text-stone-300">
              {detail.phase}
            </span>
          )}
          {detail.project_slug && <span>· {detail.project_slug}</span>}
        </div>
      </header>

      <div className="mt-6 flex items-baseline gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-stone-500">
          Versions &amp; runs
        </h2>
        <span className="text-[11px] text-stone-600">{detail.versions.length}</span>
        <span className="h-px flex-1 bg-stone-800" />
      </div>

      <div className="mt-3 flex flex-col gap-3">
        {detail.versions.map((v) => (
          <VersionBlock
            key={v.review_id ?? 'unversioned'}
            slug={slug}
            version={v}
            isCurrent={v.version != null && v.version === currentVersion}
          />
        ))}
        {detail.versions.length === 0 && (
          <div className="rounded-xl border border-dashed border-stone-800 px-4 py-6 text-center text-sm text-stone-600">
            No narrative versions yet.
          </div>
        )}
      </div>
    </div>
  )
}
