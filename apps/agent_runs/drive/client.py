"""canopy-web's own Drive client Protocol — the read+write surface the run
lifecycle needs to treat ACE's Drive run-folders as a `RunStore` backend.

This is the substrate for the (later-phase) `DriveRunStore`: a `RunStore`
impl that reads ACE's `ACE/<slug>/runs/<run-id>/` trees and returns the
storage-agnostic read model in `apps.agent_runs.schemas`.

Ported in shape from ace-web `apps/opps/drive_client.py`, but deliberately
narrower and SDK-free:

- It is a `typing.Protocol`, not an ABC, and imports **no** Google SDK. The
  real Google-backed implementation (and the retry/credentials plumbing)
  lives wherever the deploy wiring lands; this module only declares the
  interface so the lifecycle + tests depend on the contract, never on
  googleapiclient. The in-memory `FakeDriveClient`
  (`apps.agent_runs.tests.fixtures.fake_drive`) is the reference
  implementation the parity tests build run-folder trees in.
- FRAMEWORK tier: this app must not import any product app.

The interface is the minimal read+write set the lifecycle needs:

  read:    list_files, list_folder, get_file, get_content
  write:   create_folder, copy_file, update_file, trash_folder
  changes: get_changes_start_page_token, list_changes  (cache invalidation)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Drive's folder mime — handy shared constant for callers walking trees.
FOLDER_MIME = "application/vnd.google-apps.folder"


@dataclass
class DriveFile:
    """Metadata for one Drive file or folder.

    `path` is the slash-separated path from the listing root (set by the
    lister); the parsers match it against the artifact manifest. Folders
    carry `mime_type == FOLDER_MIME`.
    """

    id: str
    name: str
    mime_type: str
    web_view_link: str
    path: str = ""  # full slash-separated path from the listing root
    size_bytes: int | None = None
    modified_time: str | None = None  # ISO-8601 string, as returned by Drive
    parent_id: str | None = None  # immediate parent folder id (optional)
    drive_id: str | None = None  # shared-drive id; None for My Drive

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME


@dataclass
class FileContent:
    """The body of a Drive file. UTF-8 text for text files; base64 for binary."""

    content: str  # UTF-8 for text files; base64 for binary
    content_type: str = "text/plain"  # e.g. "text/markdown", "application/json"
    encoding: str | None = None  # "base64" for binary files


@dataclass
class ChangesPage:
    """One page of `drive.changes.list` results — the cache-invalidation hook.

    `changed_file_ids` is the set of file IDs whose state changed (created,
    modified, removed) since the input page token. `next_page_token` is the
    token to pass on the next `list_changes` call to fetch only what changed
    after this page; it is durable across calls and process restarts.

    `expired` is True when Drive returned 410 Gone on the input token —
    callers should treat caches scoped to this drive as invalid and re-seed
    via `get_changes_start_page_token`.
    """

    changed_file_ids: set[str]
    next_page_token: str
    expired: bool = False


@runtime_checkable
class DriveClient(Protocol):
    """The minimal Drive read+write interface the run lifecycle depends on.

    Structural — any object exposing these methods satisfies it (the
    in-memory `FakeDriveClient` and the real Google-backed client both do).
    No Google SDK is imported here.
    """

    # -- read surface --

    def list_files(
        self, folder_id: str, recursive: bool = False, page_size: int = 100
    ) -> list[DriveFile]:
        """List immediate children of a folder, or the full recursive tree.

        Each returned `DriveFile.path` is relative to `folder_id`.
        """
        ...

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        """List immediate children of a folder (non-recursive convenience alias)."""
        ...

    def get_file(self, file_id: str) -> DriveFile:
        """Fetch metadata for a single file or folder."""
        ...

    def get_content(self, file_id: str, mime_type: str) -> FileContent:
        """Fetch the body of a file. Google Docs types export to text; binary
        types are returned base64-encoded."""
        ...

    # -- write surface --

    def create_folder(self, parent_id: str, name: str) -> str:
        """Create a folder under `parent_id`. Returns the new folder ID."""
        ...

    def copy_file(
        self, file_id: str, new_parent_id: str, new_name: str | None = None
    ) -> str:
        """Copy a file to a new parent. Returns the new file ID."""
        ...

    def update_file(self, file_id: str, content: str, mime_type: str) -> None:
        """Replace the content of an existing file."""
        ...

    def trash_folder(self, folder_id: str) -> None:
        """Move a folder (and all descendants) to Drive trash (30-day recoverable)."""
        ...

    # -- changes feed (cache invalidation) --

    def get_changes_start_page_token(self, drive_id: str | None = None) -> str:
        """Return a fresh `pageToken` for `list_changes` from this point in time.

        Used when no token is stored yet, or after a 410 Gone forces a
        re-seed. Pass `drive_id` for a shared drive; None for My Drive.
        """
        ...

    def list_changes(
        self, page_token: str, *, drive_id: str | None = None
    ) -> ChangesPage:
        """Return one logical page of changes since `page_token`.

        On 410 Gone (token expired), returns a `ChangesPage` with
        `expired=True`, `changed_file_ids=set()`, `next_page_token=""` —
        callers should re-seed via `get_changes_start_page_token`.
        """
        ...
