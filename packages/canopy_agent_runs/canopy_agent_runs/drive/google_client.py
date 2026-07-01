"""The real Google-backed `DriveClient` for the agent-run Drive adapter.

This is the deploy-only half of the Drive path: a concrete implementation of
the `DriveClient` Protocol (`canopy_agent_runs.drive.client`) that talks to the live
Google Drive v3 API. `DriveRunStore` is written against the Protocol, so
swapping `FakeDriveClient` for this in production is a one-line change at the
composition root (canopy-web's `apps.agent_runs.resolver`).

Ported in shape from ace-web `apps/opps/drive_client.py` (the SDK calls, the
Changes API, the content get/put, the transient-error retry).

SDK import discipline (the load-bearing constraint): the Google SDK
(`googleapiclient`, `google.oauth2`) is imported **lazily**, inside `__init__`
and the methods that need it — NEVER at module top level. Importing this module
therefore requires no SDK and touches no network, which keeps the package
import-clean and lets the unit tests mock the service object without installing
or stubbing the SDK. Install the SDK via the package's `drive` extra
(`pip install "canopy-agent-runs[drive]"`).

DJANGO-FREE: this module reads no `django.conf.settings`. Credential SOURCES
(inline SA JSON / SA key path / a fallback JSON) are passed in as explicit
parameters; the composition root (a Django settings reader, an env reader,
whatever the host app uses) resolves them and calls in. That is the seam that
keeps the package portable across canopy-web and ace-web.
"""
from __future__ import annotations

import base64
import functools
import json
import logging
import random
import time

from .client import ChangesPage, DriveFile, FileContent

log = logging.getLogger(__name__)

FOLDER_MIME = "application/vnd.google-apps.folder"

# Scope the SA needs to read+write run folders.
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

# Drive 5xx + 429 are transient; reads are idempotent so retrying is safe.
# Writes are intentionally NOT wrapped — a duplicate create/upload on retry
# could leak Drive resources (a second run folder, a duplicate decisions.yaml).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.5  # seconds; effective ~0.5s, 1.0s, 2.0s + jitter


class DriveNotConfigured(RuntimeError):
    """Raised when no agent-run Drive service-account credentials are set."""


def _drive_retry(method):
    """Retry the wrapped Drive read on transient HttpError 5xx/429.

    Three attempts with exponential backoff + jitter. Non-retryable statuses
    (and non-HttpError exceptions) propagate immediately. `HttpError` is
    imported lazily so the module stays SDK-free at import time.
    """

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
                    "drive_retry: %s attempt %d/%d failed status=%s; sleeping %.2fs",
                    method.__name__, attempt, _RETRY_ATTEMPTS, status, delay,
                )
                time.sleep(delay)
                last_exc = exc
        if last_exc is not None:  # pragma: no cover - loop returns or raises
            raise last_exc
        raise RuntimeError("drive_retry: exhausted attempts without exception")

    return _wrapped


