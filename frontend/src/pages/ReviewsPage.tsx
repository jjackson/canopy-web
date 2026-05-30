import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  listReviews,
  deleteReview,
  type ReviewListItem,
  type ReviewListOrder,
  type ReviewStatus,
} from '../api/reviews'

const ORDER_OPTIONS: { value: ReviewListOrder; label: string }[] = [
  { value: '-last_activity', label: 'Last edited (newest)' },
  { value: 'last_activity', label: 'Last edited (oldest)' },
  { value: '-created', label: 'Created (newest)' },
  { value: 'created', label: 'Created (oldest)' },
  { value: 'feature', label: 'Feature (A–Z)' },
]

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime()
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (secs < 60) return `${secs}s ago`
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.round(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.round(months / 12)}y ago`
}

function absDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusChip({ status }: { status: ReviewStatus }) {
  const cls =
    status === 'pending'
      ? 'bg-amber-400/10 text-amber-300 border-amber-400/20'
      : 'bg-emerald-400/10 text-emerald-300 border-emerald-400/20'
  return (
    <span className={`px-2 py-0.5 text-[11px] rounded border ${cls}`}>
      {status === 'pending' ? 'Pending' : 'Resolved'}
    </span>
  )
}

function reviewHref(it: ReviewListItem): string {
  const t = it.share_token ? `?t=${encodeURIComponent(it.share_token)}` : ''
  return `/review/${it.id}/${t}`
}

export function ReviewsPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const order = (params.get('order') as ReviewListOrder | null) ?? '-last_activity'
  const status = (params.get('status') as ReviewStatus | null) ?? null

  const [items, setItems] = useState<ReviewListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setItems(null)
    setError(null)
    listReviews({ q: q || undefined, order, status: status ?? undefined })
      .then((data) => {
        if (!cancelled) setItems(data)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e.message || e))
      })
    return () => {
      cancelled = true
    }
  }, [q, order, status, reloadKey])

  function update(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value == null || value === '') next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  async function onDelete(it: ReviewListItem) {
    const label = it.title ? `${it.feature} — "${it.title}"` : it.feature
    if (!window.confirm(`Delete this DDD plan?\n\n${label}\n(${it.gate}, ${it.run_id})\n\nThis cannot be undone.`)) {
      return
    }
    setDeleting(it.id)
    try {
      await deleteReview(it.id)
      setItems((prev) => (prev ? prev.filter((r) => r.id !== it.id) : prev))
    } catch (e) {
      setError(String((e as Error).message || e))
    } finally {
      setDeleting(null)
    }
  }

  const count = useMemo(() => items?.length ?? 0, [items])

  return (
    <div className="max-w-6xl mx-auto">
      <header className="flex items-baseline justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-stone-100">DDD Plans</h1>
          <p className="text-sm text-stone-500 mt-1">
            Demo-driven-development narratives posted to the review surface. Open one to
            approve/redraft, or delete stale ones.
          </p>
        </div>
        {items && (
          <span className="text-xs text-stone-500">{count} plan{count === 1 ? '' : 's'}</span>
        )}
      </header>

      <div className="flex flex-wrap items-center gap-3 mb-4 text-sm">
        <input
          type="search"
          placeholder="Search feature, run id, gate, or title…"
          defaultValue={q}
          onChange={(e) => update('q', e.target.value)}
          className="flex-1 min-w-[16rem] rounded border border-stone-700 bg-stone-900 px-3 py-1.5 text-stone-200 placeholder:text-stone-600 focus:outline-none focus:border-orange-400/50"
        />
        <select
          value={status ?? ''}
          onChange={(e) => update('status', e.target.value || null)}
          className="rounded border border-stone-700 bg-stone-900 px-2 py-1.5 text-stone-200"
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="resolved">Resolved</option>
        </select>
        <select
          value={order}
          onChange={(e) => update('order', e.target.value)}
          className="rounded border border-stone-700 bg-stone-900 px-2 py-1.5 text-stone-200"
        >
          {ORDER_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}{' '}
          <button
            type="button"
            onClick={() => setReloadKey((k) => k + 1)}
            className="underline hover:text-red-200"
          >
            retry
          </button>
        </div>
      )}
      {items === null && !error && <div className="text-stone-500 text-sm">Loading…</div>}
      {items && items.length === 0 && !error && (
        <div className="rounded border border-stone-800 bg-stone-900/50 px-4 py-8 text-center text-sm text-stone-500">
          {q || status ? 'No plans match your filters.' : 'No DDD plans yet.'}
        </div>
      )}

      {items && items.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-stone-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-stone-800 bg-stone-900/60 text-left text-[11px] uppercase tracking-wider text-stone-500">
                <th className="px-4 py-2 font-medium">Plan</th>
                <th className="px-3 py-2 font-medium">Gate</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium text-right">Scenes</th>
                <th className="px-3 py-2 font-medium">Last edited</th>
                <th className="px-3 py-2 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="border-b border-stone-800/60 last:border-0 hover:bg-stone-900/40">
                  <td className="px-4 py-3">
                    <Link to={reviewHref(it)} className="font-medium text-stone-100 hover:text-orange-300">
                      {it.feature}
                    </Link>
                    {it.title && <div className="text-stone-400 text-xs mt-0.5 line-clamp-1">{it.title}</div>}
                    <div className="text-stone-600 text-[11px] mt-0.5 font-mono">{it.run_id}</div>
                  </td>
                  <td className="px-3 py-3">
                    <span className="text-stone-300 text-xs">{it.gate}</span>
                  </td>
                  <td className="px-3 py-3">
                    <StatusChip status={it.status} />
                  </td>
                  <td className="px-3 py-3 text-right text-stone-300 tabular-nums">{it.scene_count}</td>
                  <td className="px-3 py-3 whitespace-nowrap" title={absDate(it.last_activity_at)}>
                    <span className="text-stone-300">{timeAgo(it.last_activity_at)}</span>
                    {it.status === 'resolved' && (
                      <span className="text-stone-600 text-[11px] ml-1">(resolved)</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right whitespace-nowrap">
                    <Link
                      to={reviewHref(it)}
                      className="text-xs text-orange-300 hover:text-orange-200 mr-3"
                    >
                      Open
                    </Link>
                    <button
                      type="button"
                      onClick={() => void onDelete(it)}
                      disabled={deleting === it.id}
                      className="text-xs text-stone-500 hover:text-red-300 disabled:opacity-50"
                    >
                      {deleting === it.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
