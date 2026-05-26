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
