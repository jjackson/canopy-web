# Walkthrough Sharing Implementation Plan

> **⚠️ Shipped, but auth + transport superseded — annotated 2026-06-07.** The walkthrough feature shipped, but two mechanisms in this plan are RETIRED: the DRF serializers/views (migrated to Django Ninja, PR #42) and the `/api/auth/e2e-login/` + `CANOPY_E2E_AUTH_TOKEN` auth flow (replaced by Personal Access Tokens, PR #45). **Do not follow this plan's auth instructions** — they point at a dead endpoint. Current API + auth are in `/CLAUDE.md`; the still-accurate design intent is in `docs/superpowers/specs/2026-05-26-walkthrough-sharing-design.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let canopy-web host HTML slideshows + MP4 videos produced by `/canopy:walkthrough`, with per-walkthrough visibility (private/dimagi-OAuth vs link-token) and Drive-backed storage.

**Architecture:** Drive holds the bytes (canopy SA in a shared drive folder); Postgres holds metadata + share tokens; Django proxies every view byte through `StreamingHttpResponse` so auth stays in the app, not in Drive. Frontend adds a `/walkthroughs` table, an `/w/<id>` viewer page, and a count link on each project tile.

**Tech Stack:** Django 5 + DRF, Postgres, googleapiclient (Drive v3), React 19 + Vite + Tailwind 4, pytest-django.

**Plan note (auth) — refinement from the spec:** Instead of inventing a new `CANOPY_WALKTHROUGH_UPLOAD_TOKEN`, the CLI skill calls the existing `/api/auth/e2e-login/` first (already token-gated by `CANOPY_E2E_AUTH_TOKEN`) and uses the resulting session cookie to POST `/api/walkthroughs/`. This is what the spec called "reuse the existing /api/auth/e2e-login/ token pattern" and avoids a second secret. The spec section §API ("Upload auth") and §7 ("Scope") are unchanged in intent.

**Out of scope (separate work, tracked at end):** the canopy plugin CLI skill (`canopy:walkthrough-share`) lives in a different repo. Drive folder + SA grant + Cloud Run env are deployment prereqs.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `apps/walkthroughs/__init__.py` | App package marker (empty) |
| `apps/walkthroughs/apps.py` | Django AppConfig |
| `apps/walkthroughs/models.py` | `Walkthrough` model |
| `apps/walkthroughs/drive_client.py` | Thin Drive v3 wrapper: upload, download (range-aware), delete, find-or-create-folder |
| `apps/walkthroughs/storage.py` | `store_upload()` / `delete_stored()` — wraps drive_client with per-walkthrough folder layout |
| `apps/walkthroughs/serializers.py` | DRF serializers (list, detail, create, update) |
| `apps/walkthroughs/views.py` | REST endpoints (list/create, detail/patch/delete, rotate-token, content stream) |
| `apps/walkthroughs/urls.py` | URL routing |
| `apps/walkthroughs/migrations/0001_initial.py` | Generated |
| `tests/test_walkthroughs_models.py` | Model behavior (token gen, defaults) |
| `tests/test_walkthroughs_drive.py` | Drive client + storage layer |
| `tests/test_walkthroughs_views.py` | All REST endpoints |
| `tests/fixtures/__init__.py` | Make `tests/fixtures` a package |
| `tests/fixtures/fake_drive.py` | In-memory drop-in for `DriveClient` (testing) |
| `config/settings/base.py` | Add `apps.walkthroughs` + new settings + middleware allowlist |
| `config/urls.py` | Wire `/api/walkthroughs/` + `/w/<id>/content` |
| `apps/common/middleware.py` | Add `/w/<id>/content` to public-with-token allowlist |
| `apps/projects/views.py` | Add `walkthrough_count` to project detail response |
| `pyproject.toml` | Add `google-api-python-client`, `google-auth` |
| `frontend/src/api/walkthroughs.ts` | API client + TS types |
| `frontend/src/pages/WalkthroughsPage.tsx` | `/walkthroughs` list |
| `frontend/src/pages/WalkthroughViewerPage.tsx` | `/w/:id` viewer with owner toolbar |
| `frontend/src/router.tsx` | Register routes |
| `frontend/src/components/AppLayout/AppLayout.tsx` | Add nav link |
| `frontend/src/pages/ProjectsPage.tsx` | Add walkthroughs count link in expanded tile |
| `docs/deploy.md` (or new section) | Deployment prereqs |
| `CLAUDE.md` | Document new endpoints + URLs |
| `TODOS.md` | Log deferred items |

---

## Task 1: Add Python deps and scaffold the app

**Files:**
- Modify: `pyproject.toml`
- Create: `apps/walkthroughs/__init__.py`
- Create: `apps/walkthroughs/apps.py`
- Modify: `config/settings/base.py` (INSTALLED_APPS only — settings additions land in Task 9)

- [ ] **Step 1: Add Drive client deps to pyproject.toml**

Edit `pyproject.toml`, append to `dependencies`:

```toml
    "google-api-python-client>=2.120,<3.0",
    "google-auth>=2.29,<3.0",
```

- [ ] **Step 2: Install deps**

Run: `uv sync --extra dev`
Expected: `google-api-python-client` and `google-auth` resolve and install.

- [ ] **Step 3: Create app package**

Create `apps/walkthroughs/__init__.py` (empty file).

Create `apps/walkthroughs/apps.py`:

```python
from django.apps import AppConfig


class WalkthroughsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.walkthroughs"
```

- [ ] **Step 4: Register the app**

In `config/settings/base.py`, find the `INSTALLED_APPS` list (line ~40) and add a new line after `"apps.projects",`:

```python
    "apps.walkthroughs",
```

- [ ] **Step 5: Verify Django sees the app**

Run: `uv run python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock apps/walkthroughs/ config/settings/base.py
git commit -m "feat(walkthroughs): scaffold app and add Google Drive client deps"
```

---

## Task 2: Walkthrough model + migration

**Files:**
- Create: `apps/walkthroughs/models.py`
- Create: `tests/test_walkthroughs_models.py`
- Generate: `apps/walkthroughs/migrations/0001_initial.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_walkthroughs_models.py`:

```python
"""Tests for the Walkthrough model."""
import pytest
from django.contrib.auth import get_user_model

from apps.walkthroughs.models import Walkthrough


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="ace@dimagi.com",
        email="ace@dimagi.com",
    )


def test_create_minimal_html_walkthrough(db, owner):
    w = Walkthrough.objects.create(
        title="Skill Builder Demo",
        kind="html",
        owner=owner,
        drive_file_id="drive-file-1",
        drive_folder_id="drive-folder-1",
        content_type="text/html",
        size_bytes=1024,
    )
    assert w.id is not None
    assert w.visibility == "private"
    assert w.share_token is None
    assert w.project_slug is None
    assert w.description == ""
    assert w.created_at is not None


def test_uuid_primary_key(db, owner):
    w = Walkthrough.objects.create(
        title="t",
        kind="html",
        owner=owner,
        drive_file_id="x",
        drive_folder_id="y",
        content_type="text/html",
        size_bytes=1,
    )
    # UUID hex is 32 chars
    assert len(str(w.id).replace("-", "")) == 32


def test_share_token_must_be_unique(db, owner):
    Walkthrough.objects.create(
        title="a", kind="html", owner=owner,
        drive_file_id="x1", drive_folder_id="y1",
        content_type="text/html", size_bytes=1,
        visibility="link", share_token="duplicate-token-abc",
    )
    with pytest.raises(Exception):  # IntegrityError
        Walkthrough.objects.create(
            title="b", kind="html", owner=owner,
            drive_file_id="x2", drive_folder_id="y2",
            content_type="text/html", size_bytes=1,
            visibility="link", share_token="duplicate-token-abc",
        )


def test_ensure_share_token_generates_when_link_visibility(db, owner):
    w = Walkthrough.objects.create(
        title="t", kind="video", owner=owner,
        drive_file_id="x", drive_folder_id="y",
        content_type="video/mp4", size_bytes=1,
    )
    assert w.share_token is None
    w.visibility = "link"
    w.ensure_share_token()
    assert w.share_token is not None
    assert len(w.share_token) >= 24


def test_rotate_share_token_changes_value(db, owner):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="x", drive_folder_id="y",
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    old = w.share_token
    w.rotate_share_token()
    assert w.share_token is not None
    assert w.share_token != old
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_walkthroughs_models.py -v`
Expected: collection error or `ImportError: cannot import name 'Walkthrough'`.

- [ ] **Step 3: Implement the model**

Create `apps/walkthroughs/models.py`:

```python
"""Walkthrough model — one shareable HTML slideshow or MP4 video."""
import secrets
import uuid

from django.conf import settings
from django.db import models


class Walkthrough(models.Model):
    KIND_HTML = "html"
    KIND_VIDEO = "video"
    KIND_CHOICES = [
        (KIND_HTML, "HTML"),
        (KIND_VIDEO, "Video"),
    ]

    VISIBILITY_PRIVATE = "private"
    VISIBILITY_LINK = "link"
    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private (dimagi only)"),
        (VISIBILITY_LINK, "Link (anyone with token)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    project_slug = models.CharField(
        max_length=200, blank=True, null=True, db_index=True
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="walkthroughs",
    )
    visibility = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE
    )
    share_token = models.CharField(
        max_length=64, blank=True, null=True, unique=True
    )
    drive_file_id = models.CharField(max_length=128)
    drive_folder_id = models.CharField(max_length=128)
    content_type = models.CharField(max_length=64)
    size_bytes = models.BigIntegerField()
    duration_sec = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project_slug", "-created_at"]),
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.kind})"

    def ensure_share_token(self) -> str:
        """Mint a share token if none exists. Returns the token."""
        if not self.share_token:
            self.share_token = secrets.token_urlsafe(24)
            self.save(update_fields=["share_token", "updated_at"])
        return self.share_token

    def rotate_share_token(self) -> str:
        """Replace the existing share token with a fresh one."""
        self.share_token = secrets.token_urlsafe(24)
        self.save(update_fields=["share_token", "updated_at"])
        return self.share_token
```

- [ ] **Step 4: Generate the migration**

Run: `uv run python manage.py makemigrations walkthroughs`
Expected: `Migrations for 'walkthroughs': apps/walkthroughs/migrations/0001_initial.py - Create model Walkthrough`

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_walkthroughs_models.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/walkthroughs/models.py apps/walkthroughs/migrations/0001_initial.py tests/test_walkthroughs_models.py
git commit -m "feat(walkthroughs): Walkthrough model with share-token rotation"
```

---

## Task 3: Drive client wrapper

**Files:**
- Create: `apps/walkthroughs/drive_client.py`
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/fake_drive.py`

The real Drive client is exercised in Task 4's storage tests (via the fake) — this task introduces both the production client and the test fake so the contract is locked in early.

- [ ] **Step 1: Create the empty fixtures package**

Create `tests/fixtures/__init__.py` (empty file).

- [ ] **Step 2: Define the DriveClient interface + production implementation**

Create `apps/walkthroughs/drive_client.py`:

```python
"""Thin Google Drive v3 wrapper for walkthrough storage.

Modeled on ace-web's apps/opps/drive_client.py but trimmed to the four
methods this app needs: find_or_create_folder, upload, download (range-
aware), delete. Authenticates via a service-account JSON in
CANOPY_DRIVE_SA_KEY_JSON; writes happen under CANOPY_DRIVE_ROOT_FOLDER_ID.
"""
from __future__ import annotations

import functools
import io
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Iterable

from django.conf import settings

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.5

FOLDER_MIME = "application/vnd.google-apps.folder"


def _drive_retry(method):
    """Retry transient Drive errors on read methods (3 attempts, expo backoff)."""

    @functools.wraps(method)
    def _wrapped(self, *args, **kwargs):
        from googleapiclient.errors import HttpError  # noqa: PLC0415

        last_exc: Exception | None = None
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                return method(self, *args, **kwargs)
            except HttpError as exc:
                status = getattr(getattr(exc, "resp", None), "status", None)
                if status not in _RETRYABLE_STATUS or attempt == _RETRY_ATTEMPTS:
                    raise
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                delay += random.uniform(0, delay * 0.25)
                log.warning(
                    "drive_retry: %s attempt %d/%d status=%s sleeping %.2fs",
                    method.__name__, attempt, _RETRY_ATTEMPTS, status, delay,
                )
                time.sleep(delay)
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("drive_retry: unreachable")

    return _wrapped


class DriveNotConfigured(RuntimeError):
    """Raised when CANOPY_DRIVE_SA_KEY_JSON is missing or invalid."""


class DriveClient(ABC):
    """Abstract Drive client — production + fake implementations conform."""

    @abstractmethod
    def find_or_create_folder(self, name: str, parent_id: str) -> str: ...

    @abstractmethod
    def upload(
        self,
        *,
        parent_id: str,
        name: str,
        content_type: str,
        data: bytes,
    ) -> str:
        """Upload bytes, return file_id."""

    @abstractmethod
    def download(
        self,
        file_id: str,
        *,
        start: int | None = None,
        end: int | None = None,
    ) -> tuple[bytes, int, int, int]:
        """Return (chunk_bytes, start, end_inclusive, total_size). If start
        and end are None, returns the whole file with start=0 and
        end=total-1."""

    @abstractmethod
    def delete(self, file_id: str) -> None: ...


def get_drive_client() -> DriveClient:
    """Return the configured production client. Raises DriveNotConfigured
    if the SA key is unset/invalid."""
    raw = getattr(settings, "CANOPY_DRIVE_SA_KEY_JSON", "") or ""
    if not raw:
        raise DriveNotConfigured("CANOPY_DRIVE_SA_KEY_JSON is empty")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DriveNotConfigured(f"invalid JSON in CANOPY_DRIVE_SA_KEY_JSON: {e}") from e
    return GoogleDriveClient(sa_info=info)


class GoogleDriveClient(DriveClient):
    """Real implementation wrapping googleapiclient.discovery."""

    def __init__(self, sa_info: dict):
        from google.oauth2 import service_account  # noqa: PLC0415
        from googleapiclient.discovery import build  # noqa: PLC0415

        creds = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        # cache_discovery=False avoids a noisy warning in containers
        # where the discovery cache dir isn't writable.
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    @_drive_retry
    def find_or_create_folder(self, name: str, parent_id: str) -> str:
        q = (
            f"'{parent_id}' in parents and name = '{name}' "
            f"and mimeType = '{FOLDER_MIME}' and trashed = false"
        )
        resp = self._service.files().list(
            q=q,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = resp.get("files", [])
        if files:
            return files[0]["id"]
        meta = {
            "name": name,
            "mimeType": FOLDER_MIME,
            "parents": [parent_id],
        }
        created = self._service.files().create(
            body=meta,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return created["id"]

    def upload(self, *, parent_id, name, content_type, data) -> str:
        from googleapiclient.http import MediaIoBaseUpload  # noqa: PLC0415

        media = MediaIoBaseUpload(
            io.BytesIO(data), mimetype=content_type, resumable=False
        )
        meta = {"name": name, "parents": [parent_id]}
        created = self._service.files().create(
            body=meta,
            media_body=media,
            fields="id, size",
            supportsAllDrives=True,
        ).execute()
        return created["id"]

    @_drive_retry
    def download(self, file_id, *, start=None, end=None):
        # First, ask Drive for the total size so range math works even
        # when start/end aren't provided.
        meta = self._service.files().get(
            fileId=file_id,
            fields="size",
            supportsAllDrives=True,
        ).execute()
        total = int(meta["size"])
        if start is None:
            start = 0
        if end is None:
            end = total - 1
        end = min(end, total - 1)
        # alt=media + Range header
        req = self._service.files().get_media(fileId=file_id)
        req.headers["Range"] = f"bytes={start}-{end}"
        buf = io.BytesIO()
        from googleapiclient.http import MediaIoBaseDownload  # noqa: PLC0415
        downloader = MediaIoBaseDownload(buf, req, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue(), start, end, total

    def delete(self, file_id) -> None:
        self._service.files().delete(
            fileId=file_id, supportsAllDrives=True
        ).execute()
```

- [ ] **Step 3: Implement the in-memory fake**

Create `tests/fixtures/fake_drive.py`:

```python
"""In-memory DriveClient stand-in for tests. Mirrors the interface
defined in apps/walkthroughs/drive_client.DriveClient."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from apps.walkthroughs.drive_client import DriveClient


@dataclass
class _FakeFile:
    file_id: str
    parent_id: str
    name: str
    content_type: str
    data: bytes
    is_folder: bool = False


@dataclass
class FakeDriveClient(DriveClient):
    files: dict[str, _FakeFile] = field(default_factory=dict)
    root_id: str = "root-folder"

    def __post_init__(self):
        if self.root_id not in self.files:
            self.files[self.root_id] = _FakeFile(
                file_id=self.root_id,
                parent_id="",
                name="ROOT",
                content_type="application/vnd.google-apps.folder",
                data=b"",
                is_folder=True,
            )

    def find_or_create_folder(self, name, parent_id):
        for f in self.files.values():
            if f.is_folder and f.parent_id == parent_id and f.name == name:
                return f.file_id
        fid = f"fake-folder-{uuid.uuid4().hex[:8]}"
        self.files[fid] = _FakeFile(
            file_id=fid, parent_id=parent_id, name=name,
            content_type="application/vnd.google-apps.folder",
            data=b"", is_folder=True,
        )
        return fid

    def upload(self, *, parent_id, name, content_type, data):
        fid = f"fake-file-{uuid.uuid4().hex[:8]}"
        self.files[fid] = _FakeFile(
            file_id=fid, parent_id=parent_id, name=name,
            content_type=content_type, data=data, is_folder=False,
        )
        return fid

    def download(self, file_id, *, start=None, end=None):
        f = self.files[file_id]
        total = len(f.data)
        if start is None:
            start = 0
        if end is None:
            end = total - 1
        end = min(end, total - 1)
        return f.data[start : end + 1], start, end, total

    def delete(self, file_id):
        self.files.pop(file_id, None)
```

- [ ] **Step 4: Smoke-test the fake**

Add this test at the bottom of a new file `tests/test_walkthroughs_drive.py`:

```python
"""Tests for the Drive client + fake fixture."""
from tests.fixtures.fake_drive import FakeDriveClient


def test_fake_upload_download_roundtrip():
    fake = FakeDriveClient()
    folder = fake.find_or_create_folder("walkthroughs", fake.root_id)
    fid = fake.upload(
        parent_id=folder,
        name="slideshow.html",
        content_type="text/html",
        data=b"<html>hello</html>",
    )
    data, start, end, total = fake.download(fid)
    assert data == b"<html>hello</html>"
    assert (start, end, total) == (0, 17, 18)


def test_fake_download_range():
    fake = FakeDriveClient()
    folder = fake.find_or_create_folder("walkthroughs", fake.root_id)
    fid = fake.upload(
        parent_id=folder, name="v.mp4", content_type="video/mp4",
        data=b"0123456789",
    )
    data, start, end, total = fake.download(fid, start=2, end=5)
    assert data == b"2345"
    assert (start, end, total) == (2, 5, 10)


def test_fake_find_or_create_folder_idempotent():
    fake = FakeDriveClient()
    a = fake.find_or_create_folder("x", fake.root_id)
    b = fake.find_or_create_folder("x", fake.root_id)
    assert a == b


def test_fake_delete():
    fake = FakeDriveClient()
    fid = fake.upload(
        parent_id=fake.root_id, name="a", content_type="text/plain", data=b"a",
    )
    fake.delete(fid)
    assert fid not in fake.files
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_walkthroughs_drive.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/walkthroughs/drive_client.py tests/fixtures/ tests/test_walkthroughs_drive.py
git commit -m "feat(walkthroughs): Drive client wrapper + in-memory fake"
```

---

## Task 4: Storage layer (per-walkthrough folder)

**Files:**
- Create: `apps/walkthroughs/storage.py`
- Modify: `tests/test_walkthroughs_drive.py`

- [ ] **Step 1: Add failing tests for the storage layer**

Append to `tests/test_walkthroughs_drive.py`:

```python
import pytest
from django.test import override_settings

from apps.walkthroughs import storage
from apps.walkthroughs.drive_client import DriveNotConfigured


@pytest.fixture
def fake(monkeypatch):
    inst = FakeDriveClient()
    monkeypatch.setattr(storage, "get_drive_client", lambda: inst)
    return inst


@override_settings(CANOPY_DRIVE_ROOT_FOLDER_ID="root-folder")
def test_store_upload_creates_per_walkthrough_subfolder(fake):
    result = storage.store_upload(
        walkthrough_id="uuid-abc",
        filename="slideshow.html",
        content_type="text/html",
        data=b"<html>x</html>",
    )
    assert result.folder_id != "root-folder"
    assert result.file_id in fake.files
    f = fake.files[result.file_id]
    assert f.name == "slideshow.html"
    assert f.content_type == "text/html"


@override_settings(CANOPY_DRIVE_ROOT_FOLDER_ID="root-folder")
def test_delete_stored_removes_file(fake):
    r = storage.store_upload(
        walkthrough_id="uuid-xyz", filename="v.mp4",
        content_type="video/mp4", data=b"...",
    )
    storage.delete_stored(file_id=r.file_id, folder_id=r.folder_id)
    assert r.file_id not in fake.files


@override_settings(CANOPY_DRIVE_ROOT_FOLDER_ID="")
def test_store_upload_raises_when_root_unset(fake):
    with pytest.raises(DriveNotConfigured):
        storage.store_upload(
            walkthrough_id="x", filename="a.html",
            content_type="text/html", data=b"a",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_walkthroughs_drive.py -v`
Expected: 3 new tests fail with `ModuleNotFoundError: No module named 'apps.walkthroughs.storage'`.

- [ ] **Step 3: Implement the storage layer**

Create `apps/walkthroughs/storage.py`:

```python
"""Storage layer over the Drive client.

Drive layout (under CANOPY_DRIVE_ROOT_FOLDER_ID):
    walkthroughs/
        <walkthrough-uuid>/
            slideshow.html  OR  video.mp4

Each walkthrough gets its own subfolder so deletion is a clean
folder-drop and Drive UI stays browseable.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.walkthroughs.drive_client import DriveNotConfigured, get_drive_client

WALKTHROUGHS_FOLDER = "walkthroughs"


@dataclass(frozen=True)
class StoredFile:
    file_id: str
    folder_id: str


def _require_root() -> str:
    root = getattr(settings, "CANOPY_DRIVE_ROOT_FOLDER_ID", "") or ""
    if not root:
        raise DriveNotConfigured("CANOPY_DRIVE_ROOT_FOLDER_ID is empty")
    return root


def store_upload(
    *,
    walkthrough_id: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> StoredFile:
    """Upload bytes under walkthroughs/<id>/<filename>; return ids."""
    root = _require_root()
    client = get_drive_client()
    parent = client.find_or_create_folder(WALKTHROUGHS_FOLDER, root)
    subfolder = client.find_or_create_folder(str(walkthrough_id), parent)
    file_id = client.upload(
        parent_id=subfolder,
        name=filename,
        content_type=content_type,
        data=data,
    )
    return StoredFile(file_id=file_id, folder_id=subfolder)


def download(
    *, file_id: str, start: int | None = None, end: int | None = None
) -> tuple[bytes, int, int, int]:
    """Pass-through to the underlying Drive client. Returns
    (data, start, end_inclusive, total)."""
    client = get_drive_client()
    return client.download(file_id, start=start, end=end)


def delete_stored(*, file_id: str, folder_id: str) -> None:
    """Delete the file. Folder is left in place (Drive trash collects it
    eventually; cheap and avoids races if two walkthroughs ever share a
    folder, which they shouldn't but the cost is zero)."""
    client = get_drive_client()
    client.delete(file_id)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_walkthroughs_drive.py -v`
Expected: 7 passed (4 from Task 3 + 3 here).

- [ ] **Step 5: Commit**

```bash
git add apps/walkthroughs/storage.py tests/test_walkthroughs_drive.py
git commit -m "feat(walkthroughs): per-walkthrough folder storage layer"
```

---

## Task 5: Serializers + settings

**Files:**
- Create: `apps/walkthroughs/serializers.py`
- Modify: `config/settings/base.py`

- [ ] **Step 1: Add settings**

In `config/settings/base.py`, find the `AUTH_ALLOWED_EMAIL_DOMAIN` line (around line 157) and add a new block after the `REQUIRE_AUTH` setting (around line 160):

```python
# --- Walkthrough sharing (apps/walkthroughs) ---
# When False, all /api/walkthroughs/ endpoints 404 (rollout flag).
WALKTHROUGHS_ENABLED = env.bool("WALKTHROUGHS_ENABLED", default=True)

# Google Service Account JSON for the Drive that stores walkthrough
# files. Empty string disables uploads/downloads (returns 500 with
# code="drive-not-configured" — same affordance as ace-web).
CANOPY_DRIVE_SA_KEY_JSON = env("CANOPY_DRIVE_SA_KEY_JSON", default="")

# ID of the shared-drive folder under which "walkthroughs/<uuid>/"
# subfolders are created.
CANOPY_DRIVE_ROOT_FOLDER_ID = env("CANOPY_DRIVE_ROOT_FOLDER_ID", default="")

# Max upload size in bytes for a single walkthrough file. 75 MB covers
# small videos and large HTML decks.
WALKTHROUGH_MAX_UPLOAD_BYTES = env.int(
    "WALKTHROUGH_MAX_UPLOAD_BYTES", default=75 * 1024 * 1024,
)
```

- [ ] **Step 2: Create serializers**

Create `apps/walkthroughs/serializers.py`:

```python
"""DRF serializers for the Walkthrough model."""
from rest_framework import serializers

from .models import Walkthrough


class WalkthroughListItemSerializer(serializers.ModelSerializer):
    owner_email = serializers.CharField(source="owner.email", read_only=True)

    class Meta:
        model = Walkthrough
        fields = [
            "id",
            "title",
            "description",
            "kind",
            "project_slug",
            "visibility",
            "owner_email",
            "size_bytes",
            "duration_sec",
            "created_at",
            "updated_at",
        ]


class WalkthroughDetailSerializer(WalkthroughListItemSerializer):
    """Same as list item, plus share_token (only included when caller
    is owner — view layer enforces that)."""
    share_token = serializers.CharField(read_only=True, allow_null=True)
    content_type = serializers.CharField(read_only=True)
    is_owner = serializers.BooleanField(read_only=True)

    class Meta(WalkthroughListItemSerializer.Meta):
        fields = WalkthroughListItemSerializer.Meta.fields + [
            "share_token",
            "content_type",
            "is_owner",
        ]


class WalkthroughUpdateSerializer(serializers.ModelSerializer):
    """PATCH-able fields only."""

    class Meta:
        model = Walkthrough
        fields = ["title", "description", "project_slug", "visibility"]

    def validate_visibility(self, value):
        if value not in (Walkthrough.VISIBILITY_PRIVATE, Walkthrough.VISIBILITY_LINK):
            raise serializers.ValidationError("invalid visibility")
        return value
```

- [ ] **Step 3: Verify settings load**

Run: `uv run python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add apps/walkthroughs/serializers.py config/settings/base.py
git commit -m "feat(walkthroughs): settings + DRF serializers"
```

---

## Task 6: Upload endpoint (POST /api/walkthroughs/)

**Files:**
- Create: `apps/walkthroughs/views.py`
- Create: `apps/walkthroughs/urls.py`
- Modify: `config/urls.py`
- Create: `tests/test_walkthroughs_views.py`

- [ ] **Step 1: Write the failing tests for upload**

Create `tests/test_walkthroughs_views.py`:

```python
"""Tests for the walkthroughs REST endpoints."""
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.walkthroughs import storage
from apps.walkthroughs.models import Walkthrough
from tests.fixtures.fake_drive import FakeDriveClient


@pytest.fixture
def fake_drive(monkeypatch):
    inst = FakeDriveClient()
    monkeypatch.setattr(storage, "get_drive_client", lambda: inst)
    return inst


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="ace@dimagi.com", email="ace@dimagi.com",
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        username="other@dimagi.com", email="other@dimagi.com",
    )


@pytest.fixture
def auth_client(client, owner):
    client.force_login(owner)
    return client


# ---- Upload ----

@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root-folder",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',  # bypass DriveNotConfigured
)
def test_upload_html_walkthrough(auth_client, fake_drive, owner):
    html = b"<html><body>demo</body></html>"
    resp = auth_client.post(
        "/api/walkthroughs/",
        data={
            "file": _file_part("slideshow.html", html, "text/html"),
            "title": "Skill Builder Demo",
            "kind": "html",
        },
        format="multipart",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()["data"]
    assert body["title"] == "Skill Builder Demo"
    assert body["kind"] == "html"
    assert body["visibility"] == "private"
    w = Walkthrough.objects.get(id=body["id"])
    assert w.owner == owner
    assert w.drive_file_id in fake_drive.files
    assert fake_drive.files[w.drive_file_id].data == html


@override_settings(WALKTHROUGHS_ENABLED=False)
def test_upload_404_when_flag_off(auth_client):
    resp = auth_client.post("/api/walkthroughs/", data={})
    assert resp.status_code == 404


def test_upload_requires_login(client):
    resp = client.post("/api/walkthroughs/", data={})
    assert resp.status_code in (302, 401)


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    WALKTHROUGH_MAX_UPLOAD_BYTES=10,
)
def test_upload_rejects_oversize(auth_client, fake_drive):
    resp = auth_client.post(
        "/api/walkthroughs/",
        data={
            "file": _file_part("a.html", b"x" * 20, "text/html"),
            "title": "x", "kind": "html",
        },
        format="multipart",
    )
    assert resp.status_code == 413


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
)
def test_upload_rejects_unknown_kind(auth_client, fake_drive):
    resp = auth_client.post(
        "/api/walkthroughs/",
        data={
            "file": _file_part("a.pdf", b"x", "application/pdf"),
            "title": "x", "kind": "pdf",
        },
        format="multipart",
    )
    assert resp.status_code == 400


# Helper — Django test client wants SimpleUploadedFile for multipart.
def _file_part(name, content, content_type):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, content, content_type=content_type)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_walkthroughs_views.py -v`
Expected: 404 on the URL — endpoint not wired.

- [ ] **Step 3: Implement the upload view**

Create `apps/walkthroughs/views.py`:

```python
"""REST endpoints for walkthroughs."""
from __future__ import annotations

from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from . import storage
from .drive_client import DriveNotConfigured
from .models import Walkthrough
from .serializers import (
    WalkthroughDetailSerializer,
    WalkthroughListItemSerializer,
    WalkthroughUpdateSerializer,
)

KIND_BY_EXTENSION = {".html": "html", ".htm": "html", ".mp4": "video"}
CONTENT_TYPE_BY_KIND = {"html": "text/html", "video": "video/mp4"}


def _require_enabled():
    if not getattr(settings, "WALKTHROUGHS_ENABLED", True):
        raise Http404("walkthroughs disabled")


@api_view(["GET", "POST"])
def walkthroughs_list_or_create(request):
    _require_enabled()
    start_timing()

    if request.method == "POST":
        return _upload(request)
    return _list(request)


def _upload(request):
    upload = request.FILES.get("file")
    if upload is None:
        return Response(
            error_response("VALIDATION_ERROR", "file is required"),
            status=status.HTTP_400_BAD_REQUEST,
        )

    title = (request.data.get("title") or "").strip() or upload.name
    kind = (request.data.get("kind") or "").strip().lower()
    if kind not in CONTENT_TYPE_BY_KIND:
        return Response(
            error_response(
                "VALIDATION_ERROR",
                f"kind must be one of: {sorted(CONTENT_TYPE_BY_KIND)}",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    max_bytes = getattr(settings, "WALKTHROUGH_MAX_UPLOAD_BYTES", 75 * 1024 * 1024)
    if upload.size > max_bytes:
        return Response(
            error_response(
                "PAYLOAD_TOO_LARGE",
                f"upload exceeds {max_bytes} bytes",
            ),
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    project_slug = (request.data.get("project_slug") or "").strip() or None
    description = (request.data.get("description") or "").strip()
    visibility_raw = (request.data.get("visibility") or "").strip().lower()
    visibility = (
        Walkthrough.VISIBILITY_LINK
        if visibility_raw == Walkthrough.VISIBILITY_LINK
        else Walkthrough.VISIBILITY_PRIVATE
    )

    content_type = CONTENT_TYPE_BY_KIND[kind]
    data = upload.read()

    # Create row first so we have the UUID for the folder name. If the
    # Drive write fails we delete the row in the same request — no
    # orphan metadata.
    w = Walkthrough.objects.create(
        title=title[:200],
        description=description,
        kind=kind,
        project_slug=project_slug,
        owner=request.user,
        visibility=visibility,
        drive_file_id="",
        drive_folder_id="",
        content_type=content_type,
        size_bytes=len(data),
    )
    try:
        stored = storage.store_upload(
            walkthrough_id=str(w.id),
            filename=("slideshow.html" if kind == "html" else "video.mp4"),
            content_type=content_type,
            data=data,
        )
    except DriveNotConfigured as e:
        w.delete()
        return Response(
            error_response("drive-not-configured", str(e)),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception as e:
        w.delete()
        return Response(
            error_response("drive-upload-failed", str(e)),
            status=status.HTTP_502_BAD_GATEWAY,
        )

    w.drive_file_id = stored.file_id
    w.drive_folder_id = stored.folder_id
    w.save(update_fields=["drive_file_id", "drive_folder_id", "updated_at"])
    if visibility == Walkthrough.VISIBILITY_LINK:
        w.ensure_share_token()

    body = WalkthroughDetailSerializer(w).data
    body["is_owner"] = True
    return Response(success_response(body), status=status.HTTP_201_CREATED)


def _list(request):
    qs = Walkthrough.objects.all()
    project = request.query_params.get("project")
    if project:
        qs = qs.filter(project_slug=project)
    kind = request.query_params.get("kind")
    if kind in (Walkthrough.KIND_HTML, Walkthrough.KIND_VIDEO):
        qs = qs.filter(kind=kind)
    if request.query_params.get("mine") == "true" and request.user.is_authenticated:
        qs = qs.filter(owner=request.user)
    data = WalkthroughListItemSerializer(qs, many=True).data
    return Response(success_response(data))
```

- [ ] **Step 4: Wire URLs**

Create `apps/walkthroughs/urls.py`:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.walkthroughs_list_or_create, name="walkthroughs-list-or-create"),
]
```

In `config/urls.py`, find the `urlpatterns` list and add a new line before the catch-all `re_path`:

```python
    path("api/walkthroughs/", include("apps.walkthroughs.urls")),