class GoogleDriveClient:
    """Real Google Drive v3 client — structurally satisfies `DriveClient`.

    Construct with already-built Google credentials, or via the
    `get_google_drive_client()` factory which builds them from passed-in SA key
    sources. Beyond the minimal Protocol it also exposes `upload_file` (a NEW-file
    write) because `DriveRunStore` calls it (via `getattr`) to create
    `decisions.yaml` and synthesize a fork's `run_state.yaml`.
    """

    FOLDER_MIME = FOLDER_MIME

    def __init__(self, credentials):
        from googleapiclient.discovery import build  # noqa: PLC0415

        # cache_discovery=False avoids a noisy warning in containers where the
        # discovery cache dir isn't writable.
        self._service = build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )

    # -- read surface --

    @_drive_retry
    def list_files(
        self, folder_id: str, recursive: bool = False, page_size: int = 100
    ) -> list[DriveFile]:
        results: list[DriveFile] = []
        self._list_folder(
            folder_id, path="", results=results, recursive=recursive,
            page_size=page_size,
        )
        return results

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        return self.list_files(folder_id, recursive=False)

    def _list_folder(
        self, folder_id: str, path: str, results: list, recursive: bool, page_size: int
    ):
        page_token = None
        while True:
            response = self._service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields=(
                    "nextPageToken, "
                    "files(id, name, mimeType, webViewLink, size, modifiedTime, driveId)"
                ),
                pageSize=page_size,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            for f in response.get("files", []):
                file_path = f"{path}/{f['name']}" if path else f["name"]
                if f["mimeType"] == FOLDER_MIME and recursive:
                    self._list_folder(f["id"], file_path, results, True, page_size)
                else:
                    results.append(self._to_drive_file(f, file_path))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    @staticmethod
    def _to_drive_file(f: dict, path: str) -> DriveFile:
        size = f.get("size")
        return DriveFile(
            id=f["id"],
            name=f["name"],
            mime_type=f["mimeType"],
            web_view_link=f.get("webViewLink", ""),
            path=path,
            size_bytes=int(size) if size is not None else None,
            modified_time=f.get("modifiedTime"),
            drive_id=f.get("driveId") or None,
        )

    @_drive_retry
    def get_file(self, file_id: str) -> DriveFile:
        f = self._service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, webViewLink, size, modifiedTime, driveId",
            supportsAllDrives=True,
        ).execute()
        return self._to_drive_file(f, path=f["name"])

    @_drive_retry
    def get_content(self, file_id: str, mime_type: str) -> FileContent:
        export_map = {
            "application/vnd.google-apps.document": ("text/plain", "text/plain"),
            "application/vnd.google-apps.spreadsheet": ("text/csv", "text/csv"),
            "application/vnd.google-apps.presentation": ("text/plain", "text/plain"),
        }
        if mime_type in export_map:
            export_mime, content_type = export_map[mime_type]
            content = self._service.files().export(
                fileId=file_id, mimeType=export_mime
            ).execute()
            text = content.decode("utf-8") if isinstance(content, bytes) else content
            return FileContent(content=text, content_type=content_type)

        # Regular file download.
        content = self._service.files().get_media(fileId=file_id).execute()
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
                return FileContent(content=text, content_type=mime_type)
            except UnicodeDecodeError:
                return FileContent(
                    content=base64.b64encode(content).decode("ascii"),
                    content_type=mime_type,
                    encoding="base64",
                )
        return FileContent(content=content, content_type=mime_type)

    # -- write surface --

    def create_folder(self, parent_id: str, name: str) -> str:
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        resp = self._service.files().create(
            body=body, fields="id", supportsAllDrives=True
        ).execute()
        return resp["id"]

    def upload_file(
        self, parent_id: str, name: str, content: str, mime_type: str
    ) -> str:
        """Create a NEW file under `parent_id`. Beyond the minimal Protocol,
        but `DriveRunStore` needs it to write decisions.yaml / run_state.yaml."""
        from googleapiclient.http import MediaInMemoryUpload  # noqa: PLC0415

        body = {"name": name, "parents": [parent_id]}
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type)
        resp = self._service.files().create(
            body=body, media_body=media, fields="id", supportsAllDrives=True
        ).execute()
        return resp["id"]

    def update_file(self, file_id: str, content: str, mime_type: str) -> None:
        from googleapiclient.http import MediaInMemoryUpload  # noqa: PLC0415

        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type)
        self._service.files().update(
            fileId=file_id, media_body=media, supportsAllDrives=True
        ).execute()

    def copy_file(
        self, file_id: str, new_parent_id: str, new_name: str | None = None
    ) -> str:
        body: dict = {"parents": [new_parent_id]}
        if new_name:
            body["name"] = new_name
        resp = self._service.files().copy(
            fileId=file_id, body=body, fields="id", supportsAllDrives=True
        ).execute()
        return resp["id"]

    def trash_folder(self, folder_id: str) -> None:
        self._service.files().update(
            fileId=folder_id,
            body={"trashed": True},
            supportsAllDrives=True,
        ).execute()

    # -- changes feed (cache invalidation) --

    @_drive_retry
    def get_changes_start_page_token(self, drive_id: str | None = None) -> str:
        kwargs: dict = {"supportsAllDrives": True}
        if drive_id:
            kwargs["driveId"] = drive_id
        resp = self._service.changes().getStartPageToken(**kwargs).execute()
        return resp["startPageToken"]

    @_drive_retry
    def list_changes(
        self, page_token: str, *, drive_id: str | None = None
    ) -> ChangesPage:
        from googleapiclient.errors import HttpError  # noqa: PLC0415

        changed: set[str] = set()
        token = page_token
        try:
            while True:
                kwargs: dict = {
                    "pageToken": token,
                    "fields": "newStartPageToken,nextPageToken,changes(fileId,removed)",
                    "supportsAllDrives": True,
                    "includeItemsFromAllDrives": True,
                    "pageSize": 1000,
                    "spaces": "drive",
                }
                if drive_id:
                    kwargs["driveId"] = drive_id
                resp = self._service.changes().list(**kwargs).execute()
                for c in resp.get("changes", []):
                    fid = c.get("fileId")
                    if fid:
                        changed.add(fid)
                next_token = resp.get("nextPageToken")
                if next_token:
                    token = next_token
                    continue
                return ChangesPage(
                    changed_file_ids=changed,
                    next_page_token=resp.get("newStartPageToken", token),
                    expired=False,
                )
        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status in (410, "410"):
                return ChangesPage(
                    changed_file_ids=set(), next_page_token="", expired=True
                )
            raise


