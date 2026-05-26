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