```

- [ ] **Step 5: Run upload tests**

Run: `uv run pytest tests/test_walkthroughs_views.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/walkthroughs/views.py apps/walkthroughs/urls.py config/urls.py tests/test_walkthroughs_views.py
git commit -m "feat(walkthroughs): POST /api/walkthroughs/ upload endpoint"
```

---

## Task 7: List, detail, patch, delete, rotate-token

**Files:**
- Modify: `apps/walkthroughs/views.py`
- Modify: `apps/walkthroughs/urls.py`
- Modify: `tests/test_walkthroughs_views.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_walkthroughs_views.py`:

```python
# ---- List ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_list_returns_all(auth_client, db, owner):
    Walkthrough.objects.create(
        title="a", kind="html", owner=owner,
        drive_file_id="f1", drive_folder_id="d1",
        content_type="text/html", size_bytes=1,
    )
    Walkthrough.objects.create(
        title="b", kind="video", owner=owner,
        drive_file_id="f2", drive_folder_id="d2",
        content_type="video/mp4", size_bytes=1,
    )
    resp = auth_client.get("/api/walkthroughs/")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) == 2


@override_settings(WALKTHROUGHS_ENABLED=True)
def test_list_filters_by_project_and_kind(auth_client, db, owner):
    Walkthrough.objects.create(
        title="a", kind="html", owner=owner, project_slug="canopy-web",
        drive_file_id="f1", drive_folder_id="d1",
        content_type="text/html", size_bytes=1,
    )
    Walkthrough.objects.create(
        title="b", kind="video", owner=owner, project_slug="ace-web",
        drive_file_id="f2", drive_folder_id="d2",
        content_type="video/mp4", size_bytes=1,
    )
    resp = auth_client.get("/api/walkthroughs/?project=canopy-web")
    assert [w["title"] for w in resp.json()["data"]] == ["a"]
    resp = auth_client.get("/api/walkthroughs/?kind=video")
    assert [w["title"] for w in resp.json()["data"]] == ["b"]


