# PWA navigate-fallback: fail-safe route ownership (issue #345)

## Problem

The PWA service worker (`vite-plugin-pwa`, generated `sw.js`) sets workbox's
`navigateFallback` to the precached SPA shell (`index.html`) and excludes only a
**denylist** of Django-owned prefixes (`/api/`, `/accounts/`, `/admin/`,
`/static/`, `/auth/`, `/health/`). Every same-origin **navigation** whose path
isn't on that denylist is answered from the cached shell — the request never
reaches Django.

An `<iframe src=…>` load is a navigation (a `<video src>` load is not). The DDD
operator console embeds artifacts via `<iframe src="/walkthrough/<id>/content">`
(`frontend/src/components/ddd/RunPackage.tsx` → `HtmlEmbed`). `/walkthrough/` is
not on the denylist, so the SW serves the SPA shell for the iframe navigation;
React Router has no `/content` route and renders `NotFound` inside the full app
chrome — the reported "duplicate outer frame."

The denylist is **fragile by construction**: every new server-rendered/streamed
route must remember to add itself or it is silently swallowed. `/walkthrough/`
is the one that slipped through; there will be others.

## Decision

Adopt **Option C — invert the default to fail-safe** (chosen over A: scope the SW
to `/supervisor`, and B: namespace all content under one prefix).

Rationale: online, an un-fallback'd SPA route still works because Django's
catch-all `spa_view` serves `index.html` for any unknown non-API route — so the
fallback only buys *offline* shell resilience (which matters for the
`/supervisor` PWA + the menubar WKWebView). That makes the allowlist genuinely
low-downside, needs **no URL migration** (unlike B), and avoids the high-risk
SW-scope/`Service-Worker-Allowed`/asset-precache-scope surgery of A while keeping
the offline shell everywhere it's wanted.

**The rule:** the SW serves the SPA shell **only** for known SPA route prefixes
(an *allowlist*); every other navigation goes to the **network**. An unknown path
now fails safe — a future server route reaches Django by default. A forgotten
*SPA* route only loses *offline* fallback (online it still resolves via the
server catch-all).

## Design

### 1. Extract the routing rule into a tested module

New `frontend/src/pwa/navigation-fallback.ts` exports two regex arrays with the
rule documented in a header comment; `vite.config.ts` imports them instead of
inlining literals. This turns the classification into a testable, documented unit
(the "documented structural rule" the issue asks for).

- `NAVIGATE_FALLBACK_ALLOWLIST` — every top-level SPA prefix in `router.tsx`,
  each tolerant of the optional labs `(canopy/)?` mount:
  root `/`, `w/`, `supervisor`, `insights`, `system`, `settings`, `sessions`,
  `schedules`, `activity`, `timeline`, `shareouts`, `walkthroughs`, `agents`,
  `ddd`, `ddd-plans`, `reviews`, `review/`, `walkthrough/`, `share/`,
  `ddd-release/`.
- `NAVIGATE_FALLBACK_DENYLIST` — the existing Django prefixes **plus** the two
  server-stream carve-outs that overlap SPA prefixes:
  `^/(canopy/)?walkthrough/.*/content$` and the legacy
  `^/(canopy/)?w/.*/content$`. In workbox the denylist wins over the allowlist,
  so `/walkthrough/<uuid>` (viewer shell, allowlisted) still gets the shell while
  `/walkthrough/<uuid>/content` (denylisted) escapes to the network. Keeping a
  broad `walkthrough/` in the allowlist is safe precisely because the `/content`
  carve-out lives on the denylist.

A `navigation-fallback.test.ts` (+ a small `shouldServeShell(path)` helper)
asserts the matrix:
- SPA routes (`/`, `/supervisor`, `/w/connect/ddd/x/y`, `/walkthrough/<uuid>`) →
  shell.
- Server streams (`/walkthrough/<uuid>/content`, legacy `/w/<uuid>/content`) →
  network.
- Django prefixes (`/api/…`, `/accounts/…`) → network.
- Unknown (`/foo/bar`) → network (the fail-safe case).
- Each of the above also under the `/canopy/` labs prefix.

### 2. Tokenize the console embeds (parity with the release page) + unify

`apps/runs/aggregate.py`: the console `_artifact_payload` returns tokenless
content/viewer URLs (`_content_url`/`_viewer_url`), while the release
`_release_artifact` wraps them in `_tok(…)` (appends `?t=<share_token>` for
`visibility=link` artifacts). Make `_content_url`/`_viewer_url` apply `_tok`
themselves. `_tok` returns the base unchanged for non-link artifacts, so this is
a safe no-op for private/member reads and correct parity everywhere. Once
`_artifact_payload` tokenizes it is identical to `_release_artifact`, so delete
`_release_artifact` and point its two call sites at `_artifact_payload`.

Effect: even if a console-embedded artifact's workspace differs from the viewer's
active workspace, a `visibility=link` artifact still streams via its own token —
matching how the release page already behaves.

### 3. Bare 404 on a failed content request (never the SPA)

`config/urls.py`: widen the content route from `<uuid:wid>` to `<str:wid>` so a
malformed id resolves **server-side** to a real 404 instead of falling through to
the SPA catch-all. `apps/walkthroughs/streaming.py::_get_or_404` gains
`django.core.exceptions.ValidationError` in its `except` (an invalid-UUID string
passed as `pk` raises `ValidationError`, not `ValueError`), so any
`/walkthrough/<anything>/content` returns a bare 404 for a bad/unknown id and the
existing 404-on-bad-token path is unchanged. The legacy `/w/<uuid>/content`
redirect target reverses fine against the widened route.

### 4. Document the rule

- The header comment in `navigation-fallback.ts` is the canonical statement of
  the rule ("SPA shell only for allowlisted SPA prefixes; everything else →
  network; new server routes are safe by default").
- Add a short "Design Decisions" entry in `CLAUDE.md` pointing at this spec and
  the module.

## Out of scope / YAGNI

- Not scoping the SW to `/supervisor` (Option A) — highest-risk, removes offline
  shell where we still want it.
- Not migrating content URLs under a new prefix (Option B) — no URL churn /
  legacy-redirect burden needed to get the fail-safe property.

## Acceptance criteria (from the issue)

- [ ] Console **Walkthrough slides** + **Documentation** panels render the real
      artifact, not a nested app / "Page not found".
- [ ] A navigation to `/walkthrough/<id>/content` (valid token or member session)
      returns artifact bytes, not the shell.
- [ ] A failed content request returns a bare 404 (no app chrome).
- [ ] A documented, structural rule such that a *new* server route can't be
      silently swallowed (the allowlist inversion + the module's header comment).
- [ ] PWA install/entry via `/supervisor` still works (standalone, correct
      `start_url`, offline shell for the WKWebView).
