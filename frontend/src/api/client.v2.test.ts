import { describe, it, expect } from 'vitest'
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

  it('rewrites a nested matched path without an off-by-one in the prefix slice', async () => {
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
  // asserts on `original.bodyUsed`, which flips false -> true the moment the
  // body is read via ANY buffering method (arrayBuffer/text/json/blob) — so
  // it discriminates against the bug (which leaves it false, handing the
  // constructor a live, unread stream) without pinning which specific method
  // the implementation uses to do the reading. Caveat: a `.clone()`-based fix
  // wouldn't touch `original.bodyUsed` at all (the clone's body is read
  // instead), so this assertion — like the ones above — would not catch a
  // regression to that pattern either. It only guards the "hand the
  // constructor a live stream" failure mode this test exists for.
  it('reads the source body eagerly instead of handing the constructor a live stream', async () => {
    const original = new Request('http://localhost/api/agents/echo/tasks/1/commands', {
      method: 'POST',
      body: JSON.stringify({ ok: true }),
    })

    expect(original.bodyUsed).toBe(false)

    await rewriteForWorkspace(original, 'acme')

    expect(original.bodyUsed).toBe(true)
  })
})
