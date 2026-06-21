"""End-to-end tests for the /api/system catalog router (auth + reader + schema)."""
from __future__ import annotations

import json

import pytest
from django.test import override_settings

from apps.system import reader


@pytest.fixture()
def plugin(tmp_path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": "1.2.3"}), encoding="utf-8"
    )
    s = tmp_path / "skills" / "ddd-run"
    s.mkdir(parents=True)
    (s / "SKILL.md").write_text(
        "---\nname: ddd-run\ndescription: Render + judge\n---\n\n# DDD Run\nThe body.",
        encoding="utf-8",
    )
    a = tmp_path / "agents"
    a.mkdir()
    (a / "echo.md").write_text("---\nname: echo\ndescription: An agent\n---\n\nBody.", encoding="utf-8")
    c = tmp_path / "commands"
    c.mkdir()
    (c / "brief.md").write_text("---\ndescription: A command\n---\n\nBody.", encoding="utf-8")
    reader.load_catalog.cache_clear()
    yield str(tmp_path)
    reader.load_catalog.cache_clear()


@pytest.fixture()
def authed_client(client, django_user_model):
    u = django_user_model.objects.create_user(
        username="dev", email="dev@dimagi.com", password="pw"
    )
    client.force_login(u)
    return client


@pytest.mark.django_db
def test_overview_requires_auth(client, plugin):
    with override_settings(CANOPY_PLUGIN_PATH=plugin):
        resp = client.get("/api/system/overview")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_overview_returns_catalog(authed_client, plugin):
    with override_settings(CANOPY_PLUGIN_PATH=plugin):
        resp = authed_client.get("/api/system/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["counts"] == {"skill": 1, "agent": 1, "command": 1}
    assert data["plugin_version"] == "1.2.3"
    names = {(i["kind"], i["name"]) for i in data["items"]}
    assert ("skill", "ddd-run") in names
    assert ("agent", "echo") in names
    assert ("command", "brief") in names
    # list shape carries no body
    assert "body" not in data["items"][0]


@pytest.mark.django_db
def test_detail_includes_body(authed_client, plugin):
    with override_settings(CANOPY_PLUGIN_PATH=plugin):
        resp = authed_client.get("/api/system/skill/ddd-run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Ddd Run"
    assert "The body." in data["body"]


@pytest.mark.django_db
def test_detail_unknown_kind_404(authed_client, plugin):
    with override_settings(CANOPY_PLUGIN_PATH=plugin):
        resp = authed_client.get("/api/system/bogus/ddd-run")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_detail_unknown_name_404(authed_client, plugin):
    with override_settings(CANOPY_PLUGIN_PATH=plugin):
        resp = authed_client.get("/api/system/skill/nope")
    assert resp.status_code == 404