# ---- Detail ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_detail_owner_sees_token_and_is_owner_true(auth_client, db, owner):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    resp = auth_client.get(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["is_owner"] is True
    assert body["share_token"] == w.share_token


@override_settings(WALKTHROUGHS_ENABLED=True)
def test_detail_non_owner_does_not_see_token(client, db, owner, other_user):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    client.force_login(other_user)
    resp = client.get(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["is_owner"] is False
    assert body["share_token"] is None


# ---- PATCH ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_patch_owner_can_update(auth_client, db, owner):
    w = Walkthrough.objects.create(
        title="old", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
    )
    resp = auth_client.patch(
        f"/api/walkthroughs/{w.id}/",
        data=json.dumps({"title": "new", "visibility": "link"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    w.refresh_from_db()
    assert w.title == "new"
    assert w.visibility == "link"
    assert w.share_token is not None  # auto-minted on link switch


@override_settings(WALKTHROUGHS_ENABLED=True)
def test_patch_non_owner_forbidden(client, db, owner, other_user):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
    )
    client.force_login(other_user)
    resp = client.patch(
        f"/api/walkthroughs/{w.id}/",
        data=json.dumps({"title": "x"}),
        content_type="application/json",
    )
    assert resp.status_code == 403


# ---- DELETE ----

@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_delete_owner_drops_row_and_drive_file(auth_client, fake_drive, owner):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="manual-file", drive_folder_id="manual-folder",
        content_type="text/html", size_bytes=1,
    )
    fake_drive.files["manual-file"] = fake_drive.files.get(
        "manual-file"
    ) or type(fake_drive.files[fake_drive.root_id])(
        file_id="manual-file", parent_id="manual-folder", name="x",
        content_type="text/html", data=b"x", is_folder=False,
    )
    resp = auth_client.delete(f"/api/walkthroughs/{w.id}/")
    assert resp.status_code == 204
    assert not Walkthrough.objects.filter(id=w.id).exists()
    assert "manual-file" not in fake_drive.files


# ---- Rotate token ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_rotate_token(auth_client, db, owner):
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    old = w.share_token
    resp = auth_client.post(f"/api/walkthroughs/{w.id}/rotate-token/")
    assert resp.status_code == 200
    new_token = resp.json()["data"]["share_token"]
    assert new_token and new_token != old
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_walkthroughs_views.py -v`
Expected: 7 new failures (404 on the new URLs / wrong status codes).

- [ ] **Step 3: Implement detail, patch, delete, rotate**

Append to `apps/walkthroughs/views.py`:

```python
def _get_or_404(wid):
    try:
        return Walkthrough.objects.get(pk=wid)
    except (Walkthrough.DoesNotExist, ValueError):
        return None


def _serialize_detail(w, *, is_owner: bool):
    data = WalkthroughDetailSerializer(w).data
    data["is_owner"] = is_owner
    if not is_owner:
        data["share_token"] = None
    return data


@api_view(["GET", "PATCH", "DELETE"])
def walkthrough_detail(request, wid):
    _require_enabled()
    start_timing()
    w = _get_or_404(wid)
    if w is None:
        return Response(
            error_response("NOT_FOUND", "walkthrough not found"),
            status=status.HTTP_404_NOT_FOUND,
        )

    is_owner = request.user.is_authenticated and w.owner_id == request.user.id

    if request.method == "GET":
        return Response(success_response(_serialize_detail(w, is_owner=is_owner)))

    # Mutations require owner.
    if not is_owner:
        return Response(
            error_response("FORBIDDEN", "owner only"),
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "DELETE":
        if w.drive_file_id:
            try:
                storage.delete_stored(file_id=w.drive_file_id, folder_id=w.drive_folder_id)
            except DriveNotConfigured:
                # Without Drive configured we can't clean Drive, but we
                # should still drop the row so the UI matches reality.
                pass
            except Exception:
                # Log and continue — orphan Drive files are recoverable;
                # an orphan row would block the user from re-deleting.
                pass
        w.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    serializer = WalkthroughUpdateSerializer(w, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    w.refresh_from_db()
    if w.visibility == Walkthrough.VISIBILITY_LINK and not w.share_token:
        w.ensure_share_token()
    return Response(success_response(_serialize_detail(w, is_owner=True)))


@api_view(["POST"])
def walkthrough_rotate_token(request, wid):
    _require_enabled()
    start_timing()
    w = _get_or_404(wid)
    if w is None:
        return Response(
            error_response("NOT_FOUND", "walkthrough not found"),
            status=status.HTTP_404_NOT_FOUND,
        )
    if not request.user.is_authenticated or w.owner_id != request.user.id:
        return Response(
            error_response("FORBIDDEN", "owner only"),
            status=status.HTTP_403_FORBIDDEN,
        )
    new_token = w.rotate_share_token()
    return Response(success_response({"share_token": new_token}))
```

- [ ] **Step 4: Wire URLs**

Edit `apps/walkthroughs/urls.py` to add detail + rotate routes:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.walkthroughs_list_or_create, name="walkthroughs-list-or-create"),
    path("<uuid:wid>/", views.walkthrough_detail, name="walkthrough-detail"),
    path("<uuid:wid>/rotate-token/", views.walkthrough_rotate_token, name="walkthrough-rotate-token"),
]
```

- [ ] **Step 5: Run all view tests**

Run: `uv run pytest tests/test_walkthroughs_views.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add apps/walkthroughs/views.py apps/walkthroughs/urls.py tests/test_walkthroughs_views.py
git commit -m "feat(walkthroughs): detail, patch, delete, rotate-token endpoints"
```

---

## Task 8: Streaming view at /w/<id>/content with token + Range

**Files:**
- Modify: `apps/walkthroughs/views.py`
- Modify: `config/urls.py`
- Modify: `apps/common/middleware.py`
- Modify: `tests/test_walkthroughs_views.py`

The path `/w/<id>/content` lives at the root, not under `/api/`, because the viewer page hits it directly as an `<iframe src>` / `<video src>`. The middleware needs to allowlist it conditionally (auth via session OR valid token query param).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_walkthroughs_views.py`:

```python
# ---- Content streaming ----

@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_content_private_requires_session(client, db, owner, fake_drive):
    stored = storage.store_upload(
        walkthrough_id="abc", filename="slideshow.html",
        content_type="text/html", data=b"<html>x</html>",
    )
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id=stored.file_id, drive_folder_id=stored.folder_id,
        content_type="text/html", size_bytes=12,
    )
    # Anonymous → middleware redirects or 401
    resp = client.get(f"/w/{w.id}/content")
    assert resp.status_code in (302, 401, 404)


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_content_link_visibility_serves_with_token(client, db, owner, fake_drive):
    stored = storage.store_upload(
        walkthrough_id="abc", filename="slideshow.html",
        content_type="text/html", data=b"<html>linked</html>",
    )
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id=stored.file_id, drive_folder_id=stored.folder_id,
        content_type="text/html", size_bytes=17,
        visibility="link",
    )
    w.ensure_share_token()
    resp = client.get(f"/w/{w.id}/content?t={w.share_token}")
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content) == b"<html>linked</html>"
    assert resp["Content-Type"].startswith("text/html")


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_content_wrong_token_returns_404_not_403(client, db, owner, fake_drive):
    stored = storage.store_upload(
        walkthrough_id="abc", filename="slideshow.html",
        content_type="text/html", data=b"x",
    )
    w = Walkthrough.objects.create(
        title="t", kind="html", owner=owner,
        drive_file_id=stored.file_id, drive_folder_id=stored.folder_id,
        content_type="text/html", size_bytes=1,
        visibility="link",
    )
    w.ensure_share_token()
    resp = client.get(f"/w/{w.id}/content?t=wrongtoken")
    assert resp.status_code == 404


@override_settings(
    WALKTHROUGHS_ENABLED=True,
    CANOPY_DRIVE_SA_KEY_JSON='{"x":"y"}',
    CANOPY_DRIVE_ROOT_FOLDER_ID="root",
)
def test_content_range_request_serves_partial(client, db, owner, fake_drive):
    stored = storage.store_upload(
        walkthrough_id="abc", filename="video.mp4",
        content_type="video/mp4", data=b"0123456789",
    )
    w = Walkthrough.objects.create(
        title="t", kind="video", owner=owner,
        drive_file_id=stored.file_id, drive_folder_id=stored.folder_id,
        content_type="video/mp4", size_bytes=10,
        visibility="link",
    )
    w.ensure_share_token()
    resp = client.get(
        f"/w/{w.id}/content?t={w.share_token}",
        HTTP_RANGE="bytes=2-5",
    )
    assert resp.status_code == 206
    assert b"".join(resp.streaming_content) == b"2345"
    assert resp["Content-Range"] == "bytes 2-5/10"
    assert resp["Accept-Ranges"] == "bytes"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_walkthroughs_views.py -v -k content`
Expected: 4 new failures.

- [ ] **Step 3: Implement the content view**

Append to `apps/walkthroughs/views.py`:

```python
import re

from django.http import HttpResponse, StreamingHttpResponse

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)$")