# ---------------------------------------------------------------------------
# Credential factory (Django-free — sources are passed in, not read from settings)
# ---------------------------------------------------------------------------
def credentials_configured(
    *, sa_key_json: str = "", sa_key_path: str = "", fallback_json: str = ""
) -> bool:
    """True when *some* SA credential source is set (cheap, no SDK import).

    The composition root passes the three candidate sources it resolved (from
    Django settings / env / etc.); this function just reports whether any is
    non-empty. Keeping the predicate here (rather than in the host app) means
    the resolution PRECEDENCE lives in one place: `load_credentials`.
    """
    return bool((sa_key_json or "") or (sa_key_path or "") or (fallback_json or ""))


def load_credentials(
    *, sa_key_json: str = "", sa_key_path: str = "", fallback_json: str = ""
):
    """Build Google SA credentials from explicit sources (lazy SDK import).

    Resolution order (first non-empty wins):
      1. ``sa_key_json`` — inline service-account JSON.
      2. ``sa_key_path`` — path to a service-account JSON file.
      3. ``fallback_json`` — a fallback inline JSON (e.g. a shared Drive SA the
         host already configured for another feature).

    Raises ``DriveNotConfigured`` when none are set/valid.
    """
    from google.oauth2 import service_account  # noqa: PLC0415

    inline = sa_key_json or ""
    path = sa_key_path or ""
    fallback = fallback_json or ""

    if inline:
        try:
            info = json.loads(inline)
        except json.JSONDecodeError as e:
            raise DriveNotConfigured(f"invalid JSON in inline SA key: {e}") from e
        return service_account.Credentials.from_service_account_info(
            info, scopes=DRIVE_SCOPES
        )
    if path:
        return service_account.Credentials.from_service_account_file(
            path, scopes=DRIVE_SCOPES
        )
    if fallback:
        try:
            info = json.loads(fallback)
        except json.JSONDecodeError as e:
            raise DriveNotConfigured(f"invalid JSON in fallback SA key: {e}") from e
        return service_account.Credentials.from_service_account_info(
            info, scopes=DRIVE_SCOPES
        )
    raise DriveNotConfigured(
        "no agent-run Drive credentials configured "
        "(pass sa_key_json / sa_key_path / fallback_json)"
    )


def get_google_drive_client(
    *, sa_key_json: str = "", sa_key_path: str = "", fallback_json: str = ""
) -> GoogleDriveClient:
    """Return a live `GoogleDriveClient` built from the passed-in SA key sources.

    Raises `DriveNotConfigured` if no credentials are set."""
    return GoogleDriveClient(
        load_credentials(
            sa_key_json=sa_key_json, sa_key_path=sa_key_path, fallback_json=fallback_json
        )
    )
