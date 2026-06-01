import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  deleteWalkthrough,
  getWalkthrough,
  patchWalkthrough,
  rotateWalkthroughToken,
  walkthroughContentUrl,
  type WalkthroughDetail,
} from '../api/walkthroughs'

export function WalkthroughViewerPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [w, setW] = useState<WalkthroughDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getWalkthrough(id)
      .then((d) => !cancelled && setW(d))
      .catch((e) => !cancelled && setError(String(e.message || e)))
    return () => {
      cancelled = true
    }
  }, [id])

  async function toggleVisibility() {
    if (!w) return
    setBusy(true)
    try {
      const next = w.visibility === 'link' ? 'private' : 'link'
      const updated = await patchWalkthrough(w.id, { visibility: next })
      setW(updated)
    } catch (e: any) {
      setError(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function copyShareLink() {
    if (!w) return
    let token = w.share_token
    if (!token || w.visibility !== 'link') {
      const updated = await patchWalkthrough(w.id, { visibility: 'link' })
      setW(updated)
      token = updated.share_token
    }
    const url = `${window.location.origin}/w/${w.id}?t=${encodeURIComponent(token!)}`
    await navigator.clipboard.writeText(url)
  }

  async function rotate() {
    if (!w) return
    setBusy(true)
    try {
      const { share_token } = await rotateWalkthroughToken(w.id)
      setW({ ...w, share_token })
      const url = `${window.location.origin}/w/${w.id}?t=${encodeURIComponent(share_token)}`
      await navigator.clipboard.writeText(url)
    } finally {
      setBusy(false)
    }
  }

  async function destroy() {
    if (!w) return
    if (!confirm(`Delete "${w.title}"? This cannot be undone.`)) return
    setBusy(true)
    try {
      await deleteWalkthrough(w.id)
      navigate('/walkthroughs')
    } catch (e: any) {
      setError(String(e?.message || e))
      setBusy(false)
    }
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-6 text-red-400/90">Error: {error}</div>
    )
  }
  if (!w) {
    return <div className="max-w-4xl mx-auto p-6 text-stone-500">Loading…</div>
  }

  const params = new URLSearchParams(window.location.search)
  const viewerToken = params.get('t') ?? w.share_token ?? null
  const contentSrc = walkthroughContentUrl(w.id, viewerToken)

  const links = w.links ?? []
  // narrative + companion are provenance / sibling-artifact nav; reference
  // links are destinations the demo visited that the viewer can go open live.
  const siblingLinks = links.filter(
    (l) => l.kind === 'narrative' || l.kind === 'companion',
  )
  const referenceLinks = links.filter((l) => l.kind === 'reference')

  const siblingIcon = (kind: string | undefined) =>
    kind === 'narrative' ? '📖' : '🎞️'

  return (
    <div className="max-w-5xl mx-auto p-6">
      <header className="mb-4 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-stone-100">{w.title}</h1>
          <p className="text-sm text-stone-500">
            {w.kind === 'video' ? 'Video' : 'HTML slideshow'} · {w.owner_email}
            {w.project_slug ? ` · ${w.project_slug}` : ''}
          </p>
        </div>
        <span
          className={`px-2 py-0.5 text-xs rounded border ${
            w.visibility === 'link'
              ? 'text-emerald-400/90 bg-emerald-400/10 border-emerald-400/25'
              : 'text-stone-400 bg-stone-800/60 border-stone-700'
          }`}
        >
          {w.visibility === 'link' ? 'Shareable link' : 'Private (dimagi)'}
        </span>
      </header>

      {w.is_owner && (
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          <button
            className="px-3 py-1 rounded-lg border border-stone-800 bg-stone-900 text-stone-300 hover:bg-stone-800 hover:border-stone-700 transition-colors disabled:opacity-50"
            onClick={toggleVisibility}
            disabled={busy}
          >
            {w.visibility === 'link' ? 'Make private' : 'Enable link'}
          </button>
          <button
            className="px-3 py-1 rounded-lg border border-stone-800 bg-stone-900 text-stone-300 hover:bg-stone-800 hover:border-stone-700 transition-colors disabled:opacity-50"
            onClick={copyShareLink}
            disabled={busy}
          >
            Copy share link
          </button>
          {w.visibility === 'link' && (
            <button
              className="px-3 py-1 rounded-lg border border-stone-800 bg-stone-900 text-stone-300 hover:bg-stone-800 hover:border-stone-700 transition-colors disabled:opacity-50"
              onClick={rotate}
              disabled={busy}
            >
              Rotate token
            </button>
          )}
          <button
            className="px-3 py-1 rounded-lg border border-red-500/30 text-red-400/90 bg-red-500/5 hover:bg-red-500/10 transition-colors disabled:opacity-50 ml-auto"
            onClick={destroy}
            disabled={busy}
          >
            Delete
          </button>
        </div>
      )}

      <div className="rounded-xl border border-stone-800 bg-black overflow-hidden">
        {w.kind === 'video' ? (
          <video
            src={contentSrc}
            controls
            className="w-full max-h-[80vh] bg-black"
          />
        ) : (
          <iframe
            src={contentSrc}
            title={w.title}
            sandbox="allow-scripts allow-same-origin"
            className="w-full h-[80vh] bg-white"
          />
        )}
      </div>

      {(siblingLinks.length > 0 || referenceLinks.length > 0) && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {siblingLinks.length > 0 && (
            <section className="bg-stone-900 border border-stone-800 rounded-xl p-5">
              <h2 className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-3">
                This walkthrough
              </h2>
              <div className="flex flex-col gap-2">
                {siblingLinks.map((l) => (
                  <a
                    key={l.url}
                    href={l.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center gap-3 bg-stone-950/40 hover:bg-stone-950/70 border border-stone-800 hover:border-stone-700 rounded-lg px-3 py-2 transition-colors"
                  >
                    <span aria-hidden className="shrink-0 text-sm">
                      {siblingIcon(l.kind)}
                    </span>
                    <span className="text-xs text-stone-300 truncate flex-1">
                      {l.label}
                    </span>
                    <span
                      aria-hidden
                      className="text-[11px] text-stone-600 group-hover:text-orange-400 transition-colors shrink-0"
                    >
                      ↗
                    </span>
                  </a>
                ))}
              </div>
            </section>
          )}

          {referenceLinks.length > 0 && (
            <section className="bg-stone-900 border border-stone-800 rounded-xl p-5">
              <h2 className="text-[9px] uppercase tracking-wider text-stone-600 font-semibold mb-1">
                Explore in the app
              </h2>
              <p className="text-xs text-stone-500 mb-3">
                Destinations shown in this walkthrough — open them live.
              </p>
              <div className="flex flex-col gap-2">
                {referenceLinks.map((l) => (
                  <a
                    key={l.url}
                    href={l.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center gap-3 bg-stone-950/40 hover:bg-stone-950/70 border border-stone-800 hover:border-stone-700 rounded-lg px-3 py-2 transition-colors"
                  >
                    <span className="text-xs text-stone-300 truncate flex-1">
                      {l.label}
                    </span>
                    <span
                      aria-hidden
                      className="text-[11px] text-stone-600 group-hover:text-orange-400 transition-colors shrink-0"
                    >
                      ↗
                    </span>
                  </a>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
