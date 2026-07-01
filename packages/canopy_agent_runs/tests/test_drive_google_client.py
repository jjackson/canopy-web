"""Unit tests for the real `GoogleDriveClient` — method *shaping* against a
MOCKED google service (no SDK auth, no network).

We bypass ``__init__`` (which would build a real discovery service) via
``object.__new__`` and inject a ``MagicMock`` as ``_service``, then assert each
method translates the Drive REST response shapes into the canopy read-model
dataclasses and calls the API with the expected arguments. This is the
deploy-time contract that lets ``DriveRunStore`` run against live Drive.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from canopy_agent_runs.drive.client import ChangesPage, DriveFile, FileContent
from canopy_agent_runs.drive.google_client import GoogleDriveClient

FOLDER_MIME = "application/vnd.google-apps.folder"


def _client_with_service() -> tuple[GoogleDriveClient, MagicMock]:
    """A GoogleDriveClient whose `_service` is a MagicMock (no SDK build)."""
    client = object.__new__(GoogleDriveClient)
    service = MagicMock()
    client._service = service
    return client, service


def _set_list_response(service: MagicMock, response: dict) -> None:
    service.files.return_value.list.return_value.execute.return_value = response


def test_list_folder_shapes_files_and_folders():
    client, service = _client_with_service()
    _set_list_response(
        service,
        {
            "files": [
                {
                    "id": "f1", "name": "run_state.yaml",
                    "mimeType": "application/x-yaml",
                    "webViewLink": "https://drive/f1", "size": "42",
                    "modifiedTime": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "d1", "name": "1-design", "mimeType": FOLDER_MIME,
                    "webViewLink": "https://drive/d1",
                },
            ]
        },
    )

    files = client.list_folder("root")

    assert [f.name for f in files] == ["run_state.yaml", "1-design"]
    yaml_file = files[0]
    assert isinstance(yaml_file, DriveFile)
    assert yaml_file.id == "f1"
    assert yaml_file.size_bytes == 42
    assert yaml_file.path == "run_state.yaml"
    assert files[1].mime_type == FOLDER_MIME
    assert files[1].size_bytes is None  # no size on the folder

    # Non-recursive list passes the trashed=false parent query.
    _, kwargs = service.files.return_value.list.call_args
    assert kwargs["q"] == "'root' in parents and trashed = false"
    assert kwargs["supportsAllDrives"] is True


def test_list_files_recursive_descends_into_subfolders():
    client, service = _client_with_service()
    # First call: root has a folder + a file. Second call (into the folder):
    # one file. Third+ calls: empty (defensive).
    responses = [
        {
            "files": [
                {"id": "d1", "name": "1-design", "mimeType": FOLDER_MIME,
                 "webViewLink": ""},
                {"id": "f1", "name": "idea.md", "mimeType": "text/markdown",
                 "webViewLink": ""},
            ]
        },
        {
            "files": [
                {"id": "f2", "name": "pdd.md", "mimeType": "text/markdown",
                 "webViewLink": ""},
            ]
        },
        {"files": []},
    ]
    service.files.return_value.list.return_value.execute.side_effect = responses

    files = client.list_files("root", recursive=True)

    # Folder itself is not emitted when recursing; its file carries the path.
    by_path = {f.path: f for f in files}
    assert "idea.md" in by_path
    assert "1-design/pdd.md" in by_path
    assert by_path["1-design/pdd.md"].id == "f2"


def test_get_content_text_file_decodes_utf8():
    client, service = _client_with_service()
    service.files.return_value.get_media.return_value.execute.return_value = (
        b"hello: world\n"
    )

    content = client.get_content("f1", "application/x-yaml")

    assert isinstance(content, FileContent)
    assert content.content == "hello: world\n"
    assert content.encoding is None


def test_get_content_binary_falls_back_to_base64():
    client, service = _client_with_service()
    raw = b"\xff\xfe\x00\x01"  # not valid utf-8
    service.files.return_value.get_media.return_value.execute.return_value = raw

    content = client.get_content("f1", "image/png")

    assert content.encoding == "base64"
    import base64
    assert base64.b64decode(content.content) == raw


def test_get_content_google_doc_exports_to_text():
    client, service = _client_with_service()
    service.files.return_value.export.return_value.execute.return_value = b"exported"

    content = client.get_content("doc1", "application/vnd.google-apps.document")

    assert content.content == "exported"
    assert content.content_type == "text/plain"
    _, kwargs = service.files.return_value.export.call_args
    assert kwargs["mimeType"] == "text/plain"


def test_create_folder_posts_folder_mime_and_returns_id():
    client, service = _client_with_service()
    service.files.return_value.create.return_value.execute.return_value = {"id": "new"}

    new_id = client.create_folder("parent", "runs")

    assert new_id == "new"
    _, kwargs = service.files.return_value.create.call_args
    assert kwargs["body"]["mimeType"] == FOLDER_MIME
    assert kwargs["body"]["parents"] == ["parent"]


def test_upload_file_creates_with_media_and_returns_id():
    client, service = _client_with_service()
    service.files.return_value.create.return_value.execute.return_value = {"id": "fid"}

    fid = client.upload_file("parent", "decisions.yaml", "decisions: []\n", "application/x-yaml")

    assert fid == "fid"
    _, kwargs = service.files.return_value.create.call_args
    assert kwargs["body"]["name"] == "decisions.yaml"
    assert kwargs["media_body"] is not None


def test_update_file_replaces_content():
    client, service = _client_with_service()
    service.files.return_value.update.return_value.execute.return_value = {}

    client.update_file("fid", "x: 1\n", "application/x-yaml")

    _, kwargs = service.files.return_value.update.call_args
    assert kwargs["fileId"] == "fid"
    assert kwargs["media_body"] is not None


def test_copy_file_renames_and_returns_new_id():
    client, service = _client_with_service()
    service.files.return_value.copy.return_value.execute.return_value = {"id": "copy"}

    new_id = client.copy_file("src", "dest", "pdd.md")

    assert new_id == "copy"
    _, kwargs = service.files.return_value.copy.call_args
    assert kwargs["fileId"] == "src"
    assert kwargs["body"]["parents"] == ["dest"]
    assert kwargs["body"]["name"] == "pdd.md"


def test_trash_folder_sets_trashed_true():
    client, service = _client_with_service()
    service.files.return_value.update.return_value.execute.return_value = {}

    client.trash_folder("fid")

    _, kwargs = service.files.return_value.update.call_args
    assert kwargs["body"] == {"trashed": True}


def test_get_changes_start_page_token():
    client, service = _client_with_service()
    service.changes.return_value.getStartPageToken.return_value.execute.return_value = {
        "startPageToken": "tok-1"
    }

    assert client.get_changes_start_page_token() == "tok-1"


def test_list_changes_collects_ids_and_next_token():
    client, service = _client_with_service()
    service.changes.return_value.list.return_value.execute.return_value = {
        "changes": [
            {"fileId": "a"}, {"fileId": "b"}, {"removed": True},  # no fileId
        ],
        "newStartPageToken": "tok-2",
    }

    page = client.list_changes("tok-1")

    assert isinstance(page, ChangesPage)
    assert page.changed_file_ids == {"a", "b"}
    assert page.next_page_token == "tok-2"
    assert page.expired is False


def test_list_changes_410_returns_expired():
    from googleapiclient.errors import HttpError

    client, service = _client_with_service()
    resp = type("Resp", (), {"status": 410, "reason": "Gone"})()
    service.changes.return_value.list.return_value.execute.side_effect = HttpError(
        resp, b"gone"
    )

    page = client.list_changes("stale-token")

    assert page.expired is True
    assert page.changed_file_ids == set()
    assert page.next_page_token == ""
