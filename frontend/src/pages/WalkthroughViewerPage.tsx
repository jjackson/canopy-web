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
      <div className="max-w-4xl mx-auto p-6 text-red-600">Error: {error}</div>
    )
  }
  if (!w) {
    return <div className="max-w-4xl mx-auto p-6 text-slate-500">Loading…</div>
  }

  const params = new URLSearchParams(window.location.search)
  const viewerToken = params.get('t') ?? w.share_token ?? null
  const contentSrc = walkthroughContentUrl(w.id, viewerToken)

  return (
    <div className="max-w-5xl mx-auto p-6">
      <header className="mb-4 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{w.title}</h1>
          <p className="text-sm text-slate-500">
            {w.kind === 'video' ? 'Video' : 'HTML slideshow'} · {w.owner_email}
            {w.project_slug ? ` · ${w.project_slug}` : ''}
          </p>
        </div>
        <span
          className={`px-2 py-0.5 text-xs rounded ${
            w.visibility === 'link'
              ? 'bg-emerald-100 text-emerald-800'
              : 'bg-slate-100 text-slate-700'
          }`}
        >
          {w.visibility === 'link' ? 'Shareable link' : 'Private (dimagi)'}
        </span>
      </header>

      {w.is_owner && (
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          <button
            className="px-3 py-1 rounded border hover:bg-slate-50"
            onClick={toggleVisibility}
            disabled={busy}
          >
            {w.visibility === 'link' ? 'Make private' : 'Enable link'}
          </button>
          <button
            className="px-3 py-1 rounded border hover:bg-slate-50"
            onClick={copyShareLink}
            disabled={busy}
          >
            Copy share link
          </button>
          {w.visibility === 'link' && (
            <button
              className="px-3 py-1 rounded border hover:bg-slate-50"
              onClick={rotate}
              disabled={busy}
            >
              Rotate token
            </button>
          )}
          <button
            className="px-3 py-1 rounded border border-red-300 text-red-700 hover:bg-red-50 ml-auto"
            onClick={destroy}
            disabled={busy}
          >
            Delete
          </button>
        </div>
      )}

      <div className="rounded border bg-white overflow-hidden">
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
            className="w-full h-[80vh]"
          />
        )}
      </div>
    </div>
  )
}
