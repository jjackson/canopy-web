import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getNarrative, type DddNarrativeDetail } from '@/api/ddd'

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

      {detail.story && (
        <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-stone-300">
          {detail.story}
        </p>
      )}

      <div className="mt-6 flex items-baseline gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-stone-500">
          Runs
        </h2>
        <span className="text-[11px] text-stone-600">{detail.runs.length}</span>
        <span className="h-px flex-1 bg-stone-800" />
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {detail.runs.map((r, i) => (
          <Link
            key={r.run_id}
            to={`/ddd/${encodeURIComponent(slug)}/${encodeURIComponent(r.run_id)}`}
            className="group rounded-xl border border-stone-800 bg-stone-900 p-4 transition-colors hover:border-stone-700"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-sm text-stone-200">{r.run_id}</span>
              {i === 0 && (
                <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-[9px] text-orange-300">
                  latest
                </span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-stone-500">
              {r.gate && <span>{r.gate}</span>}
              {r.status && (
                <span className="rounded bg-stone-800 px-1.5 py-0.5 text-stone-400">
                  {r.status}
                </span>
              )}
              <span>· {r.scene_count} scenes</span>
              {r.has_video && <span title="has video">🎬</span>}
              {r.has_deck && <span title="has deck">🖼️</span>}
              <span className="ml-auto">{fmtDate(r.latest_at)}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
