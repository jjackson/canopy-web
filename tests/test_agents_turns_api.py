"""API-level (ninja route) tests for the agent turns endpoints — reproduces the
live 500 the service-level tests missed."""
from __future__ import annotations

import pytest

from apps.agents import services
from apps.agents.models import Agent

pytestmark = pytest.mark.django_db


@pytest.fixture()
def authed_client(client, django_user_model):
    u = django_user_model.objects.create_user(username="dev", email="dev@dimagi.com", password="pw")
    client.force_login(u)
    return client


def _echo() -> Agent:
    from types import SimpleNamespace
    return services.upsert_agent(
        SimpleNamespace(slug="echo", name="Echo", description="", persona="", email="", avatar_url="")
    )


def test_list_turns_empty(authed_client):
    _echo()
    resp = authed_client.get("/api/agents/echo/turns/?limit=1")
    assert resp.status_code == 200, resp.content
    assert resp.json()["items"] == []


def test_post_then_list_turn(authed_client):
    _echo()
    resp = authed_client.post(
        "/api/agents/echo/turns/",
        data={"cli_session_id": "s1", "title": "Did a thing", "task_ext_ids": ["t1"],
              "work_product_urls": [], "source": "turn"},
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    resp2 = authed_client.get("/api/agents/echo/turns/?limit=10")
    assert resp2.status_code == 200, resp2.content
    assert resp2.json()["items"][0]["task_ext_ids"] == ["t1"]