def _parse_range(header: str, total: int) -> tuple[int, int] | None:
    """Parse a single-range HTTP Range header. Multi-range not supported."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    start = int(m.group(1))
    end_raw = m.group(2)
    end = int(end_raw) if end_raw else total - 1
    if start > end or start >= total:
        return None
    return start, min(end, total - 1)


def walkthrough_content(request, wid):
    """GET /w/<id>/content — stream the file bytes from Drive.

    Auth: caller is the authenticated owner OR visibility=link with a
    valid ?t=<share_token>. Mismatch returns 404 (don't leak existence
    of private walkthroughs).
    """
    if not getattr(settings, "WALKTHROUGHS_ENABLED", True):
        raise Http404("walkthroughs disabled")

    w = _get_or_404(wid)
    if w is None:
        raise Http404("walkthrough not found")

    token = request.GET.get("t", "")
    is_authed = request.user.is_authenticated
    token_ok = (
        w.visibility == Walkthrough.VISIBILITY_LINK
        and bool(w.share_token)
        and token == w.share_token
    )
    if not (is_authed or token_ok):
        raise Http404("walkthrough not found")

    range_hdr = request.META.get("HTTP_RANGE", "")
    try:
        # Probe size by asking for 1 byte first if there's no Range; for
        # most files this is wasted, so instead just stream full and let
        # Drive give us the size. For Range requests we need to parse
        # before download.
        if range_hdr:
            # We need the total to clamp the range — do a tiny head download.
            _, _, _, total = storage.download(
                file_id=w.drive_file_id, start=0, end=0,
            )
            parsed = _parse_range(range_hdr, total)
            if parsed is None:
                resp = HttpResponse(status=416)
                resp["Content-Range"] = f"bytes */{total}"
                return resp
            start, end = parsed
            data, s, e, t = storage.download(
                file_id=w.drive_file_id, start=start, end=end,
            )
            resp = StreamingHttpResponse(
                iter([data]),
                status=206,
                content_type=w.content_type,
            )
            resp["Content-Range"] = f"bytes {s}-{e}/{t}"
            resp["Content-Length"] = str(len(data))
            resp["Accept-Ranges"] = "bytes"
            return resp

        data, s, e, t = storage.download(file_id=w.drive_file_id)
        resp = StreamingHttpResponse(
            iter([data]),
            status=200,
            content_type=w.content_type,
        )
        resp["Content-Length"] = str(len(data))
        resp["Accept-Ranges"] = "bytes"
        return resp
    except DriveNotConfigured:
        return HttpResponse(status=500)
    except Exception:
        return HttpResponse(status=502)
```

- [ ] **Step 4: Wire the URL**

In `config/urls.py`, add this line before the catch-all `re_path` (after the `/api/walkthroughs/` line from Task 6):

```python
    path("w/<uuid:wid>/content", views_walkthrough_content, name="walkthrough-content"),
```

At the top of `config/urls.py`, add the import:

```python
from apps.walkthroughs.views import walkthrough_content as views_walkthrough_content
```

- [ ] **Step 5: Allowlist the content URL for token-based access**

In `apps/common/middleware.py`, edit the `LoginRequiredMiddleware.__call__` method (or the relevant gate function) — the simplest expression is to add a path-prefix bypass.

Find the section that classifies the request (around `_is_public` use). Add a new helper near the existing ones:

```python
def _is_walkthrough_content(path: str) -> bool:
    # /w/<uuid>/content — the view itself enforces token-or-session auth.
    # We let it through the middleware so the per-token public link can
    # be served without a session cookie.
    return path.startswith("/w/") and path.endswith("/content")
```

Then in the request-classification block of `LoginRequiredMiddleware.__call__`, allow requests matching `_is_walkthrough_content(request.path)` alongside the existing `_is_public(...)` check. **Read the file before editing** — preserve existing branches; just add an `or _is_walkthrough_content(request.path)` to the public-allow condition.

- [ ] **Step 6: Run the content tests**

Run: `uv run pytest tests/test_walkthroughs_views.py -v -k content`
Expected: 4 passed.

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -v`
Expected: all passing (existing + new).

- [ ] **Step 8: Commit**

```bash
git add apps/walkthroughs/views.py config/urls.py apps/common/middleware.py tests/test_walkthroughs_views.py
git commit -m "feat(walkthroughs): /w/<id>/content streams with Range + token gate"
```

---

## Task 9: Project-tile integration (walkthrough count)

**Files:**
- Modify: `apps/projects/views.py`
- Modify: `apps/projects/serializers.py` (if a detail serializer adds the field) — or just inject into the response dict in views; pick whichever matches the existing style
- Modify: `tests/test_walkthroughs_views.py` (new test)

Before editing, **read the existing `apps/projects/views.py` `project_detail` view** to find where the response dict is assembled. The walkthrough count is added there.

- [ ] **Step 1: Write a failing test**

Append to `tests/test_walkthroughs_views.py`:

```python
# ---- Project tile integration ----

@override_settings(WALKTHROUGHS_ENABLED=True)
def test_project_detail_includes_walkthrough_count(auth_client, db, owner):
    from apps.projects.models import Project
    p = Project.objects.create(name="Canopy", slug="canopy-web")
    Walkthrough.objects.create(
        title="a", kind="html", owner=owner, project_slug="canopy-web",
        drive_file_id="f", drive_folder_id="d",
        content_type="text/html", size_bytes=1,
    )
    Walkthrough.objects.create(
        title="b", kind="html", owner=owner, project_slug="canopy-web",
        drive_file_id="f2", drive_folder_id="d2",
        content_type="text/html", size_bytes=1,
    )
    Walkthrough.objects.create(
        title="other", kind="html", owner=owner, project_slug="ace-web",
        drive_file_id="f3", drive_folder_id="d3",
        content_type="text/html", size_bytes=1,
    )
    resp = auth_client.get(f"/api/projects/{p.slug}/")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["walkthrough_count"] == 2
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_walkthroughs_views.py -v -k project_detail`
Expected: KeyError on `walkthrough_count`.

- [ ] **Step 3: Add the count to project detail**

In `apps/projects/views.py`, locate the `project_detail` view. After the project is fetched and the serializer dict is built (look for the pattern `Response(success_response(serializer.data))` or similar), inject the count:

```python
from apps.walkthroughs.models import Walkthrough  # at top of file

# ... in project_detail, after building the response body:
body = serializer.data  # or however it's currently constructed
body["walkthrough_count"] = Walkthrough.objects.filter(
    project_slug=project.slug
).count()
return Response(success_response(body))
```

Adjust as needed to match the existing code style in `apps/projects/views.py`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_walkthroughs_views.py -v -k project_detail`
Expected: pass.

Run: `uv run pytest tests/test_projects.py -v` (if present)
Expected: existing project tests still pass.

- [ ] **Step 5: Commit**

```bash
git add apps/projects/views.py tests/test_walkthroughs_views.py
git commit -m "feat(walkthroughs): expose walkthrough_count on project detail"
```

---

## Task 10: Frontend API client + types

**Files:**
- Create: `frontend/src/api/walkthroughs.ts`

- [ ] **Step 1: Write the client**

Create `frontend/src/api/walkthroughs.ts`:

```typescript
const BASE = '/api'

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

function redirectToLogin(): never {
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.href = `/accounts/google/login/?next=${next}`
  throw new Error('Redirecting to login')
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> | undefined),
  }
  // Don't force Content-Type for FormData — the browser sets it with boundary.
  const isForm = options?.body instanceof FormData
  if (!isForm && method !== 'GET' && method !== 'HEAD') {
    headers['Content-Type'] = 'application/json'
  }
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
    const token = getCsrfToken()
    if (token) headers['X-CSRFToken'] = token
  }
  const resp = await fetch(`${BASE}${path}`, {
    credentials: 'same-origin',
    ...options,
    headers,
  })
  if (resp.status === 401) redirectToLogin()
  if (resp.status === 204) return undefined as T
  const data = await resp.json()
  if (!data.success) throw new Error(data.error?.message || 'Request failed')
  return data.data as T
}

export type WalkthroughKind = 'html' | 'video'
export type WalkthroughVisibility = 'private' | 'link'

export interface WalkthroughListItem {
  id: string
  title: string
  description: string
  kind: WalkthroughKind
  project_slug: string | null
  visibility: WalkthroughVisibility
  owner_email: string
  size_bytes: number
  duration_sec: number | null
  created_at: string
  updated_at: string
}

export interface WalkthroughDetail extends WalkthroughListItem {
  share_token: string | null
  content_type: string
  is_owner: boolean
}

export interface WalkthroughListFilters {
  project?: string
  kind?: WalkthroughKind
  mine?: boolean
}

export async function listWalkthroughs(
  filters: WalkthroughListFilters = {},
): Promise<WalkthroughListItem[]> {
  const params = new URLSearchParams()
  if (filters.project) params.set('project', filters.project)
  if (filters.kind) params.set('kind', filters.kind)
  if (filters.mine) params.set('mine', 'true')
  const qs = params.toString()
  return request<WalkthroughListItem[]>(`/walkthroughs/${qs ? `?${qs}` : ''}`)
}

export async function getWalkthrough(id: string): Promise<WalkthroughDetail> {
  return request<WalkthroughDetail>(`/walkthroughs/${id}/`)
}

export interface PatchWalkthroughInput {
  title?: string
  description?: string
  project_slug?: string | null
  visibility?: WalkthroughVisibility
}

export async function patchWalkthrough(
  id: string,
  patch: PatchWalkthroughInput,
): Promise<WalkthroughDetail> {
  return request<WalkthroughDetail>(`/walkthroughs/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export async function deleteWalkthrough(id: string): Promise<void> {
  await request<void>(`/walkthroughs/${id}/`, { method: 'DELETE' })
}

export async function rotateWalkthroughToken(
  id: string,
): Promise<{ share_token: string }> {
  return request<{ share_token: string }>(
    `/walkthroughs/${id}/rotate-token/`,
    { method: 'POST' },
  )
}

export function walkthroughContentUrl(
  id: string,
  shareToken: string | null,
): string {
  const t = shareToken ? `?t=${encodeURIComponent(shareToken)}` : ''
  return `/w/${id}/content${t}`
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/walkthroughs.ts
git commit -m "feat(walkthroughs): frontend API client + types"
```

---

## Task 11: WalkthroughsPage (list + filters)

**Files:**
- Create: `frontend/src/pages/WalkthroughsPage.tsx`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/AppLayout/AppLayout.tsx`

Before editing the layout, **read `frontend/src/components/AppLayout/AppLayout.tsx`** to match the existing nav-link style (look at how `/skills`, `/insights`, `/leaderboard` are wired).

- [ ] **Step 1: Write the page**

Create `frontend/src/pages/WalkthroughsPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  listWalkthroughs,
  type WalkthroughListItem,
  type WalkthroughKind,
} from '../api/walkthroughs'

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function VisibilityChip({ v }: { v: 'private' | 'link' }) {
  const cls =
    v === 'link'
      ? 'bg-emerald-100 text-emerald-800'
      : 'bg-slate-100 text-slate-700'
  return (
    <span className={`px-2 py-0.5 text-xs rounded ${cls}`}>
      {v === 'link' ? 'Link' : 'Private'}
    </span>
  )
}

export function WalkthroughsPage() {
  const [params, setParams] = useSearchParams()
  const project = params.get('project') ?? ''
  const kind = (params.get('kind') as WalkthroughKind | null) ?? null
  const mine = params.get('mine') === 'true'

  const [items, setItems] = useState<WalkthroughListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setItems(null)
    setError(null)
    listWalkthroughs({
      project: project || undefined,
      kind: kind ?? undefined,
      mine: mine || undefined,
    })
      .then((data) => {
        if (!cancelled) setItems(data)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e.message || e))
      })
    return () => {
      cancelled = true
    }
  }, [project, kind, mine])

  const distinctProjects = useMemo(() => {
    if (!items) return []
    const s = new Set<string>()
    for (const w of items) if (w.project_slug) s.add(w.project_slug)
    return [...s].sort()
  }, [items])

  function update(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value == null || value === '') next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      <header className="flex items-baseline justify-between mb-6">
        <h1 className="text-2xl font-semibold">Walkthroughs</h1>
        <p className="text-sm text-slate-500">
          Sharable demos uploaded from <code>/canopy:walkthrough</code>
        </p>
      </header>

      <div className="flex gap-3 mb-4 text-sm">
        <select
          className="border rounded px-2 py-1"
          value={project}
          onChange={(e) => update('project', e.target.value)}
        >
          <option value="">All projects</option>
          {distinctProjects.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select
          className="border rounded px-2 py-1"
          value={kind ?? ''}
          onChange={(e) => update('kind', e.target.value || null)}
        >
          <option value="">All kinds</option>
          <option value="html">HTML</option>
          <option value="video">Video</option>
        </select>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => update('mine', e.target.checked ? 'true' : null)}
          />
          Mine only
        </label>
      </div>

      {error && (
        <div className="text-red-600 text-sm mb-3">Failed: {error}</div>
      )}
      {items === null && !error && (
        <div className="text-slate-500 text-sm">Loading…</div>
      )}
      {items && items.length === 0 && (
        <div className="text-slate-500 text-sm">No walkthroughs match.</div>
      )}
      {items && items.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-slate-500 border-b">
            <tr>
              <th className="py-2 pr-3">Title</th>
              <th className="py-2 pr-3">Project</th>
              <th className="py-2 pr-3">Kind</th>
              <th className="py-2 pr-3">Owner</th>
              <th className="py-2 pr-3">Visibility</th>
              <th className="py-2 pr-3">Size</th>
              <th className="py-2 pr-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {items.map((w) => (
              <tr key={w.id} className="border-b hover:bg-slate-50">
                <td className="py-2 pr-3">
                  <Link to={`/w/${w.id}`} className="text-blue-700 hover:underline">
                    {w.title}
                  </Link>
                </td>
                <td className="py-2 pr-3">
                  {w.project_slug ? (
                    <Link to={`/?project=${w.project_slug}`} className="text-slate-700 hover:underline">
                      {w.project_slug}
                    </Link>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                <td className="py-2 pr-3 capitalize">{w.kind}</td>
                <td className="py-2 pr-3">{w.owner_email}</td>
                <td className="py-2 pr-3">
                  <VisibilityChip v={w.visibility} />
                </td>
                <td className="py-2 pr-3">{formatBytes(w.size_bytes)}</td>
                <td className="py-2 pr-3 text-slate-500">
                  {new Date(w.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Register the route**

In `frontend/src/router.tsx`, add:

```tsx
import { WalkthroughsPage } from './pages/WalkthroughsPage'
```

And add a route inside `children:` (alongside `/skills`, etc.):

```tsx
      { path: '/walkthroughs', element: <WalkthroughsPage /> },
```

- [ ] **Step 3: Add nav link**

In `frontend/src/components/AppLayout/AppLayout.tsx`, add a `Walkthroughs` nav link matching the existing pattern used for `Skills`/`Insights`/`Leaderboard`. Read the file first to match link styling exactly.

- [ ] **Step 4: Type-check + build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/WalkthroughsPage.tsx frontend/src/router.tsx frontend/src/components/AppLayout/AppLayout.tsx
git commit -m "feat(walkthroughs): /walkthroughs list page + nav link"
```

---

## Task 12: WalkthroughViewerPage (/w/:id with owner toolbar)

**Files:**
- Create: `frontend/src/pages/WalkthroughViewerPage.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Write the viewer page**

Create `frontend/src/pages/WalkthroughViewerPage.tsx`:

```tsx
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
```

- [ ] **Step 2: Register the route**

In `frontend/src/router.tsx`, import and add:

```tsx
import { WalkthroughViewerPage } from './pages/WalkthroughViewerPage'
// ...
      { path: '/w/:id', element: <WalkthroughViewerPage /> },
```

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Manual smoke (deferred to Task 14)**

Note for the engineer: full local browser testing is bundled in Task 14 so you only spin up the dev server once. Move on for now.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/WalkthroughViewerPage.tsx frontend/src/router.tsx
git commit -m "feat(walkthroughs): /w/:id viewer with owner toolbar"
```

---

## Task 13: Project tile link + docs

**Files:**
- Modify: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/api/projects.ts` (add `walkthrough_count` to type)
- Modify: `CLAUDE.md`
- Modify: `TODOS.md` (create if not present)

- [ ] **Step 1: Add `walkthrough_count` to project type**

In `frontend/src/api/projects.ts`, find the `Project` interface and add:

```ts
  walkthrough_count?: number
```

- [ ] **Step 2: Render the count link in the expanded tile**

**Read `frontend/src/pages/ProjectsPage.tsx`** to find the expanded-card layout (the "3-column" section per CLAUDE.md). In the rightmost column where details/skills live, add (only when `count > 0`):

```tsx
{project.walkthrough_count && project.walkthrough_count > 0 ? (
  <a
    href={`/walkthroughs?project=${project.slug}`}
    className="text-sm text-blue-700 hover:underline"
  >
    Walkthroughs · {project.walkthrough_count}
  </a>
) : null}
```

- [ ] **Step 3: Document endpoints in CLAUDE.md**

In `CLAUDE.md`, find the API Endpoints section. Add a new subsection after the Projects block (and add `/walkthroughs` to the Key URLs list above):

```markdown
### Walkthroughs
- `GET /api/walkthroughs/` — List. Filters: `?project=<slug>`, `?kind=html|video`, `?mine=true`
- `POST /api/walkthroughs/` — Upload (multipart). Fields: `file`, `title`, `kind` (html|video), optional `description`, `project_slug`, `visibility` (private|link)
- `GET /api/walkthroughs/<uuid>/` — Detail. Returns `share_token` only to owner; `is_owner` flag tells the UI which toolbar to render
- `PATCH /api/walkthroughs/<uuid>/` — Owner-only update of title/description/project_slug/visibility. Switching to `visibility=link` auto-mints `share_token`
- `DELETE /api/walkthroughs/<uuid>/` — Owner-only. Deletes Drive file and the row
- `POST /api/walkthroughs/<uuid>/rotate-token/` — Owner-only. Mints a fresh `share_token`, invalidating the old one
- `GET /w/<uuid>/content?t=<token>` — Streams file bytes. Session-auth OR valid token. Range-aware (supports `<video>` scrubbing)
```

In the Key URLs list, add:

```markdown
- `/walkthroughs` — Sharable demos uploaded from `/canopy:walkthrough`
- `/w/:id` — Single walkthrough viewer (HTML iframe or video player)
```

- [ ] **Step 4: Document settings in CLAUDE.md**

In the existing settings/env documentation (look for `AUTH_ALLOWED_EMAIL_DOMAIN` or similar), add:

```markdown
- `WALKTHROUGHS_ENABLED` (default `True`) — endpoints 404 when off
- `CANOPY_DRIVE_SA_KEY_JSON` — Google Drive service-account key (JSON string). Empty disables uploads/streams
- `CANOPY_DRIVE_ROOT_FOLDER_ID` — Shared-drive folder ID. `walkthroughs/<uuid>/` subfolders created under it
- `WALKTHROUGH_MAX_UPLOAD_BYTES` (default 75 MB)
```

- [ ] **Step 5: Append deferred items to TODOS.md**

If `TODOS.md` exists, append. Otherwise create it:

```markdown
## Walkthrough sharing — deferred (V2)

- View analytics (who viewed, when, where from)
- Multi-link / per-audience tokens (promote `share_token` to its own table)
- Comments / reactions on walkthroughs
- Embed support (oEmbed-style)
- Video poster frames, chapter markers, thumbnails
- Signed Drive URLs for video (approach B in the spec) — only if Cloud Run egress becomes a measurable cost
- Auto-upload mode from `/canopy:walkthrough`
- Browser drag-drop upload UI at `/walkthroughs` (currently CLI-only)
- Multi-tenant scoping of walkthrough list (today: any dimagi user sees all walkthroughs)
```

- [ ] **Step 6: Build + commit**

Run: `cd frontend && npm run build`
Expected: build succeeds.

```bash
git add frontend/src/pages/ProjectsPage.tsx frontend/src/api/projects.ts CLAUDE.md TODOS.md
git commit -m "feat(walkthroughs): project tile link + docs + deferred TODOs"
```

---

## Task 14: End-to-end manual smoke

Goal: validate the whole flow once against a local dev instance before declaring done. Real Drive integration is exercised by the manual test; pytest covers the rest.

**Prereqs:** A Drive service-account JSON and a writeable shared-drive folder. If you don't have one, set `WALKTHROUGHS_ENABLED=False` in `.env` and skip to Step 5 — the unit tests already covered the wiring.

- [ ] **Step 1: Configure .env**

Add to `.env`:

```
WALKTHROUGHS_ENABLED=True
CANOPY_DRIVE_SA_KEY_JSON=<paste single-line JSON>
CANOPY_DRIVE_ROOT_FOLDER_ID=<folder id>
```

- [ ] **Step 2: Start dev servers**

Run: `uv run honcho start -f Procfile.dev`
Expected: backend at `http://localhost:8000`, frontend at the configured port.

- [ ] **Step 3: Upload via curl**

Run:

```bash
curl -X POST http://localhost:8000/api/auth/e2e-login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"ace@dimagi.com","token":"<CANOPY_E2E_AUTH_TOKEN>"}' \
  -c /tmp/canopy-cookies.txt

curl -X POST http://localhost:8000/api/walkthroughs/ \
  -b /tmp/canopy-cookies.txt \
  -F 'file=@/path/to/your/walkthrough.html' \
  -F 'title=Smoke Test' \
  -F 'kind=html' \
  -F 'visibility=link'
```

Expected: 201 with a JSON body containing `id` and `share_token`.

- [ ] **Step 4: View in browser**

- Open `http://localhost:8000/walkthroughs` → see the new row.
- Click into it → renders the HTML slideshow in the iframe.
- Click "Copy share link" → paste in an Incognito window → renders without login.
- Click "Rotate token" → old Incognito URL now 404s.
- Click "Delete" → row gone; Drive file gone (verify via Drive UI).

- [ ] **Step 5: Repeat for an MP4**

Upload a small `.mp4` with `kind=video`. Confirm `<video controls>` plays, and that seeking mid-video works (Range request).

- [ ] **Step 6: Full test suite + lint**

Run: `uv run pytest -v`
Run: `cd frontend && npm run build`
Run: `uv run ruff check apps/walkthroughs tests/test_walkthroughs_*.py tests/fixtures`
Expected: all clean.

- [ ] **Step 7: Final commit (if any cleanup)**

If any small tweaks were needed during smoke (likely none), commit them:

```bash
git add -A
git commit -m "chore(walkthroughs): post-smoke cleanup"
```

---

## Post-merge follow-ups (not part of this plan)

These are tracked here for the next session, not in TODOS.md (they're concrete next-step actions, not deferred features).

1. **Canopy plugin work** (separate repo):
   - New skill `canopy:walkthrough-share` (auto-detects html/mp4, inlines HTML assets, POSTs multipart).
   - Edit existing `canopy:walkthrough` to add the post-run "upload?" prompt.
   - Extend `canopy:setup` to write `canopy_web_url` + `upload_token` to `~/.canopy/config`.
2. **Deployment**:
   - Create the Shared Drive folder "canopy-web walkthroughs".
   - Generate (or reuse) a Google service-account JSON, store in 1Password.
   - Add `CANOPY_DRIVE_SA_KEY_JSON`, `CANOPY_DRIVE_ROOT_FOLDER_ID` to Cloud Run env via `./deploy.sh` flow.
   - Update `docs/deploy.md` with the prereqs section.

---

## Self-review notes (this section is for the planner; engineers can ignore)

- **Spec coverage:** All §1-§7 mapped to tasks. §6 deployment is in Post-merge follow-ups (not codable).
- **Auth refinement:** Plan deliberately swaps `CANOPY_WALKTHROUGH_UPLOAD_TOKEN` for the existing e2e-login path. Documented at top.
- **Types consistent:** `Walkthrough.KIND_*` / `VISIBILITY_*` constants used throughout. `WalkthroughListItem`/`Detail` TS types mirror serializer fields.
- **Test fake parity:** `FakeDriveClient` implements the same four `DriveClient` methods used by the production client.
- **No placeholders:** Each step shows code or commands. Where the existing file structure must be read first (project-tile layout, AppLayout nav, middleware classification), the plan explicitly says "read the file first" and shows the diff fragment to add.
