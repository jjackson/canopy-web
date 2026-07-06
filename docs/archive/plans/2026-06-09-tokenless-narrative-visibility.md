# Tokenless Narrative-Level Visibility Implementation Plan

**Status:** Shipped (PR #105, 2026-06-09) — historical record of the build, not current-state. All 12 tasks executed; checkboxes left unticked as a build artifact.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-artifact share tokens with a tokenless Public/Private model, and add a narrative-level toggle that cascades visibility to every walkthrough and review under a narrative.

**Architecture:** `visibility` keeps its stored enum (`private`/`link`) but `link` now means "anyone with the URL" — no `?t=` token. Streaming, detail, and review-read gates drop the token check; the login middleware allowlists the walkthrough viewer shell + detail GET (mirroring the existing review-link allowlist). A new `PATCH /api/ddd/narratives/{slug}/visibility/` bulk-updates all rows sharing the narrative. The DDD narrative page gets one toggle; the walkthrough viewer keeps one simplified toggle for standalone artifacts. Review *submission* stays authenticated-only.

**Tech Stack:** Django 5 + Django Ninja, pytest, React 19 + Vite + TypeScript, openapi-typescript.

**Design doc:** `docs/superpowers/specs/2026-06-08-tokenless-narrative-visibility-design.md`

---

## File Structure

**Backend (modify):**
- `apps/walkthroughs/streaming.py` — drop token check in the content gate (Task 1)
- `apps/walkthroughs/api.py` — detail GET `auth=None` + self-enforce; remove rotate route; stop minting tokens (Tasks 2, 6)
- `apps/walkthroughs/schemas.py` — drop `share_token` from detail out; remove rotate out schema (Task 6)
- `apps/common/middleware.py` — allowlist walkthrough shell + detail GET (Task 3)
- `apps/reviews/api.py` — tokenless read, authenticated-only write; drop `share_token` from payload (Task 4, 6)
- `apps/reviews/schemas.py` — drop `share_token` from review out schemas (Task 6)
- `apps/runs/aggregate.py` — compute narrative `visibility`; add `set_narrative_visibility()` (Task 5)
- `apps/runs/api.py` — `PATCH /narratives/{slug}/visibility/` (Task 5)
- `apps/runs/schemas.py` — `visibility` on `NarrativeDetailOut`; new patch in/out schemas (Task 5)

**Backend (test):**
- `tests/test_visibility_walkthroughs.py` — new (Tasks 1, 2, 3)
- `tests/test_visibility_reviews.py` — new (Task 4)
- `tests/test_narrative_visibility.py` — new (Task 5)

**Frontend (modify):**
- `frontend/src/api/ddd.ts` — `visibility` field + `setNarrativeVisibility()` + `patch` helper (Task 8)
- `frontend/src/components/ddd/NarrativeLanding.tsx` — narrative toggle (Task 9)
- `frontend/src/api/walkthroughs.ts` — remove rotate fn; drop token from content URL (Task 10)
- `frontend/src/pages/WalkthroughViewerPage.tsx` — single toggle, remove copy/rotate (Task 11)
- `frontend/src/api/generated.ts` — regenerated (Task 7)

---

## Task 1: Walkthrough streaming gate goes tokenless

**Files:**
- Modify: `apps/walkthroughs/streaming.py` (the `token`/`token_ok` block, ~lines 64–73)
- Test: `tests/test_visibility_walkthroughs.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_visibility_walkthroughs.py`:

```python
"""Tokenless visibility behaviour for the walkthrough content stream + detail."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.walkthroughs.models import Walkthrough


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="owner@dimagi.com", email="owner@dimagi.com",
    )


def _make(owner, **kw):
    defaults = dict(
        title="Demo", kind="video", owner=owner,
        drive_file_id="file-1", drive_folder_id="folder-1",
        content_type="video/mp4", size_bytes=10,
    )
    defaults.update(kw)
    return Walkthrough.objects.create(**defaults)


# Streaming returns bytes; stub the Drive download so tests stay offline.
def _stub_download():
    return patch(
        "apps.walkthroughs.streaming.storage.download",
        return_value=(b"data", "video/mp4", 4, 4),
    )


@override_settings(REQUIRE_AUTH=True)
def test_public_content_served_to_anonymous_without_token(owner):
    w = _make(owner, visibility="link")
    with _stub_download():
        resp = Client().get(f"/w/{w.id}/content")
    assert resp.status_code == 200


@override_settings(REQUIRE_AUTH=True)
def test_private_content_404s_anonymous(owner):
    w = _make(owner, visibility="private")
    resp = Client().get(f"/w/{w.id}/content")
    assert resp.status_code == 404


@override_settings(REQUIRE_AUTH=True)
def test_owner_sees_private_content(owner):
    w = _make(owner, visibility="private")
    client = Client()
    client.force_login(owner)
    with _stub_download():
        resp = client.get(f"/w/{w.id}/content")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_visibility_walkthroughs.py::test_public_content_served_to_anonymous_without_token -v`
Expected: FAIL — anonymous public request 404s because the gate still requires a token.

- [ ] **Step 3: Edit the gate**

In `apps/walkthroughs/streaming.py`, replace the token block:

```python
    token = request.GET.get("t", "")
    is_authed = request.user.is_authenticated
    token_ok = (
        w.visibility == Walkthrough.VISIBILITY_LINK
        and bool(w.share_token)
        and token == w.share_token
    )
    if not (is_authed or token_ok):
        raise Http404("walkthrough not found")
```

with:

```python
    # Tokenless public access: visibility=link means anyone with the URL.
    # The UUID is the only secret. Private stays session-gated.
    if not (
        request.user.is_authenticated
        or w.visibility == Walkthrough.VISIBILITY_LINK
    ):
        raise Http404("walkthrough not found")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_visibility_walkthroughs.py -v`
Expected: the three streaming tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/streaming.py tests/test_visibility_walkthroughs.py
git commit -m "feat(walkthroughs): tokenless public content streaming"
```

---

## Task 2: Walkthrough detail GET becomes anonymously reachable for public

**Files:**
- Modify: `apps/walkthroughs/api.py` (`get_walkthrough`, ~lines 332–344)
- Test: `tests/test_visibility_walkthroughs.py` (append)

Note: the detail API is gated by `LoginRequiredMiddleware` before Ninja runs. This task makes the Ninja route `auth=None` and self-enforce; Task 3 opens the middleware. Until Task 3 lands, the anonymous-detail test will still 401 — so write that test in Task 3.

- [ ] **Step 1: Write the failing test (self-enforce branch)**

Append to `tests/test_visibility_walkthroughs.py`:

```python
def test_detail_handler_404s_private_for_anonymous(owner):
    """With auth=None the handler itself must hide private rows from anonymous."""
    from django.test import RequestFactory
    from django.contrib.auth.models import AnonymousUser
    from apps.walkthroughs.api import get_walkthrough

    w = _make(owner, visibility="private")
    req = RequestFactory().get(f"/api/walkthroughs/{w.id}/")
    req.user = AnonymousUser()
    with pytest.raises(Exception):  # Http404 / ProblemError → not found
        get_walkthrough(req, w.id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_visibility_walkthroughs.py::test_detail_handler_404s_private_for_anonymous -v`
Expected: FAIL — handler currently returns the payload for anyone (no guard).

- [ ] **Step 3: Add `auth=None` + guard to `get_walkthrough`**

In `apps/walkthroughs/api.py`, change the decorator and body:

```python
@router.get(
    "/{wid}/",
    response=WalkthroughDetailOut,
    auth=None,  # Public (visibility=link) walkthroughs load without a session.
    summary="Get walkthrough detail",
)
def get_walkthrough(request: HttpRequest, wid: UUID) -> WalkthroughDetailOut:
    _require_enabled()
    w = _get_or_404(wid)
    if not (
        request.user.is_authenticated
        or w.visibility == Walkthrough.VISIBILITY_LINK
    ):
        raise Http404("walkthrough not found")  # don't leak private existence
    is_owner = request.user.is_authenticated and w.owner_id == request.user.id
    return WalkthroughDetailOut.model_validate(_detail_payload(w, is_owner=is_owner))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_visibility_walkthroughs.py::test_detail_handler_404s_private_for_anonymous -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/api.py tests/test_visibility_walkthroughs.py
git commit -m "feat(walkthroughs): detail GET self-enforces tokenless public access"
```

---

## Task 3: Middleware allowlists the walkthrough shell + detail GET

**Files:**
- Modify: `apps/common/middleware.py` (add `_is_walkthrough_link`, wire into `__call__`)
- Test: `tests/test_visibility_walkthroughs.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_visibility_walkthroughs.py`:

```python
@override_settings(REQUIRE_AUTH=True)
def test_public_detail_api_reachable_anonymous(owner):
    w = _make(owner, visibility="link")
    resp = Client().get(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(w.id)


@override_settings(REQUIRE_AUTH=True)
def test_private_detail_api_404s_anonymous(owner):
    w = _make(owner, visibility="private")
    resp = Client().get(f"/api/walkthroughs/{w.id}/")
    # Reaches the handler (allowlisted) and the handler hides it.
    assert resp.status_code == 404


@override_settings(REQUIRE_AUTH=True)
def test_walkthrough_shell_served_to_anonymous(owner):
    w = _make(owner, visibility="link")
    resp = Client().get(f"/w/{w.id}")
    assert resp.status_code == 200  # SPA shell, not redirected to login


@override_settings(REQUIRE_AUTH=True)
def test_walkthrough_collection_still_gated(db):
    # The list/upload collection must NOT be public.
    resp = Client().get("/api/walkthroughs/")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_visibility_walkthroughs.py -k "anonymous or shell or collection" -v`
Expected: the public-detail and shell tests FAIL (401/302) — middleware blocks them.

- [ ] **Step 3: Add the allowlist helper + wire it in**

In `apps/common/middleware.py`, add after `_is_review_link` (~line 43):

```python
def _is_walkthrough_link(request) -> bool:
    # The walkthrough viewer SPA shell (/w/<uuid>) and the per-walkthrough
    # detail GET self-enforce tokenless public access, so let anonymous
    # callers through the middleware. The bare collection (/api/walkthroughs/)
    # is NOT included — list/upload still require auth. /w/<uuid>/content is
    # already covered by _is_walkthrough_content.
    path = request.path
    if path.startswith("/w/"):
        return True
    return (
        request.method == "GET"
        and path.startswith("/api/walkthroughs/")
        and path != "/api/walkthroughs/"
    )
```

Then add it to the bypass condition in `__call__`:

```python
        if (
            request.user.is_authenticated
            or _is_public(request.path)
            or _is_walkthrough_content(request.path)
            or _is_walkthrough_link(request)
            or _is_review_link(request.path)
        ):
            return self.get_response(request)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_visibility_walkthroughs.py -v`
Expected: all tests PASS (including Task 1/2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/common/middleware.py tests/test_visibility_walkthroughs.py
git commit -m "feat(auth): allowlist walkthrough shell + detail GET for public links"
```

---

## Task 4: Reviews — tokenless read, authenticated-only write

**Files:**
- Modify: `apps/reviews/api.py` (`_can_read`, `_can_write`; remove now-unused `_token_ok` use)
- Test: `tests/test_visibility_reviews.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_visibility_reviews.py`:

```python
"""Tokenless review read; authenticated-only submit."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.reviews.models import ReviewRequest


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="owner@dimagi.com", email="owner@dimagi.com",
    )


def _review(owner, **kw):
    defaults = dict(
        run_id="demo-2026-06-09-001",
        narrative_slug="demo",
        gate="narrative-agreement",
        request_json={"narrative": "A story"},
        owner=owner,
    )
    defaults.update(kw)
    return ReviewRequest.objects.create(**defaults)


@override_settings(REQUIRE_AUTH=True)
def test_public_review_read_anonymous(owner):
    r = _review(owner, visibility="link")
    resp = Client().get(f"/api/reviews/{r.id}/")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(r.id)


@override_settings(REQUIRE_AUTH=True)
def test_private_review_404s_anonymous(owner):
    r = _review(owner, visibility="private")
    resp = Client().get(f"/api/reviews/{r.id}/")
    assert resp.status_code in (403, 404)


@override_settings(REQUIRE_AUTH=True)
def test_public_review_submit_blocked_for_anonymous(owner):
    r = _review(owner, visibility="link")
    resp = Client().post(
        f"/api/reviews/{r.id}/submit/",
        data={"decisions": []},
        content_type="application/json",
    )
    assert resp.status_code in (401, 403)


@override_settings(REQUIRE_AUTH=True)
def test_review_submit_allowed_for_authenticated(owner):
    r = _review(owner, visibility="link")
    client = Client()
    client.force_login(owner)
    resp = client.post(
        f"/api/reviews/{r.id}/submit/",
        data={"decisions": []},
        content_type="application/json",
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_visibility_reviews.py -v`
Expected: `test_public_review_read_anonymous` FAILS (read still needs token).

- [ ] **Step 3: Update the access checks**

In `apps/reviews/api.py`, replace `_can_read` and `_can_write`:

```python
def _can_read(request: HttpRequest, review: ReviewRequest) -> bool:
    """Authenticated users see all reviews; public (link) reviews are readable by anyone."""
    return (
        request.user.is_authenticated
        or review.visibility == ReviewRequest.VISIBILITY_LINK
    )


def _can_write(request: HttpRequest, review: ReviewRequest) -> bool:
    """Submitting a decision (approve/redraft) requires a Dimagi login —
    public-readable does NOT grant anonymous write."""
    return request.user.is_authenticated
```

If `_token_ok` is now unused anywhere in the module, delete its definition to keep the linter quiet. (Search: `grep -n "_token_ok" apps/reviews/api.py` — remove if no remaining references.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_visibility_reviews.py -v`
Expected: all four PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/reviews/api.py tests/test_visibility_reviews.py
git commit -m "feat(reviews): tokenless public read; authenticated-only submit"
```

---

## Task 5: Narrative visibility — cascade endpoint + aggregate field

**Files:**
- Modify: `apps/runs/aggregate.py` (`_blank_narrative`, `_aggregate` loops, `build_narrative`; add `set_narrative_visibility`)
- Modify: `apps/runs/schemas.py` (`NarrativeDetailOut.visibility`; add `NarrativeVisibilityIn` / `NarrativeVisibilityOut`)
- Modify: `apps/runs/api.py` (new PATCH route)
- Test: `tests/test_narrative_visibility.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_narrative_visibility.py`:

```python
"""Narrative-level visibility cascade + computed aggregate field."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from apps.reviews.models import ReviewRequest
from apps.runs import aggregate
from apps.walkthroughs.models import Walkthrough


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="owner@dimagi.com", email="owner@dimagi.com",
    )


def _wt(owner, **kw):
    defaults = dict(
        title="art", kind="video", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="video/mp4", size_bytes=1,
        run_id="demo-2026-06-09-001", narrative_slug="demo",
    )
    defaults.update(kw)
    return Walkthrough.objects.create(**defaults)


def _rev(owner, **kw):
    defaults = dict(
        run_id="demo-2026-06-09-001", narrative_slug="demo",
        gate="narrative-agreement", request_json={"narrative": "s"}, owner=owner,
    )
    defaults.update(kw)
    return ReviewRequest.objects.create(**defaults)


def test_set_narrative_visibility_cascades(db, owner):
    w1 = _wt(owner, drive_file_id="f1", visibility="private")
    w2 = _wt(owner, drive_file_id="f2", visibility="private", run_id="demo-2026-06-09-002")
    r1 = _rev(owner, visibility="private")
    wt_n, rev_n = aggregate.set_narrative_visibility("demo", "link")
    assert (wt_n, rev_n) == (2, 1)
    w1.refresh_from_db(); w2.refresh_from_db(); r1.refresh_from_db()
    assert w1.visibility == w2.visibility == "link"
    assert r1.visibility == "link"


def test_aggregate_visibility_public_private_mixed(db, owner):
    _wt(owner, drive_file_id="fa", visibility="link")
    _rev(owner, visibility="link")
    assert aggregate.build_narrative("demo")["visibility"] == "public"
    aggregate.set_narrative_visibility("demo", "private")
    assert aggregate.build_narrative("demo")["visibility"] == "private"
    # Make one row disagree → mixed.
    Walkthrough.objects.filter(narrative_slug="demo").update(visibility="link")
    assert aggregate.build_narrative("demo")["visibility"] == "mixed"


@override_settings(REQUIRE_AUTH=True)
def test_patch_endpoint_requires_auth(db, owner):
    _wt(owner)
    resp = Client().patch(
        "/api/ddd/narratives/demo/visibility/",
        data={"visibility": "link"}, content_type="application/json",
    )
    assert resp.status_code == 401


@override_settings(REQUIRE_AUTH=True)
def test_patch_endpoint_cascades(db, owner):
    _wt(owner, visibility="private")
    _rev(owner, visibility="private")
    client = Client(); client.force_login(owner)
    resp = client.patch(
        "/api/ddd/narratives/demo/visibility/",
        data={"visibility": "link"}, content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["visibility"] == "public"
    assert body["walkthroughs_updated"] == 1
    assert body["reviews_updated"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_narrative_visibility.py -v`
Expected: FAIL — `set_narrative_visibility` and the route don't exist; `build_narrative` has no `visibility` key.

- [ ] **Step 3a: Track visibility in the aggregate**

In `apps/runs/aggregate.py`, add to `_blank_narrative`'s returned dict (next to `"owner_ids": set(),`):

```python
        "visibilities": set(),
```

In `_aggregate`, inside the walkthrough loop (after `a["owner_ids"].add(w.owner_id)`):

```python
        a["visibilities"].add(w.visibility)
```

In `_aggregate`, inside the review loop (after `a["run_ids"].add(r.run_id)`):

```python
        a["visibilities"].add(r.visibility)
```

- [ ] **Step 3b: Expose computed visibility from `build_narrative`**

In `apps/runs/aggregate.py`, add this helper above `build_narrative`:

```python
def _agg_visibility(visibilities: set[str]) -> str:
    """Collapse a set of row visibilities into the narrative's status."""
    if visibilities == {Walkthrough.VISIBILITY_LINK}:
        return "public"
    if visibilities <= {Walkthrough.VISIBILITY_PRIVATE}:  # all private or empty
        return "private"
    return "mixed"
```

Then in `build_narrative`, add the `"visibility"` key to the final return dict literal (which currently ends `"current_version": current_payload, "versions": versions_payload,`):

```python
    return {
        "slug": slug,
        "title": a["title"],
        "story": a["story"],
        "phase": a["phase"],
        "project_slug": a["project_slug"],
        "visibility": _agg_visibility(a["visibilities"]),
        "current_version": current_payload,
        "versions": versions_payload,
    }
```

- [ ] **Step 3c: Add the cascade function**

In `apps/runs/aggregate.py`, add near the bottom:

```python
def set_narrative_visibility(slug: str, visibility: str) -> tuple[int, int]:
    """Set visibility on every walkthrough + review grouped under ``slug``.

    Matches the exact same rows the narrative aggregate displays (explicit
    narrative_slug wins; run_id-derived slug is the fallback). Returns
    (walkthroughs_updated, reviews_updated).
    """
    slug = (slug or "").strip()
    wts = list(
        Walkthrough.objects.exclude(run_id__isnull=True).exclude(run_id="")
    )
    feature_map = _narrative_slug_map(wts)
    wt_pks = [w.pk for w in wts if narrative_of_walkthrough(w) == slug]
    rev_pks = [
        r.pk
        for r in ReviewRequest.objects.all()
        if narrative_for_run_id(r.run_id, feature_map) == slug
    ]
    wt_n = Walkthrough.objects.filter(pk__in=wt_pks).update(visibility=visibility)
    rev_n = ReviewRequest.objects.filter(pk__in=rev_pks).update(visibility=visibility)
    return wt_n, rev_n
```

- [ ] **Step 3d: Add schemas**

In `apps/runs/schemas.py`, add `visibility` to `NarrativeDetailOut` (after `project_slug`):

```python
    visibility: str = "private"  # "public" | "private" | "mixed"
```

And add two new schemas (near the other narrative schemas):

```python
class NarrativeVisibilityIn(StrictModel):
    visibility: Literal["private", "link"]


class NarrativeVisibilityOut(StrictModel):
    slug: str
    visibility: str  # "public" | "private" | "mixed"
    walkthroughs_updated: int
    reviews_updated: int
```

If `Literal` isn't imported, add `from typing import Literal` at the top.

- [ ] **Step 3e: Add the route**

In `apps/runs/api.py`, import the new schemas and `aggregate` (already imported), then add:

```python
@router.patch(
    "/narratives/{slug}/visibility/",
    response=NarrativeVisibilityOut,
    summary="Set visibility for an entire narrative (cascades to all artifacts + reviews)",
)
def set_narrative_visibility(
    request: HttpRequest, slug: str, payload: NarrativeVisibilityIn
) -> NarrativeVisibilityOut:
    wt_n, rev_n = aggregate.set_narrative_visibility(slug, payload.visibility)
    detail = aggregate.build_narrative(slug)
    status = detail["visibility"] if detail else (
        "public" if payload.visibility == "link" else "private"
    )
    return NarrativeVisibilityOut(
        slug=slug,
        visibility=status,
        walkthroughs_updated=wt_n,
        reviews_updated=rev_n,
    )
```

Add `NarrativeVisibilityIn, NarrativeVisibilityOut` to the schema imports at the top of `apps/runs/api.py`. (The route is named `set_narrative_visibility` — distinct from the aggregate function of the same name, which is called as `aggregate.set_narrative_visibility`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_narrative_visibility.py -v`
Expected: all five PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/runs/aggregate.py apps/runs/schemas.py apps/runs/api.py tests/test_narrative_visibility.py
git commit -m "feat(ddd): narrative-level visibility cascade endpoint + aggregate status"
```

---

## Task 6: Remove dead token surfaces

**Files:**
- Modify: `apps/walkthroughs/api.py` (delete `rotate_token` route; stop minting in `patch_walkthrough` + upload)
- Modify: `apps/walkthroughs/schemas.py` (drop `share_token` from `WalkthroughDetailOut`; remove `WalkthroughRotateTokenOut`)
- Modify: `apps/walkthroughs/api.py` `_detail_payload` (drop `share_token` key)
- Modify: `apps/reviews/api.py` `_detail_payload` (drop `expose_token` param + `share_token` key) and its call sites
- Modify: `apps/reviews/schemas.py` (drop `share_token` from review out schemas)
- Test: existing suites must stay green.

- [ ] **Step 1: Delete the walkthrough rotate route**

In `apps/walkthroughs/api.py`, delete the entire `@router.post("/{wid}/rotate-token/", ...)` block and the `def rotate_token(...)` function. Remove `WalkthroughRotateTokenOut` from the schema imports.

- [ ] **Step 2: Stop minting walkthrough tokens**

In `apps/walkthroughs/api.py`, in `patch_walkthrough`, delete:

```python
    if w.visibility == Walkthrough.VISIBILITY_LINK and not w.share_token:
        w.ensure_share_token()
```

In the upload handler (`create` / `POST /`), find and delete the auto-mint on link visibility (the `ensure_share_token()` call near where visibility is set, ~lines 263–264).

- [ ] **Step 3: Drop `share_token` from the detail payload + schema**

In `apps/walkthroughs/api.py` `_detail_payload`, remove the `"share_token": ...` entry.
In `apps/walkthroughs/schemas.py`, remove the `share_token: str | None = None` line from `WalkthroughDetailOut` and delete the `WalkthroughRotateTokenOut` class.

- [ ] **Step 4: Drop `share_token` from reviews**

In `apps/reviews/api.py`, change `_detail_payload(review, *, is_owner, expose_token)` to `_detail_payload(review, *, is_owner)`, delete the `"share_token": ...` key, and update all call sites to drop the `expose_token=` argument.
In `apps/reviews/schemas.py`, remove the `share_token: str | None = None` lines from both review out classes (lines ~27 and ~49). Leave the `share_token: str` at line ~73 only if it belongs to a still-used schema; if it's a rotate-out schema with no remaining route, delete that class too. (Search `grep -rn "share_token" apps/reviews/` and remove every response-facing reference; the model field stays.)

- [ ] **Step 5: Run the full backend suite**

Run: `uv run pytest`
Expected: PASS. Fix any test that asserted on `share_token` in a response by removing that assertion (the field is intentionally gone). The model-level token tests in `tests/test_walkthroughs_models.py` stay — the column/methods are retained.

- [ ] **Step 6: Commit**

```bash
git add apps/walkthroughs/api.py apps/walkthroughs/schemas.py apps/reviews/api.py apps/reviews/schemas.py
git commit -m "refactor: drop share_token from API responses + remove rotate route"
```

---

## Task 7: Regenerate OpenAPI types

**Files:**
- Modify: `frontend/src/api/generated.ts` (generated)

- [ ] **Step 1: Regenerate**

Run (backend must be importable; this reads the schema):

```bash
cd frontend && npm run gen:api
```

- [ ] **Step 2: Verify the diff**

Run: `git diff --stat frontend/src/api/generated.ts`
Expected: `WalkthroughDetailOut` loses `share_token`; `ReviewRequestOut` loses `share_token`; `WalkthroughRotateTokenOut` and the rotate path removed; `NarrativeDetailOut` gains `visibility`; new `/api/ddd/narratives/{slug}/visibility/` PATCH appears.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/generated.ts
git commit -m "chore(api): regenerate OpenAPI types for tokenless visibility"
```

---

## Task 8: Frontend DDD client — visibility field + setter

**Files:**
- Modify: `frontend/src/api/ddd.ts`

- [ ] **Step 1: Add the `visibility` field to the detail type**

In `frontend/src/api/ddd.ts`, add to `interface DddNarrativeDetail` (after `project_slug`):

```typescript
  visibility: 'public' | 'private' | 'mixed'
```

- [ ] **Step 2: Add a `patch` helper next to `del`**

In `frontend/src/api/ddd.ts`, after the `del` function, add:

```typescript
async function patchJson<T>(url: string, body: unknown): Promise<T> {
  const csrf = csrfToken()
  const resp = await fetch(url, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRFToken': decodeURIComponent(csrf) } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    let detail = ''
    try {
      const b = await resp.json()
      detail = b?.detail ?? b?.title ?? ''
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Request failed (${resp.status})`)
  }
  return resp.json() as Promise<T>
}
```

- [ ] **Step 3: Add the setter + its result type**

In `frontend/src/api/ddd.ts`, add near the other narrative functions:

```typescript
export interface SetNarrativeVisibilityResult {
  slug: string
  visibility: 'public' | 'private' | 'mixed'
  walkthroughs_updated: number
  reviews_updated: number
}

/** Make an entire narrative public or private (cascades to all artifacts + reviews). */
export function setNarrativeVisibility(
  slug: string,
  makePublic: boolean,
): Promise<SetNarrativeVisibilityResult> {
  return patchJson(`/api/ddd/narratives/${encodeURIComponent(slug)}/visibility/`, {
    visibility: makePublic ? 'link' : 'private',
  })
}
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ddd.ts
git commit -m "feat(ddd-web): narrative visibility client (field + setter)"
```

---

## Task 9: Narrative page toggle

**Files:**
- Modify: `frontend/src/components/ddd/NarrativeLanding.tsx`

- [ ] **Step 1: Import the setter + add state**

In `frontend/src/components/ddd/NarrativeLanding.tsx`, add `setNarrativeVisibility` to the `@/api/ddd` import. Inside `function NarrativeLanding({ slug })`, add (near the existing `useState` calls):

```typescript
  const [vizBusy, setVizBusy] = useState(false)

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
```

- [ ] **Step 2: Render the toggle in the header**

In the `<header>` block (the right-hand side, near where the version count / delete-narrative control sits, ~line 261–289), add a toggle button. Place it before the existing controls:

```tsx
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
```

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ddd/NarrativeLanding.tsx
git commit -m "feat(ddd-web): one Public/Private toggle on the narrative page"
```

---

## Task 10: Walkthrough client cleanup

**Files:**
- Modify: `frontend/src/api/walkthroughs.ts`

- [ ] **Step 1: Remove the rotate function**

In `frontend/src/api/walkthroughs.ts`, delete the entire `export async function rotateWalkthroughToken(...) { ... }` block.

- [ ] **Step 2: Drop the token param from the content URL**

Replace `walkthroughContentUrl`:

```typescript
export function walkthroughContentUrl(id: string): string {
  return `/w/${id}/content`;
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npm run build`
Expected: build FAILS in `WalkthroughViewerPage.tsx` (still references `rotateWalkthroughToken` / passes a token arg). That's fixed in Task 11 — proceed.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/walkthroughs.ts
git commit -m "refactor(walkthroughs-web): drop rotate fn + token from content URL"
```

---

## Task 11: Walkthrough viewer — single toggle

**Files:**
- Modify: `frontend/src/pages/WalkthroughViewerPage.tsx`

- [ ] **Step 1: Remove the rotate + copy-link handlers and import**

In `frontend/src/pages/WalkthroughViewerPage.tsx`:
- Remove `rotateWalkthroughToken` from the `@/api/walkthroughs` (or relative) import.
- Delete the `copyShareLink` function (lines ~45–55) and the `rotate` function (lines ~57–68).

- [ ] **Step 2: Drop the viewer token + fix the iframe src**

Remove the `viewerToken` line (~93) and change `contentSrc`:

```typescript
  const contentSrc = withSceneHash(
    walkthroughContentUrl(w.id),
    window.location.hash,
  )
```

- [ ] **Step 3: Relabel the toggle + remove the two buttons**

In the owner controls block (~lines 134–158):
- Change the first button's label from `{w.visibility === 'link' ? 'Make private' : 'Enable link'}` to:

```tsx
            {w.visibility === 'link' ? 'Make private' : 'Make public'}
```

- Delete the "Copy share link" `<button>` block and the `{w.visibility === 'link' && (<button ...>Rotate token</button>)}` block entirely.

- [ ] **Step 4: Relabel the status badge**

In the badge (`~line 130`), change the text:

```tsx
          {w.visibility === 'link' ? 'Public' : 'Private (dimagi)'}
```

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds (no remaining references to the removed functions or the token arg).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/WalkthroughViewerPage.tsx
git commit -m "feat(walkthroughs-web): single Public/Private toggle, drop token UI"
```

---

## Task 12: Full verification

- [ ] **Step 1: Backend**

Run: `uv run pytest`
Expected: all PASS.

- [ ] **Step 2: Frontend**

Run: `cd frontend && npm run build`
Expected: type-check + build succeed.

- [ ] **Step 3: Manual smoke (optional but recommended)**

With the dev servers running:
1. Open a DDD narrative at `/ddd/<slug>`, click the toggle → "Public".
2. In a logged-out browser (or incognito), open `/w/<id>` for one of its artifacts and `/review/<id>` — both load; the video scrubs.
3. Toggle back to "Private" → both 404 / redirect to login when logged out.

- [ ] **Step 4: Final commit (if any stragglers)**

```bash
git status   # should be clean
```

---

## Notes for the implementer

- **No data migration.** Enum values are unchanged; existing `link` rows transparently become tokenless-public and existing tokens simply stop being read. The `share_token` column and the `ensure_share_token`/`rotate_share_token` model methods are intentionally **kept** (dormant) so this is reversible — do not delete them.
- **Why `build_narrative` for the response status:** after the bulk update, re-aggregating returns the authoritative `"public"`/`"private"`/`"mixed"` (it will be uniform right after a cascade, but re-reading avoids drift).
- **Review submit body:** `test_review_submit_allowed_for_authenticated` posts `{"decisions": []}`. If `ReviewSubmitIn` requires other fields, adjust the test body to the minimal valid payload (read `apps/reviews/schemas.py` `ReviewSubmitIn`).
```
