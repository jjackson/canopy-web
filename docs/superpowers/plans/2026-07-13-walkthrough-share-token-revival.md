# Walkthrough Share-Token Revival Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anonymous read of a public walkthrough requires `?t=<share_token>`; bare-UUID URLs 404 for anonymous visitors, owners get a copyable/rotatable tokened `share_url`.

**Architecture:** Revive the dormant `share_token` column on `Walkthrough` (spec: `docs/superpowers/specs/2026-07-13-walkthrough-share-token-revival-design.md`). Two anonymous-read surfaces gain a constant-time token check (`apps/walkthroughs/api.py::get_walkthrough`, `apps/walkthroughs/streaming.py::walkthrough_content`); tokens are minted on create/PATCH-to-public plus a backfill migration; a new owner-only rotate endpoint invalidates leaked links. The React viewer threads `?t=` through detail fetch + content src and gives owners Open/Copy/Rotate controls driven by a new owner-only `share_url` field.

**Tech Stack:** Django 5 + Django Ninja 1.x (Pydantic v2), pytest, React 19 + TypeScript + openapi-fetch.

## Global Constraints

- Reviews stay tokenless — do NOT touch `apps/reviews/`.
- Anonymous failures are always `404 "walkthrough not found"` (never 403) so private/existing rows don't leak.
- Token comparison uses `secrets.compare_digest`; empty/absent stored token never matches.
- The raw token is never a standalone response field and never appears in list responses; only `share_url` (owner + `visibility=link` only).
- Session-authenticated users keep full read access regardless of visibility (unchanged).
- Frontend: semantic design tokens only (`bg-card`, `border-border`, `text-muted-foreground`, …) — no raw Tailwind palette literals.
- Backend tests: `uv run pytest`; frontend check: `cd frontend && npm run build`.

---

### Task 1: Model — `token_matches()`

**Files:**
- Modify: `apps/walkthroughs/models.py` (after `rotate_share_token`, ~line 118)
- Test: `tests/test_walkthroughs_models.py`

**Interfaces:**
- Consumes: existing `Walkthrough.share_token`, `VISIBILITY_LINK`, `secrets` (already imported in models.py).
- Produces: `Walkthrough.token_matches(token: str | None) -> bool` — used by Task 3.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_walkthroughs_models.py`, reusing that file's existing fixtures/factory conventions — check its top for the `Walkthrough.objects.create` pattern and mirror it):

```python
class TestTokenMatches:
    def _make(self, db, **kw):
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user(
            username="tok-owner@dimagi.com", email="tok-owner@dimagi.com",
        )
        defaults = dict(
            title="Demo", kind="video", owner=owner,
            drive_file_id="f", drive_folder_id="d",
            content_type="video/mp4", size_bytes=1,
        )
        defaults.update(kw)
        return Walkthrough.objects.create(**defaults)

    def test_matches_on_public_with_correct_token(self, db):
        w = self._make(db, visibility="link")
        token = w.ensure_share_token()
        assert w.token_matches(token) is True

    def test_rejects_wrong_token(self, db):
        w = self._make(db, visibility="link")
        w.ensure_share_token()
        assert w.token_matches("wrong") is False

    def test_rejects_empty_and_none_token(self, db):
        w = self._make(db, visibility="link")
        w.ensure_share_token()
        assert w.token_matches("") is False
        assert w.token_matches(None) is False

    def test_rejects_when_no_token_minted(self, db):
        # Empty stored token must never match, even an empty presented token.
        w = self._make(db, visibility="link")
        assert w.share_token is None
        assert w.token_matches("") is False

    def test_rejects_on_private_even_with_correct_token(self, db):
        w = self._make(db, visibility="private")
        token = w.ensure_share_token()
        assert w.token_matches(token) is False
```

(`Walkthrough` is already imported at the top of that test file.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_walkthroughs_models.py -k TestTokenMatches -v`
Expected: FAIL — `AttributeError: 'Walkthrough' object has no attribute 'token_matches'`

- [ ] **Step 3: Implement** — add to `apps/walkthroughs/models.py` directly below `rotate_share_token`:

