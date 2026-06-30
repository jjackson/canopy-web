"""Tests for the run-store resolver — the db-vs-drive selection seam.

No live creds, no SDK auth: we drive selection purely through settings and a
patched `get_google_drive_client`.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings

from apps.agent_runs.resolver import get_run_store
from apps.agent_runs.stores import DbRunStore
from canopy_runs.drive.google_client import DriveNotConfigured
from canopy_runs.drive.store import DriveRunStore


class _Agent:
    def __init__(self, slug: str):
        self.slug = slug


@override_settings(AGENT_RUNS_DRIVE_ROOTS={})
def test_unmapped_agent_resolves_to_db_store():
    assert isinstance(get_run_store(_Agent("ace")), DbRunStore)


@override_settings(
    AGENT_RUNS_DRIVE_ROOTS={"ace": "root-123"},
    AGENT_RUNS_DRIVE_SA_KEY_JSON="",
    AGENT_RUNS_DRIVE_SA_KEY_PATH="",
    CANOPY_DRIVE_SA_KEY_JSON="",
)
def test_mapped_but_no_creds_falls_back_to_db_store():
    # Mapped Drive-backed, but no SA credentials configured anywhere → DB.
    assert isinstance(get_run_store(_Agent("ace")), DbRunStore)


@override_settings(
    AGENT_RUNS_DRIVE_ROOTS={"ace": "root-123"},
    AGENT_RUNS_DRIVE_SA_KEY_JSON='{"x": "y"}',
)
def test_mapped_with_creds_resolves_to_drive_store():
    sentinel_client = object()
    with patch(
        "canopy_runs.drive.google_client.get_google_drive_client",
        return_value=sentinel_client,
    ):
        store = get_run_store(_Agent("ace"))

    assert isinstance(store, DriveRunStore)
    assert store.client is sentinel_client
    assert store.root_folder_id == "root-123"
    assert store.agent_slug == "ace"


@override_settings(
    AGENT_RUNS_DRIVE_ROOTS={"ace": "root-123"},
    AGENT_RUNS_DRIVE_SA_KEY_JSON='{"x": "y"}',
)
def test_mapped_with_creds_but_load_fails_falls_back_to_db_store():
    with patch(
        "canopy_runs.drive.google_client.get_google_drive_client",
        side_effect=DriveNotConfigured("boom"),
    ):
        store = get_run_store(_Agent("ace"))

    assert isinstance(store, DbRunStore)


@override_settings(
    AGENT_RUNS_DRIVE_ROOTS={"ace": "root-123"},
    AGENT_RUNS_DRIVE_SA_KEY_JSON="",
)
def test_other_agent_not_in_map_uses_db_store_even_when_one_is_drive_backed():
    assert isinstance(get_run_store(_Agent("echo")), DbRunStore)


@override_settings(
    AGENT_RUNS_DRIVE_ROOTS={"ace": "root-123"},
    AGENT_RUNS_DRIVE_SA_KEY_JSON='{"x": "y"}',
)
def test_bare_slug_string_is_accepted():
    sentinel_client = object()
    with patch(
        "canopy_runs.drive.google_client.get_google_drive_client",
        return_value=sentinel_client,
    ):
        store = get_run_store("ace")
    assert isinstance(store, DriveRunStore)
    assert store.agent_slug == "ace"
