"""Tests for the Drive client + fake fixture."""
import pytest
from django.test import override_settings

from apps.walkthroughs import storage
from apps.walkthroughs.drive_client import DriveNotConfigured
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
