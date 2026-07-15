import { describe, it, expect, vi } from 'vitest'
import { rewriteForWorkspace } from './client.v2'

// Regression test for the workspace-rewrite middleware eating request bodies.
//
// The middleware used to rebuild the rewritten request via
// `new Request(url, request)`. That constructor form adopts the source
// Request's body as a *live stream*, which consumes/disturbs it — so every
// workspace-scoped POST/PATCH/PUT died at the network layer with
// "TypeError: Failed to fetch" before it ever left the browser (no response,
// no status). A test that only checks the rewritten URL would NOT have
// caught this — the URL rewrite was always correct; only the body died.
describe('rewriteForWorkspace', () => {
  it('preserves a JSON POST body while rewriting onto the tenant path', async () => {
    const payload = { title: 'accept', note: 'flip to accepted' }
    const original = new Request('http://localhost/api/agents/echo/tasks/1/commands', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    const rewritten = await rewriteForWorkspace(original, 'acme')

    // URL rewrite: /api/<app>/… -> /api/w/:ws/<app>/…
    expect(new URL(rewritten.url).pathname).toBe(
      '/api/w/acme/agents/echo/tasks/1/commands',
    )
    expect(rewritten.method).toBe('POST')

    // The assertion that actually matters: the body must have survived the
    // rewrite. Against the bug, this throws/reads empty because the source
    // stream was already disturbed by `new Request(url, request)`.
    await expect(rewritten.json()).resolves.toEqual(payload)
  })

  it('rewrites a bodyless GET without attaching a body', async () => {
    const original = new Request('http://localhost/api/projects/', { method: 'GET' })

    const rewritten = await rewriteForWorkspace(original, 'acme')

    expect(new URL(rewritten.url).pathname).toBe('/api/w/acme/projects/')
    expect(rewritten.method).toBe('GET')
    expect(rewritten.body).toBeNull()
  })

  it('leaves an unmatched URL under the same origin (identity check via manual prefix use)', async () => {
    // rewriteForWorkspace itself doesn't prefix-match (that's done by the
    // caller in onRequest); this test just documents the pure rewrite math
    // for a nested path, guarding against an off-by-one in the slice().
    const original = new Request('http://localhost/api/walkthroughs/abc123/', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ visibility: 'link' }),
    })

    const rewritten = await rewriteForWorkspace(original, 'dimagi')

    expect(new URL(rewritten.url).pathname).toBe('/api/w/dimagi/walkthroughs/abc123/')
    await expect(rewritten.json()).resolves.toEqual({ visibility: 'link' })
  })

  // Node's fetch/Request implementation tolerates the literal buggy pattern
  // (`new Request(url, request)`) in a way Chrome does not — verified by hand
  // against a local HTTP server, the two-arg form neither throws nor drops
  // the body under Node. So the black-box assertions above, on their own,
  // would NOT fail if this function regressed back to that exact line — only
  // Playwright (real Chromium) reproduces the browser-only "Failed to fetch"
  // network-layer failure. This white-box check closes that gap for CI: it
  // pins down *how* the body must be obtained (read eagerly via a buffering
  // method) rather than only *what* the end state looks like, so reverting to
  // handing the constructor a live stream fails here even though it wouldn't
  // fail on body-content alone.
  it('reads the source body eagerly instead of handing the constructor a live stream', async () => {
    const original = new Request('http://localhost/api/agents/echo/tasks/1/commands', {
      method: 'POST',
      body: JSON.stringify({ ok: true }),
    })
    const arrayBufferSpy = vi.spyOn(original, 'arrayBuffer')

    await rewriteForWorkspace(original, 'acme')

    expect(arrayBufferSpy).toHaveBeenCalled()
  })
})