```python
    def token_matches(self, token: str | None) -> bool:
        """Constant-time check that ``token`` grants anonymous public access.

        True only when the walkthrough is public (visibility=link), a token
        has been minted, and the presented token matches. Empty/absent on
        either side never matches.
        """
        return bool(
            self.visibility == self.VISIBILITY_LINK
            and self.share_token
            and token
            and secrets.compare_digest(self.share_token, token)
        )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_walkthroughs_models.py -k TestTokenMatches -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/models.py tests/test_walkthroughs_models.py
git commit -m "feat(walkthroughs): add Walkthrough.token_matches constant-time check"
```

---

### Task 2: Backfill migration — mint tokens for existing public rows

**Files:**
- Create: `apps/walkthroughs/migrations/0008_mint_share_tokens.py`
- Test: `tests/test_walkthroughs_models.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: every `visibility=link` row has a non-empty `share_token` after migrate. Tasks 3+ can assume public rows created before this feature still work once re-shared with their minted token.

- [ ] **Step 1: Write the migration**

```python
"""Mint share tokens for pre-existing public walkthroughs.

The share-token revival (spec 2026-07-13) makes anonymous read require
?t=<share_token>. Rows that were already visibility=link need a token so
their owners can re-share without re-toggling visibility.
"""
import secrets

from django.db import migrations
from django.db.models import Q


