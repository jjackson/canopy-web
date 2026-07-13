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
import { withSceneHash } from '../lib/sceneHash'
import { timeHashSeconds, withTimeFragment } from '../lib/timeHash'

export function WalkthroughViewerPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [w, setW] = useState<WalkthroughDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const shareToken = new URLSearchParams(window.location.search).get('t')

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getWalkthrough(id, shareToken)
      .then((d) => !cancelled && setW(d))
      .catch((e) => !cancelled && setError(String(e.message || e)))
    return () => {
      cancelled = true
    }
  }, [id, shareToken])

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

  // The owner-only tokened public URL. Anonymous/non-owner viewers get null —
  // anonymous visitors already hold the link they arrived with.
  const shareUrl = w?.share_url ?? null

  async function copyShareUrl() {
    if (!shareUrl) return
    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (e: any) {
      setError(String(e?.message || e))
    }
  }

  async function rotateLink() {
    if (!w) return
    if (!confirm('Rotate the public link? Anyone using the current link will lose access.')) return
    setBusy(true)
    try {
      const updated = await rotateWalkthroughToken(w.id)
      setW(updated)
    } catch (e: any) {
      setError(String(e?.message || e))
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
      <div className="max-w-4xl mx-auto p-6 text-destructive/90">Error: {error}</div>
    )
  }
  if (!w) {
    return <div className="max-w-4xl mx-auto p-6 text-muted-foreground">Loading…</div>
  }

  // Forward a `#scene-N` deep-link (e.g. /w/<id>#scene-3) into the deck
  // iframe so it opens on that scene; the deck's own JS reads its hash. Videos
  // ignore it. Non-scene hashes normalize to '' and pass through unchanged.
  const contentSrc = withSceneHash(
    walkthroughContentUrl(w.id, shareToken),
    window.location.hash,
  )

  // Video time deep-link: a `#t=<seconds>` fragment (e.g. /w/<id>#t=83) seeks
  // the video to that offset on load. DDD findings reviews link evidence as
  // `<clip_url>#t=<scene start>` so the reviewer lands on the exact moment.
  // The fragment never collides with the `?t=<share_token>` query param.
  // Two mechanisms, belt-and-braces: a Media Fragments `#t=` on the src
  // (native seek; the content endpoint supports Range) plus a
  // `loadedmetadata` fallback that sets currentTime directly.
  const startAt = w.kind === 'video' ? timeHashSeconds(window.location.hash) : null
  const videoSrc = startAt != null ? withTimeFragment(contentSrc, startAt) : contentSrc

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
          <h1 className="text-2xl font-semibold text-foreground">{w.title}</h1>
          <p className="text-sm text-muted-foreground">
            {w.kind === 'video' ? 'Video' : 'HTML slideshow'} · {w.owner_email}
            {w.project_slug ? ` · ${w.project_slug}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {shareUrl && (
            <>
              <a
                href={shareUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-muted-foreground hover:text-primary transition-colors"
                title={shareUrl}
              >
                Open public link ↗
              </a>
              <button
                onClick={copyShareUrl}
                className="px-2 py-0.5 text-xs rounded border border-border bg-card text-foreground-secondary hover:bg-muted hover:border-input transition-colors"
              >
                {copied ? 'Copied!' : 'Copy link'}
              </button>
            </>
          )}
          <span
            className={`px-2 py-0.5 text-xs rounded border ${
              w.visibility === 'link'
                ? 'text-success/90 bg-success/10 border-success/25'
                : 'text-foreground-secondary bg-muted/60 border-input'
            }`}
          >
            {w.visibility === 'link' ? 'Public' : 'Private (dimagi)'}
          </span>
        </div>
      </header>

      {w.is_owner && (
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          <button
            className="px-3 py-1 rounded-lg border border-border bg-card text-foreground-secondary hover:bg-muted hover:border-input transition-colors disabled:opacity-50"
            onClick={toggleVisibility}
            disabled={busy}
          >
            {w.visibility === 'link' ? 'Make private' : 'Make public'}
          </button>
          {w.visibility === 'link' && (
            <button
              className="px-3 py-1 rounded-lg border border-border bg-card text-foreground-secondary hover:bg-muted hover:border-input transition-colors disabled:opacity-50"
              onClick={rotateLink}
              disabled={busy}
            >
              Rotate link
            </button>
          )}
          <button
            className="px-3 py-1 rounded-lg border border-destructive/30 text-destructive/90 bg-destructive/5 hover:bg-destructive/10 transition-colors disabled:opacity-50 ml-auto"
            onClick={destroy}
            disabled={busy}
          >
            Delete
          </button>
        </div>
      )}

      <div className="rounded-xl border border-border bg-black overflow-hidden">
        {w.kind === 'video' ? (
          <video
            src={videoSrc}
            controls
            onLoadedMetadata={(e) => {
              if (startAt != null && Math.abs(e.currentTarget.currentTime - startAt) > 0.5) {
                e.currentTarget.currentTime = startAt
              }
            }}
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
            <section className="bg-card border border-border rounded-xl p-5">
              <h2 className="text-[9px] uppercase tracking-wider text-muted-foreground font-semibold mb-3">
                This walkthrough
              </h2>
              <div className="flex flex-col gap-2">
                {siblingLinks.map((l) => (
                  <a
                    key={l.url}
                    href={l.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center gap-3 bg-background/40 hover:bg-background/70 border border-border hover:border-input rounded-lg px-3 py-2 transition-colors"
                  >
                    <span aria-hidden className="shrink-0 text-sm">
                      {siblingIcon(l.kind)}
                    </span>
                    <span className="text-xs text-foreground-secondary truncate flex-1">
                      {l.label}
                    </span>
                    <span
                      aria-hidden
                      className="text-[11px] text-muted-foreground group-hover:text-primary transition-colors shrink-0"
                    >
                      ↗
                    </span>
                  </a>
                ))}
              </div>
            </section>
          )}

          {referenceLinks.length > 0 && (
            <section className="bg-card border border-border rounded-xl p-5">
              <h2 className="text-[9px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                Explore in the app
              </h2>
              <p className="text-xs text-muted-foreground mb-3">
                Destinations shown in this walkthrough — open them live.
              </p>
              <div className="flex flex-col gap-2">
                {referenceLinks.map((l) => (
                  <a
                    key={l.url}
                    href={l.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center gap-3 bg-background/40 hover:bg-background/70 border border-border hover:border-input rounded-lg px-3 py-2 transition-colors"
                  >
                    <span className="text-xs text-foreground-secondary truncate flex-1">
                      {l.label}
                    </span>
                    <span
                      aria-hidden
                      className="text-[11px] text-muted-foreground group-hover:text-primary transition-colors shrink-0"
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
