import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  deleteNarrative,
  deleteNarrativeVersion,
  deleteRun,
  getNarrative,
  setNarrativeVisibility,
  type DddNarrativeDetail,
  type DddNarrativeRun,
  type DddNarrativeVersion,
} from '@/api/ddd'
import { withBase } from '@/lib/basePath'

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

/** Small ghost button that turns red on hover — the delete affordance. */
function DeleteButton({
  label,
  busy,
  onClick,
}: {
  label: string
  busy: boolean
  onClick: (e: React.MouseEvent) => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      title={label}
      className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-stone-500 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
    >
      {busy ? '…' : 'Delete'}
    </button>
  )
}

function RunCard({
  slug,
  run,
  latest,
  onDeleted,
}: {
  slug: string
  run: DddNarrativeRun
  latest: boolean
  onDeleted: () => void
}) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const href = `/ddd/${encodeURIComponent(slug)}/${encodeURIComponent(run.run_id)}`

  async function onDelete(e: React.MouseEvent) {
    e.stopPropagation()
    if (
      !window.confirm(
        `Delete run ${run.run_id}?\n\nIts rendered video/deck files will be removed from Drive. This cannot be undone.`,
      )
    )
      return
    setBusy(true)
    try {
      await deleteRun(run.run_id)
      onDeleted()
    } catch (err) {
      window.alert(`Delete failed: ${(err as Error).message || err}`)
      setBusy(false)
    }
  }

  return (
    <div
      role="link"
      tabIndex={0}
      onClick={() => navigate(href)}
      onKeyDown={(e) => e.key === 'Enter' && navigate(href)}
      className="group cursor-pointer rounded-xl border border-stone-800 bg-stone-900 p-4 transition-colors hover:border-stone-700"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-sm text-stone-200">{run.run_id}</span>
        <div className="flex shrink-0 items-center gap-2">
          {latest && (
            <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-[9px] text-orange-300">
              latest
            </span>
          )}
          <DeleteButton label="Delete run" busy={busy} onClick={onDelete} />
        </div>
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
    </div>
  )
}

function VersionBlock({
  slug,
  version,
  isCurrent,
  onChanged,
}: {
  slug: string
  version: DddNarrativeVersion
  isCurrent: boolean
  onChanged: () => void
}) {
  const [open, setOpen] = useState(isCurrent)
  const [busy, setBusy] = useState(false)
  const label = version.version != null ? `v${version.version}` : 'no narrative'

  async function onDelete(e: React.MouseEvent) {
    e.stopPropagation()
    if (version.version == null) return
    const n = version.runs.length
    if (
      !window.confirm(
        `Delete ${label}${version.title ? ` — "${version.title}"` : ''}?\n\n` +
          `This removes the version and its ${n} run${n === 1 ? '' : 's'} (rendered files included). This cannot be undone.`,
      )
    )
      return
    setBusy(true)
    try {
      await deleteNarrativeVersion(slug, version.version)
      onChanged()
    } catch (err) {
      window.alert(`Delete failed: ${(err as Error).message || err}`)
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-stone-800 bg-stone-950/30">
      <div className="flex items-center gap-2 px-4 py-3">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <span aria-hidden className="text-stone-600">
            {open ? '▾' : '▸'}
          </span>
          <span className="font-mono text-xs text-orange-300">{label}</span>
          {isCurrent && (
            <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-[9px] text-orange-300">
              current
            </span>
          )}
          <span className="truncate text-sm text-stone-300">{version.title || ''}</span>
          <span className="ml-auto shrink-0 text-[11px] text-stone-600">
            {version.runs.length} run{version.runs.length === 1 ? '' : 's'} ·{' '}
            {fmtDate(version.created_at)}
          </span>
        </button>
        {version.version != null && (
          <DeleteButton label="Delete version" busy={busy} onClick={onDelete} />
        )}
      </div>

      {open && (
        <div className="border-t border-stone-800 px-4 py-3">
          {version.story && (
            <p className="mb-3 whitespace-pre-line text-sm leading-relaxed text-stone-300">
              {version.story}
            </p>
          )}
          {version.video_url && (
            <video
              src={withBase(version.video_url)}
              controls
              preload="metadata"
              className="mb-3 w-full max-w-2xl rounded-lg border border-stone-800 bg-black"
            />
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
                <RunCard
                  key={r.run_id}
                  slug={slug}
                  run={r}
                  latest={isCurrent && i === 0}
                  onDeleted={onChanged}
                />
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
  const navigate = useNavigate()
  const [detail, setDetail] = useState<DddNarrativeDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [deletingNarrative, setDeletingNarrative] = useState(false)
  const [vizBusy, setVizBusy] = useState(false)

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
  }, [slug, reloadKey])

  async function onDeleteNarrative() {
    const n = detail?.versions.length ?? 0
    if (
      !window.confirm(
        `Delete the ENTIRE narrative "${slug}"?\n\n` +
          `This removes all ${n} version${n === 1 ? '' : 's'} and every run + rendered file. This cannot be undone.`,
      )
    )
      return
    setDeletingNarrative(true)
    try {
      await deleteNarrative(slug)
      navigate('/ddd')
    } catch (err) {
      window.alert(`Delete failed: ${(err as Error).message || err}`)
      setDeletingNarrative(false)
    }
  }

  async function toggleVisibility() {
    if (!detail) return
    const makePublic = detail.visibility !== 'public'
    setVizBusy(true)
    try {
      const res = await setNarrativeVisibility(slug, makePublic)
      setDetail({ ...detail, visibility: res.visibility })
    } catch (err) {
      window.alert(`Could not change visibility: ${(err as Error).message || err}`)
    } finally {
      setVizBusy(false)
    }
  }

  if (error) return <div className="p-8 text-sm text-red-400/90">Error: {error}</div>
  if (!detail) return <div className="p-8 text-sm text-stone-500">Loading…</div>

  const currentVersion = detail.current_version?.version ?? null

  return (
    <div className="mx-auto max-w-4xl px-8 py-6">
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0">
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
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={toggleVisibility}
            disabled={vizBusy}
            title="Toggle whether this whole narrative (video, deck, docs, reviews) is public"
            className={`rounded-lg border px-3 py-1 text-sm transition-colors disabled:opacity-50 ${
              detail.visibility === 'public'
                ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-400/90 hover:bg-emerald-400/20'
                : 'border-stone-700 bg-stone-800/60 text-stone-300 hover:bg-stone-800'
            }`}
          >
            {vizBusy
              ? '…'
              : detail.visibility === 'public'
                ? 'Public'
                : detail.visibility === 'mixed'
                  ? 'Mixed — make public'
                  : 'Private'}
          </button>
          <button
            type="button"
            onClick={onDeleteNarrative}
            disabled={deletingNarrative}
            className="rounded-md border border-stone-800 px-2.5 py-1 text-xs text-stone-500 transition-colors hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
          >
            {deletingNarrative ? 'Deleting…' : 'Delete narrative'}
          </button>
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
            onChanged={() => setReloadKey((k) => k + 1)}
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
