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
