# Tokenless narrative-level visibility — design

**Date:** 2026-06-08
**Status:** Approved (design)
**Author:** Jonathan Jackson (+ Claude)

## Problem

The walkthrough viewer exposes three overlapping sharing controls — a green
"Shareable link" status badge, a "Make private" toggle, a "Copy share link"
button, and a "Rotate token" button. The mental model is confusing: "link"
visibility means *anyone with a secret `?t=<token>` query param*, so there are
two secrets (the UUID and the token), a rotate-to-revoke flow, and a copy-link
button that mints tokens as a side effect.

In practice the user is "mostly making everything public for now," and sharing
happens at the level of a **DDD narrative** (a story that bundles a hero video,
a deck, docs, and review surfaces), not a single artifact. Toggling one
walkthrough leaves its siblings at their original visibility.

## Goals

- One **Public / Private** toggle that operates on an entire narrative and
  cascades to every artifact and review surface under it.
- Drop share tokens from the UI entirely. "Public" means the plain
  `/w/<id>` and `/review/<id>` URLs load for anyone — the UUID is the only
  secret.
- Keep a single simplified per-item toggle on the walkthrough viewer for
  standalone (non-narrative) walkthroughs.
- New artifacts keep defaulting to **private**.

## Non-goals

- No per-run toggle (narrative-level only).
- No multi-tenant / per-narrative ownership model — single-tenant V1, any
  authenticated Dimagi user may toggle.
- Not deleting the `share_token` column or model methods — left dormant so the
  change is reversible ("remove tokens *for now*").

## Background: the data model

There is **no Narrative or Run table.** Narratives and runs are read-time
aggregations (`apps/runs/aggregate.py`) over two row types that carry a
`narrative_slug` (and `run_id`):

- `Walkthrough` (`apps/walkthroughs/models.py`) — video / deck / docs / clip
  artifacts. Has `visibility` (`private` | `link`), `share_token`, `owner`,
  `run_id`, `narrative_slug`, `role`.
- `ReviewRequest` (`apps/reviews/models.py`) — narrative-agreement review
  surfaces. Same `visibility` / `share_token` semantics, plus `narrative_slug`,
  `version`, `gate`, `status`.

So a "narrative toggle" is an endpoint that flips `visibility` on every
`Walkthrough` and `ReviewRequest` sharing a `narrative_slug`.

### Existing auth scaffolding we mirror

`apps/common/middleware.py` is default-deny with an allowlist. Reviews already
implement tokenless-ish public read via:

- `_is_review_link(path)` — allowlists the `/review/<uuid>/` SPA shell and the
  per-review API endpoints (but **not** the bare collection `POST
  /api/reviews/`).
- Per-route `auth=None` on `get_review` / `submit_review`, with
  `_can_read` / `_can_write` self-enforcing inside the handler.

Walkthrough content (`/w/<uuid>/content`, a bare Django view in
`streaming.py`) is allowlisted via `_is_walkthrough_content`, but the SPA shell
`/w/<uuid>` and the detail API `GET /api/walkthroughs/<uuid>/` are **not** —
today an anonymous holder can fetch the raw content stream but cannot load the
full viewer page chrome. This design fixes that for public walkthroughs.

## Redefining `visibility`

Keep the stored enum values `private` and `link` (no data migration of
choices). Redefine and relabel:

| Stored value | Old meaning | New meaning | UI label |
|---|---|---|---|
| `private` | Dimagi-OAuth only | Dimagi-OAuth only | **Private** |
| `link` | anyone with `?t=<token>` | anyone with the link (tokenless) | **Public** |

`share_token` is no longer read or minted. The column and the
`ensure_share_token` / `rotate_share_token` methods remain but become dead.

### Access matrix after this change

| Surface | Private | Public (`link`) |
|---|---|---|
| `/w/<id>` viewer shell | Dimagi login | anyone with URL |
| `GET /api/walkthroughs/<id>/` detail | Dimagi login | anyone with URL |
| `/w/<id>/content` stream | owner/Dimagi login | anyone with URL |
| `/review/<id>` read | Dimagi login | anyone with URL |
| `POST /api/reviews/<id>/submit/` (approve/redraft) | Dimagi login | **Dimagi login only** |

**Deliberate tradeoffs:**
- Dropping tokens removes per-link revocation. To cut off a leaked URL, flip the
  narrative (or item) back to Private.
- Review **submission stays authenticated-only** even when the narrative is
  public-readable — anonymous internet users must not be able to approve or
  redraft narratives. The previous token-based anonymous-approval flow is
  removed (accepted by product owner).

## Backend changes

### 1. Narrative visibility cascade endpoint

`PATCH /api/ddd/narratives/{slug}/visibility/` (in `apps/runs/api.py`).

- Body: `{ "visibility": "private" | "link" }`.
- Effect: `Walkthrough.objects.filter(narrative_slug=slug).update(visibility=...)`
  and `ReviewRequest.objects.filter(narrative_slug=slug).update(visibility=...)`.
  Also handle rows that carry the slug only via `run_id`
  (`narrative_slug_from_run_id`) — match the same set the aggregate uses, so
  the toggle covers exactly what the narrative page displays.
- Auth: `session_auth` (any authenticated Dimagi user).
- Response: `{ slug, visibility, walkthroughs_updated, reviews_updated }`.

