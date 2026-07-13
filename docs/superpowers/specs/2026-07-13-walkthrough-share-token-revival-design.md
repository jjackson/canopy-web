# Walkthrough share-token revival

**Date:** 2026-07-13
**Status:** Approved for implementation
**Supersedes (partially):** `2026-06-08-tokenless-narrative-visibility-design.md` — the
tokenless model stays for **reviews**; this spec re-gates **walkthroughs** on their
dormant share token.

## Why

The tokenless model shipped in PR #105 made `visibility=link` mean "anyone with the
bare URL" — the walkthrough UUID is the only secret. That URL is the same one that
appears in browser history, ACE/DDD package links, Slack unfurls, and screen shares.
The owner's verdict after living with it: *"having the public-ness of the url be based
on the url is even worse"* than tokens. Tokens restore two properties:

1. **The canonical URL is not a capability.** Knowing where a walkthrough lives no
   longer grants anonymous read access.
2. **Revocability.** A leaked public link can be rotated dead without deleting the
   artifact or changing where it lives.

The reversibility hedge in the tokenless spec (dormant `share_token` column +
`ensure_share_token()` / `rotate_share_token()` model methods, and the `?t=` query
param deliberately reserved in the viewer's URL scheme) is exactly what this spec
cashes in.

## Decisions (made with the owner)

- **Token required, no grace period.** Anonymous read of a public walkthrough
  requires `?t=<share_token>`. Bare-UUID anonymous access 404s — same response as
  a private walkthrough, so existence still doesn't leak. Existing tokenless public
  links in the wild break; accepted as one-time re-share cost.
- **Walkthroughs only.** Reviews keep tokenless link-visibility (their links flow
  to the DDD supervisor, not outward, and submit already requires login). Reviews
  can follow later; their model methods stay dormant.
- **URL shape: query param on the canonical URL** (`/walkthrough/<uuid>?t=<token>`),
  not a separate `/share/...` route. One page, one route; sessions keep their
  token-is-the-URL model, walkthroughs keep theirs.

## Design

### Backend

**Access rule** (both enforcement points):

```
anonymous read allowed ⇔ visibility == link AND request "t" param == share_token (non-empty)
```

Session-authenticated users are unaffected (any logged-in Dimagi user can read any
walkthrough, as today). Comparison uses `secrets.compare_digest`; an empty/absent
stored token never matches.

Enforcement points (the only two anonymous read surfaces):

- `apps/walkthroughs/api.py::get_walkthrough` (GET `/api/walkthroughs/{wid}/`,
  `auth=None`) — read `request.GET.get("t")`.
- `apps/walkthroughs/streaming.py::walkthrough_content`
  (GET `/walkthrough/<uuid>/content`) — same check; the `?t=` param coexists with
  Range headers and the legacy `/w/<uuid>/content` `RedirectView` already preserves
  query strings.

**Minting:**

- Data migration: `ensure_share_token()` semantics for every existing row with
  `visibility=link` (bulk: generate `secrets.token_urlsafe(24)` per row).
- `POST /api/walkthroughs/` (upload) with `visibility=link` → mint on create.
- `PATCH /api/walkthroughs/{wid}/` flipping to `link` → `ensure_share_token()`.
- Flipping to `private` keeps the token — re-publishing later revives the same
  link; invalidation is an explicit rotate, not a side effect.

**Rotate endpoint:** `POST /api/walkthroughs/{wid}/rotate-token` — owner-only
(404 for non-owners, matching the sessions app's pattern at
`apps/session_sharing/api.py`), calls `rotate_share_token()`, returns the new
`share_url`.

**Schema:** `WalkthroughDetailOut` gains `share_url: str | None` — the absolute
public URL (`{scheme}://{host}{FORCE_SCRIPT_NAME}/walkthrough/<uuid>?t=<token>`),
present **only when `is_owner` and `visibility=link`**; `None` otherwise. The raw
token is never exposed as its own field and never appears in list responses.

### Frontend (`frontend/src/pages/WalkthroughViewerPage.tsx` + `frontend/src/api/walkthroughs.ts`)

- **Owner controls:** "Open public link ↗" and "Copy link" switch from the bare
  page URL to `share_url` from the detail response. New "Rotate link" action
  (confirm dialog: old links stop working) calls the rotate endpoint and swaps in
  the returned `share_url`.
- **Anonymous visitor with `?t=`:** the page threads the token from
  `window.location.search` into `getWalkthrough(id, token)` and
  `walkthroughContentUrl(id, token)` so both the detail fetch and the
  `<video>`/`<iframe>` src carry it. The existing `#t=<seconds>` video fragment is
  unaffected (fragment vs query param, per the existing comment in the file).
- **Legacy redirect fix:** `WorkspaceIndex` in `frontend/src/router.tsx` currently
  drops the query string when redirecting `/w/<uuid>` → `/walkthrough/<uuid>`;
  preserve `location.search` (and hash) in the `Navigate`.
- The client-side auth allowlist for `/walkthrough/` (PR #192) stays — the shell
  renders for anonymous visitors; the API self-enforces. A missing/wrong token
  surfaces as the existing 404 error state.
- Regenerate `frontend/src/api/generated.ts` (`npm run gen:api`).

### Known breakage (accepted, with follow-ups)

- Tokenless public walkthrough links already shared stop working for anonymous
  visitors (viewer shows "not found"; logging in fixes it for Dimagi folks).
- **Producer follow-ups (canopy plugin repo, out of scope here):**
  `canopy:walkthrough-share` and `canopy:ddd-upload` print/store public URLs —
  they must read `share_url` from the upload/detail response. Until then, links
  they publish are login-gated rather than public.
- `Walkthrough.links[]` entries pointing at sibling walkthroughs (video ↔ deck)
  are stored bare; anonymous cross-navigation between public siblings breaks until
  producers store tokened URLs. Dimagi-authed navigation is unaffected.

### Tests (`tests/test_walkthroughs*.py`, extend existing patterns)

1. Anonymous + correct `?t=` on public walkthrough → 200 (detail and content).
2. Anonymous, no/wrong token on public walkthrough → 404 (detail and content).
3. Anonymous + correct token on **private** walkthrough → 404 (visibility wins).
4. Session-authed, no token → 200 regardless of visibility.
5. PATCH to `link` mints a token; PATCH to `private` keeps it.
6. Rotate: owner-only (non-owner 404), old token 404s afterward, new one works.
7. `share_url` present only for owner + link; absent for anonymous/non-owner/private.
8. Migration mints tokens for pre-existing `visibility=link` rows.

### Deploy

Has a migration → `gh workflow run "Deploy to Labs (AWS)" --ref main -f run_migrations=true`.