def mint_tokens(apps, schema_editor):
    Walkthrough = apps.get_model("walkthroughs", "Walkthrough")
    qs = Walkthrough.objects.filter(visibility="link").filter(
        Q(share_token__isnull=True) | Q(share_token="")
    )
    for w in qs:
        w.share_token = secrets.token_urlsafe(24)
        w.save(update_fields=["share_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("walkthroughs", "0007_backfill_default_workspace"),
    ]

    operations = [
        migrations.RunPython(mint_tokens, migrations.RunPython.noop),
    ]
```

- [ ] **Step 2: Write the test** (append to `tests/test_walkthroughs_models.py`; loads the migration module by path since its name starts with a digit):

```python
def test_backfill_migration_mints_tokens_for_public_rows(db):
    import importlib.util
    from pathlib import Path

    from django.apps import apps as django_apps
    from django.contrib.auth import get_user_model

    owner = get_user_model().objects.create_user(
        username="mig-owner@dimagi.com", email="mig-owner@dimagi.com",
    )
    common = dict(
        title="Demo", kind="video", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="video/mp4", size_bytes=1,
    )
    public = Walkthrough.objects.create(visibility="link", **common)
    private = Walkthrough.objects.create(visibility="private", **common)
    assert public.share_token is None

    spec = importlib.util.spec_from_file_location(
        "mint_share_tokens",
        Path("apps/walkthroughs/migrations/0008_mint_share_tokens.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.mint_tokens(django_apps, None)

    public.refresh_from_db()
    private.refresh_from_db()
    assert public.share_token
    assert private.share_token is None
```

- [ ] **Step 3: Run test + migration checks**

Run: `uv run pytest tests/test_walkthroughs_models.py::test_backfill_migration_mints_tokens_for_public_rows -v`
Expected: PASS

Run: `uv run python manage.py makemigrations --check --dry-run`
Expected: `No changes detected` (proves no schema migration is missing — this is data-only).

- [ ] **Step 4: Commit**

```bash
git add apps/walkthroughs/migrations/0008_mint_share_tokens.py tests/test_walkthroughs_models.py
git commit -m "feat(walkthroughs): backfill share tokens for existing public walkthroughs"
```

---

### Task 3: Enforce the token gate on both anonymous-read surfaces

**Files:**
- Modify: `apps/walkthroughs/streaming.py:67-73` (the tokenless gate in `walkthrough_content`)
- Modify: `apps/walkthroughs/api.py:354-369` (`get_walkthrough` — add `t` query param + gate)
- Test: `tests/test_visibility_walkthroughs.py`

**Interfaces:**
- Consumes: `Walkthrough.token_matches(token)` from Task 1.
- Produces: `GET /api/walkthroughs/{wid}/?t=<token>` and `GET /walkthrough/<uuid>/content?t=<token>` are the anonymous read contract. The `t` param is declared in the Ninja signature so it lands in the OpenAPI schema (Task 6 depends on that).

- [ ] **Step 1: Update the now-wrong test and add the new matrix** in `tests/test_visibility_walkthroughs.py`. Replace `test_public_content_served_to_anonymous_without_token` (which asserted 200 for tokenless anonymous) with:

```python
@override_settings(REQUIRE_AUTH=True)
def test_public_content_404s_anonymous_without_token(owner):
    w = _make(owner, visibility="link")
    w.ensure_share_token()
    resp = Client().get(f"/walkthrough/{w.id}/content")
    assert resp.status_code == 404


@override_settings(REQUIRE_AUTH=True)
def test_public_content_served_to_anonymous_with_token(owner):
    w = _make(owner, visibility="link")
    token = w.ensure_share_token()
    with _stub_download():
        resp = Client().get(f"/walkthrough/{w.id}/content?t={token}")
    assert resp.status_code == 200


@override_settings(REQUIRE_AUTH=True)
def test_public_content_404s_anonymous_with_wrong_token(owner):
    w = _make(owner, visibility="link")
    w.ensure_share_token()
    resp = Client().get(f"/walkthrough/{w.id}/content?t=nope")
    assert resp.status_code == 404


@override_settings(REQUIRE_AUTH=True)
def test_private_content_404s_anonymous_even_with_token(owner):
    w = _make(owner, visibility="private")
    token = w.ensure_share_token()
    resp = Client().get(f"/walkthrough/{w.id}/content?t={token}")
    assert resp.status_code == 404
```

And the API-detail equivalents (session `Client` through the full middleware stack, same style):

```python
@override_settings(REQUIRE_AUTH=True)
def test_detail_api_404s_anonymous_without_token(owner):
    w = _make(owner, visibility="link")
    w.ensure_share_token()
    resp = Client().get(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 404


@override_settings(REQUIRE_AUTH=True)
def test_detail_api_serves_anonymous_with_token(owner):
    w = _make(owner, visibility="link")
    token = w.ensure_share_token()
    resp = Client().get(f"/api/walkthroughs/{w.id}/?t={token}")
    assert resp.status_code == 200
    assert resp.json()["is_owner"] is False


@override_settings(REQUIRE_AUTH=True)
def test_detail_api_404s_anonymous_with_wrong_token(owner):
    w = _make(owner, visibility="link")
    w.ensure_share_token()
    resp = Client().get(f"/api/walkthroughs/{w.id}/?t=nope")
    assert resp.status_code == 404
```

If the anonymous `Client()` hits a login redirect (302) instead of reaching the handler in the test environment, mirror however the existing `test_detail_handler_404s_private_for_anonymous` test at the bottom of this file invokes the handler (RequestFactory directly) for the detail-API cases — keep the streaming cases on `Client()` as above.

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/test_visibility_walkthroughs.py -v`
Expected: the new `*_with_token` tests FAIL (token currently ignored → tokenless tests pass where they should now 404).

- [ ] **Step 3: Implement.** In `apps/walkthroughs/streaming.py`, replace the gate (lines 67–73) and update the docstring's "Auth (tokenless)" paragraph:

```python
    # Token-gated public access (spec 2026-07-13): anonymous read requires
    # visibility=link AND a matching ?t=<share_token>. Bare-UUID anonymous
    # access 404s exactly like private, so existence never leaks.
    if not (
        request.user.is_authenticated
        or w.token_matches(request.GET.get("t"))
    ):
        raise Http404("walkthrough not found")
```

Docstring replacement for the "Auth (tokenless)" paragraph:

```python
    Auth: any authenticated session user OR a public (visibility=link)
    walkthrough presented with its ?t=<share_token>. Anything else 404s
    so existence isn't leaked.
```

In `apps/walkthroughs/api.py`, change `get_walkthrough` to declare the query param and use the same gate:

```python
def get_walkthrough(request: HttpRequest, wid: UUID, t: str = "") -> WalkthroughDetailOut:
    _require_enabled()
    w = _get_or_404(wid)
    if not (request.user.is_authenticated or w.token_matches(t)):
        raise Http404("walkthrough not found")  # don't leak private existence
    is_owner = request.user.is_authenticated and w.owner_id == request.user.id
    return WalkthroughDetailOut.model_validate(_detail_payload(w, is_owner=is_owner))
```

Also update the route's `auth=None` comment: `# Public walkthroughs load with ?t=<share_token>, no session.`

- [ ] **Step 4: Run the whole file**

Run: `uv run pytest tests/test_visibility_walkthroughs.py -v`
Expected: ALL PASS (including untouched owner/authed tests).

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/streaming.py apps/walkthroughs/api.py tests/test_visibility_walkthroughs.py
git commit -m "feat(walkthroughs): require share token for anonymous public read"
```

---

### Task 4: Minting on create/PATCH + owner-only `share_url`

**Files:**
- Modify: `apps/walkthroughs/schemas.py` (`WalkthroughDetailOut`)
- Modify: `apps/walkthroughs/api.py` (`_detail_payload` ~line 85, `upload_walkthrough` create block ~line 234, `patch_walkthrough` ~line 390, and every `_detail_payload` call site)
- Test: `tests/test_visibility_walkthroughs.py` (append)

**Interfaces:**
- Consumes: `ensure_share_token()` (existing model method), Task 3's gate.
- Produces: `WalkthroughDetailOut.share_url: str | None` — absolute tokened URL, present only when `is_owner and visibility == "link"`. `_detail_payload(w, *, is_owner, request)` (new required `request` kwarg). Tasks 5–7 rely on both.

- [ ] **Step 1: Write failing tests** (append to `tests/test_visibility_walkthroughs.py`):

```python
@override_settings(REQUIRE_AUTH=True)
def test_patch_to_public_mints_token_and_returns_share_url(owner):
    w = _make(owner, visibility="private")
    assert w.share_token is None
    client = Client()
    client.force_login(owner)
    resp = client.patch(
        f"/api/walkthroughs/{w.id}/",
        data={"visibility": "link"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    w.refresh_from_db()
    assert w.share_token
    assert body["share_url"] is not None
    assert f"/walkthrough/{w.id}?t={w.share_token}" in body["share_url"]


@override_settings(REQUIRE_AUTH=True)
def test_patch_to_private_keeps_token_and_hides_share_url(owner):
    w = _make(owner, visibility="link")
    token = w.ensure_share_token()
    client = Client()
    client.force_login(owner)
    resp = client.patch(
        f"/api/walkthroughs/{w.id}/",
        data={"visibility": "private"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    w.refresh_from_db()
    assert w.share_token == token  # kept — rotation is explicit
    assert resp.json()["share_url"] is None


@override_settings(REQUIRE_AUTH=True)
def test_share_url_hidden_from_non_owner_and_anonymous(owner):
    w = _make(owner, visibility="link")
    token = w.ensure_share_token()

    # Anonymous with a valid token: readable, but share_url is None and the
    # raw token is not a response field.
    resp = Client().get(f"/api/walkthroughs/{w.id}/?t={token}")
    assert resp.status_code == 200
    assert resp.json()["share_url"] is None
    assert "share_token" not in resp.json()

    # Authed non-owner: same.
    other = get_user_model().objects.create_user(
        username="other2@dimagi.com", email="other2@dimagi.com",
    )
    client = Client()
    client.force_login(other)
    resp = client.get(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 200
    assert resp.json()["share_url"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_visibility_walkthroughs.py -k "share_url or mints or keeps_token" -v`
Expected: FAIL (`share_url` KeyError / token not minted).

- [ ] **Step 3: Implement.**

`apps/walkthroughs/schemas.py` — add to `WalkthroughDetailOut`:

```python
class WalkthroughDetailOut(WalkthroughListItemOut):
    """Detail view adds content_type, is_owner, and the owner-only share_url."""

    content_type: str
    is_owner: bool
    links: list[WalkthroughLink] = []
    # Absolute tokened public URL (…/walkthrough/<id>?t=<token>). Present only
    # for the owner of a public (visibility=link) walkthrough; never expose the
    # raw token as its own field.
    share_url: str | None = None
```

`apps/walkthroughs/api.py` — add a helper above `_detail_payload` (import `get_script_prefix` from `django.urls` at the top of the file):

```python
def _share_url(request: HttpRequest, w: Walkthrough) -> str | None:
    """Absolute tokened public URL; None unless public + minted."""
    if w.visibility != Walkthrough.VISIBILITY_LINK or not w.share_token:
        return None
    prefix = get_script_prefix().rstrip("/")  # "" locally, "/canopy" on labs
    return request.build_absolute_uri(
        f"{prefix}/walkthrough/{w.id}?t={w.share_token}"
    )
```

Change `_detail_payload` to take the request and emit the field:

```python
def _detail_payload(w: Walkthrough, *, is_owner: bool, request: HttpRequest) -> dict:
```

…and inside the returned dict add:

```python
        "share_url": _share_url(request, w) if is_owner else None,
```

Update **every** `_detail_payload(...)` call site in `apps/walkthroughs/api.py` to pass `request=request` (grep for `_detail_payload(` — upload's 201 return, `get_walkthrough`, `patch_walkthrough`, and any others).

Minting — in `upload_walkthrough`, immediately after the `Walkthrough.objects.create(...)` block:

```python
    if w.visibility == Walkthrough.VISIBILITY_LINK:
        w.ensure_share_token()
```

…and in `patch_walkthrough`, after `w.save()` / before `w.refresh_from_db()`:

```python
    if w.visibility == Walkthrough.VISIBILITY_LINK:
        w.ensure_share_token()  # mint on flip-to-public; keep token on flip-to-private
```

- [ ] **Step 4: Run the file**

Run: `uv run pytest tests/test_visibility_walkthroughs.py tests/test_walkthroughs_drive.py -v`
Expected: ALL PASS (drive tests exercise the upload path — they catch a missed `request=` kwarg).

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/schemas.py apps/walkthroughs/api.py tests/test_visibility_walkthroughs.py
git commit -m "feat(walkthroughs): mint tokens on publish, expose owner-only share_url"
```

---

### Task 5: Rotate endpoint

**Files:**
- Modify: `apps/walkthroughs/api.py` (new route after `patch_walkthrough`)
- Test: `tests/test_visibility_walkthroughs.py` (append)

**Interfaces:**
- Consumes: `rotate_share_token()` (existing model method), `_detail_payload(w, is_owner=..., request=...)` from Task 4.
- Produces: `POST /api/walkthroughs/{wid}/rotate-token` → `WalkthroughDetailOut` with the fresh `share_url`. Task 6's `rotateWalkthroughToken()` calls it.

- [ ] **Step 1: Write failing tests:**

```python
@override_settings(REQUIRE_AUTH=True)
def test_rotate_invalidates_old_token_and_returns_new_share_url(owner):
    w = _make(owner, visibility="link")
    old = w.ensure_share_token()
    client = Client()
    client.force_login(owner)
    resp = client.post(f"/api/walkthroughs/{w.id}/rotate-token")
    assert resp.status_code == 200
    w.refresh_from_db()
    assert w.share_token != old
    assert f"?t={w.share_token}" in resp.json()["share_url"]
    # Old token is dead on both surfaces.
    assert Client().get(f"/api/walkthroughs/{w.id}/?t={old}").status_code == 404
    assert Client().get(f"/walkthrough/{w.id}/content?t={old}").status_code == 404
    # New token works.
    assert Client().get(f"/api/walkthroughs/{w.id}/?t={w.share_token}").status_code == 200


@override_settings(REQUIRE_AUTH=True)
def test_rotate_is_owner_only(owner):
    w = _make(owner, visibility="link")
    w.ensure_share_token()
    # Anonymous → 404.
    assert Client().post(f"/api/walkthroughs/{w.id}/rotate-token").status_code == 404
    # Authed non-owner → 404 (hidden, matching the tokens-app pattern).
    other = get_user_model().objects.create_user(
        username="other3@dimagi.com", email="other3@dimagi.com",
    )
    client = Client()
    client.force_login(other)
    assert client.post(f"/api/walkthroughs/{w.id}/rotate-token").status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_visibility_walkthroughs.py -k rotate -v`
Expected: FAIL with 404s where 200 expected (route doesn't exist).

- [ ] **Step 3: Implement** — add after `patch_walkthrough` in `apps/walkthroughs/api.py`:

```python
@router.post(
    "/{wid}/rotate-token",
    response=WalkthroughDetailOut,
    summary="Rotate the share token (owner only)",
)
def rotate_walkthrough_token(request: HttpRequest, wid: UUID) -> WalkthroughDetailOut:
    """Mint a fresh share token, killing every previously shared public link."""
    _require_enabled()
    w = _get_or_404(wid)
    if not (request.user.is_authenticated and w.owner_id == request.user.id):
        raise Http404("walkthrough not found")  # hide existence from non-owners
    w.rotate_share_token()
    return WalkthroughDetailOut.model_validate(
        _detail_payload(w, is_owner=True, request=request)
    )
```

- [ ] **Step 4: Run backend suite**

Run: `uv run pytest`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/api.py tests/test_visibility_walkthroughs.py
git commit -m "feat(walkthroughs): owner-only rotate-token endpoint"
```

---

### Task 6: Frontend API client + regenerated types

**Files:**
- Modify: `frontend/src/api/walkthroughs.ts`
- Modify (generated): `frontend/src/api/generated.ts`

**Interfaces:**
- Consumes: the Task 3–5 API surface (`t` query param, `share_url`, rotate route).
- Produces: `getWalkthrough(id: string, token?: string | null)`, `walkthroughContentUrl(id: string, token?: string | null)`, `rotateWalkthroughToken(id: string): Promise<WalkthroughDetail>`. `WalkthroughDetail` gains `share_url`. Task 7 consumes all three.

- [ ] **Step 1: Regenerate types.** Export the schema statically (no server needed), then generate:

```bash
cd /path/to/repo  # repo root
uv run python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()
from apps.api.api import api
import json
print(json.dumps(api.get_openapi_schema()))
" > frontend/openapi.json
cd frontend && npm run gen:api:local && rm ../frontend/openapi.json 2>/dev/null; rm -f openapi.json
```

(If the settings module path differs, check `manage.py` for the default `DJANGO_SETTINGS_MODULE`. The `regen-openapi.yml` workflow re-generates and auto-commits on the PR as a backstop, so a locally imperfect regen is not fatal.)

Verify: `grep -n "share_url\|rotate-token" frontend/src/api/generated.ts` shows both.

- [ ] **Step 2: Update the client** in `frontend/src/api/walkthroughs.ts`:

Replace `getWalkthrough`:

```typescript
export async function getWalkthrough(
  id: string,
  token?: string | null,
): Promise<WalkthroughDetail> {
  const { data, error } = await apiV2.GET("/api/walkthroughs/{wid}/", {
    params: {
      path: { wid: id },
      ...(token ? { query: { t: token } } : {}),
    },
  });
  if (error) throw new Error("Failed to load walkthrough");
  // openapi-fetch's immutable response type deep-freezes the `links` array
  // (method signatures become `{}`), which no longer structurally matches the
  // plain schema alias. Same cast `listWalkthroughs` uses for its array body.
  return data as unknown as WalkthroughDetail;
}
```

Replace `walkthroughContentUrl`:

```typescript
export function walkthroughContentUrl(id: string, token?: string | null): string {
  // Base-aware so the `<video>`/`<iframe>` src resolves under the deployed
  // sub-path (e.g. `/canopy/walkthrough/<id>/content`), not the origin root.
  // Anonymous public access carries the share token as ?t=.
  const suffix = token ? `?t=${encodeURIComponent(token)}` : "";
  return withBase(`/walkthrough/${id}/content${suffix}`);
}
```

Add:

```typescript
export async function rotateWalkthroughToken(
  id: string,
): Promise<WalkthroughDetail> {
  const { data, error } = await apiV2.POST("/api/walkthroughs/{wid}/rotate-token", {
    params: { path: { wid: id } },
  });
  if (error) throw new Error("Failed to rotate share link");
  return data as unknown as WalkthroughDetail;
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npm run build`
Expected: PASS (viewer page still compiles — it passes fewer args than the new optional params accept).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/walkthroughs.ts frontend/src/api/generated.ts
git commit -m "feat(frontend): walkthrough client threads share token; rotate endpoint"
```

---

### Task 7: Viewer page + legacy-redirect query preservation

**Files:**
- Modify: `frontend/src/pages/WalkthroughViewerPage.tsx`
- Modify: `frontend/src/router.tsx` (`WorkspaceIndex`, ~line 81)

**Interfaces:**
- Consumes: Task 6's client functions and `WalkthroughDetail.share_url`.
- Produces: user-facing behavior only.

- [ ] **Step 1: Thread the token + switch controls to `share_url`** in `WalkthroughViewerPage.tsx`.

At the top of the component, read the token once:

```tsx
  const shareToken = new URLSearchParams(window.location.search).get('t')
```

Update the detail fetch effect:

```tsx
    getWalkthrough(id, shareToken)
      .then((d) => !cancelled && setW(d))
      .catch((e) => !cancelled && setError(String(e.message || e)))
```

(add `shareToken` to the effect's dependency array alongside `id`).

Replace the `publicUrl` derivation + `copyPublicUrl` with `share_url`-driven versions:

```tsx
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
```

Import `rotateWalkthroughToken` from `../api/walkthroughs`.

In the header, gate the Open/Copy controls on `shareUrl` (they were `w.visibility === 'link'`) and point them at it:

```tsx
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
```

In the owner toolbar (the `w.is_owner && (...)` block), add a Rotate button between the visibility toggle and Delete, shown only when public:

```tsx
          {w.visibility === 'link' && (
            <button
              className="px-3 py-1 rounded-lg border border-border bg-card text-foreground-secondary hover:bg-muted hover:border-input transition-colors disabled:opacity-50"
              onClick={rotateLink}
              disabled={busy}
            >
              Rotate link
            </button>
          )}
```

Thread the token into the content src (the `contentSrc` derivation):

```tsx
  const contentSrc = withSceneHash(
    walkthroughContentUrl(w.id, shareToken),
    window.location.hash,
  )
```

- [ ] **Step 2: Preserve query + hash on the legacy redirect** in `frontend/src/router.tsx`. `WorkspaceIndex` currently drops them:

```tsx
// /w/:workspace index. Disambiguates a legacy /w/<uuid> walkthrough link
// (redirect to the new viewer) from a real workspace slug (render the workbench).
function WorkspaceIndex() {
  const { workspace } = useParams()
  const { search, hash } = useLocation()
  if (workspace && UUID_RE.test(workspace)) {
    // Preserve ?t=<share_token> and #t=<seconds> across the redirect.
    return <Navigate to={`/walkthrough/${workspace}${search}${hash}`} replace />
  }
  return <ProjectsPage />
}
```

Add `useLocation` to the existing `react-router-dom` import in `router.tsx` if not already imported.

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/WalkthroughViewerPage.tsx frontend/src/router.tsx
git commit -m "feat(frontend): tokened share links on the walkthrough viewer + rotate"
```

---

### Task 8: Docs, full suite, PR

**Files:**
- Modify: `CLAUDE.md` (Walkthroughs API section + the "Visibility is tokenless Public/Private" design decision)

**Interfaces:** none — closeout.

- [ ] **Step 1: Update `CLAUDE.md`.** In the **Walkthroughs** API section: change the detail-GET line to say anonymous read requires `?t=<share_token>`; change the content-stream line the same way; add the rotate endpoint line (`POST /api/walkthroughs/<uuid>/rotate-token — owner-only; re-mints the token, killing shared links`); replace the "Visibility is **tokenless**" paragraph under the section and in **Design Decisions** to say: walkthroughs are token-gated (`visibility=link` + `?t=<share_token>`; `share_url` returned to owners; rotate endpoint) while **reviews remain tokenless** — cite `docs/superpowers/specs/2026-07-13-walkthrough-share-token-revival-design.md`.

- [ ] **Step 2: Full verification**

Run: `uv run pytest`
Expected: ALL PASS.
Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 3: Commit + PR**

```bash
git add CLAUDE.md
git commit -m "docs: walkthrough visibility is token-gated (reviews stay tokenless)"
git push
gh pr create --title "feat(walkthroughs): revive share tokens — anonymous read requires ?t=<token>" --body "Implements docs/superpowers/specs/2026-07-13-walkthrough-share-token-revival-design.md. Breaking for tokenless public links already in the wild (accepted in spec). Deploy with run_migrations=true."
```

**Post-merge deploy (has a migration):**

```bash
gh workflow run "Deploy to Labs (AWS)" --ref main -f run_migrations=true
```

**Post-deploy verification (manual):**
1. Open a public walkthrough while logged in → header shows Open/Copy/Rotate; copy the link.
2. Open the copied `?t=` link in incognito → video plays.
3. Strip `?t=` in incognito → "not found" error state.
4. Rotate → old copied link dies in incognito, new one works.

**Follow-ups (out of scope, canopy plugin repo):** `canopy:walkthrough-share` + `canopy:ddd-upload` must consume `share_url` from the upload/detail response; DDD `links[]` sibling links need tokened URLs for anonymous cross-navigation.