### 2. Narrative aggregate exposes computed visibility

In `apps/runs/aggregate.py` + the narrative schema (`apps/runs/schemas.py`),
add a computed `visibility` to the narrative payload:

- `"public"` if every matched row is `link`.
- `"private"` if every matched row is `private`.
- `"mixed"` if rows disagree (e.g. legacy data). The toggle resolves mixed by
  setting all rows to the chosen value.

The UI renders the toggle from this field; "mixed" shows as an indeterminate
state biased toward Private.

### 3. Walkthrough streaming gate (`apps/walkthroughs/streaming.py`)

Replace the token check:

```python
# before
token_ok = (w.visibility == VISIBILITY_LINK and bool(w.share_token)
            and token == w.share_token)
if not (is_authed or token_ok): raise Http404

# after
if not (request.user.is_authenticated
        or w.visibility == Walkthrough.VISIBILITY_LINK):
    raise Http404("walkthrough not found")
```

### 4. Walkthrough detail GET becomes tokenless-public

`get_walkthrough` (`apps/walkthroughs/api.py`): set `auth=None`, self-enforce:

```python
if not (request.user.is_authenticated
        or w.visibility == Walkthrough.VISIBILITY_LINK):
    raise Http404  # don't leak private existence
```

### 5. Middleware allowlist (`apps/common/middleware.py`)

Add `_is_walkthrough_link(path)`, mirroring `_is_review_link`:

- allow the SPA shell `/w/<uuid>` (path starts with `/w/`),
- allow `GET /api/walkthroughs/<uuid>/` (a detail path under
  `/api/walkthroughs/` that is not the bare collection),
- **not** the bare collection `POST /api/walkthroughs/` (upload still requires
  auth).

Wire it into `LoginRequiredMiddleware.__call__` alongside the existing
`_is_walkthrough_content` / `_is_review_link` checks. (`/w/<uuid>/content`
remains covered by `_is_walkthrough_content`.)

### 6. Reviews access checks (`apps/reviews/api.py`)

- `_can_read`: `request.user.is_authenticated or review.visibility ==
  VISIBILITY_LINK`. (Drop the token comparison.)
- `_can_write`: `request.user.is_authenticated` (owner or any Dimagi user).
  Drop the token-write path.

### 7. Remove dead surfaces

- Delete the `POST /api/walkthroughs/{wid}/rotate-token/` route and
  `WalkthroughRotateTokenOut` schema.
- Remove `share_token` from `WalkthroughDetailOut` and `ReviewRequestOut`
  response schemas (and the `_detail_payload` builder).
- Stop auto-minting tokens in `patch_walkthrough`, `create` (upload), and
  review creation.
- Keep the model column + methods (dormant).

### 8. Regenerate OpenAPI types

`cd frontend && npm run gen:api` after schema changes (or let `regen-openapi`
CI do it).

## Frontend changes

### 9. DDD narrative page (`NarrativeLanding`)

Add a single **Public / Private** toggle in the narrative header, bound to the
aggregate `visibility`. Calls `PATCH /api/ddd/narratives/{slug}/visibility/`,
optimistically updates, shows "mixed" as a distinct (indeterminate) state that
resolves on click. Add the API client wrapper in the runs/ddd api module.

### 10. Walkthrough viewer (`WalkthroughViewerPage`)

- Remove "Copy share link" and "Rotate token" buttons and their handlers
  (`copyShareLink`, `rotate`), plus the `rotateWalkthroughToken` client fn.
- Keep one **Public / Private** toggle (the existing `toggleVisibility`, now
  labeled Public/Private) and the status badge (green "Public" /
  gray "Private").
- Iframe `src` drops the `?t=` token: `contentSrc =
  withSceneHash(walkthroughContentUrl(w.id), window.location.hash)`. Remove the
  `viewerToken` plumbing.

### 11. List / package pages

No functional change. If any list item renders token/share affordances, drop
them. Run package page (`RunPackage`) continues to link to artifacts by clean
URL.

## Testing

- **Backend** (`uv run pytest`):
  - Cascade endpoint flips all walkthroughs + reviews for a slug; counts
    correct; covers rows matched via `run_id`-derived slug.
  - Aggregate `visibility` returns public / private / mixed correctly.
  - Streaming gate: public content served to anonymous (no token); private
    404s anonymous; owner always served.
  - Walkthrough detail GET: public reachable anonymous, private 404s anonymous.
  - Reviews: public read anonymous OK; submit anonymous → 401/403; submit
    authenticated OK.
  - Middleware allowlist: `/w/<uuid>` and `GET /api/walkthroughs/<uuid>/` pass
    for anonymous; `POST /api/walkthroughs/` and `/api/reviews/` (collection)
    still gated.
  - Removed `rotate-token` route returns 404; `share_token` absent from
    detail/review responses.
- **Frontend** (`cd frontend && npm run build`): type-checks against
  regenerated OpenAPI types (no `share_token` / rotate references remain).
- **Manual:** flip a narrative to Public, open `/w/<id>` and `/review/<id>` in a
  logged-out browser, confirm both load and the video scrubs; flip back to
  Private, confirm both 404 / redirect.

## Rollout

Single PR. No data migration required (enum values unchanged; existing `link`
rows transparently become tokenless-public, existing tokens simply stop being
checked). Reversible by restoring the token checks and UI; the `share_token`
data is preserved.
