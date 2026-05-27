"""Contract tests for the v2 collections Ninja surface.

Covers:
- Auth: 401 for anonymous, expected status for authenticated.
- Status codes: 201 create, 200 detail, 404 not-found.
- Round-trip: response bodies validate through the corresponding Pydantic schema.
- Validation: empty name → 422, empty/oversize content → 422.
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.collections.models import Collection, Source
from apps.collections.schemas import CollectionOut, SourceOut

User = get_user_model()

BASE = "/api/v2/collections"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(username="alice", email="alice@dimagi.com"):
    return User.objects.create_user(username=username, email=email, password="pw")


def _auth_client(user=None):
    c = Client()
    if user is None:
        user = _make_user()
    c.force_login(user)
    return c


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


# ---------------------------------------------------------------------------
# create_collection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_collection_returns_201_and_typed_payload():
    c = _auth_client()
    resp = _post_json(c, f"{BASE}/", {"name": "X"})
    assert resp.status_code == 201
    CollectionOut.model_validate(resp.json())


@pytest.mark.django_db
def test_create_collection_validates_name():
    """Empty name should yield 422 + problem+json."""
    c = _auth_client()
    resp = _post_json(c, f"{BASE}/", {"name": ""})
    assert resp.status_code == 422
    body = resp.json()
    assert "type" in body


# ---------------------------------------------------------------------------
# get_collection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_collection_detail_includes_sources():
    user = _make_user()
    c = _auth_client(user)
    collection = Collection.objects.create(name="Test Collection")
    Source.objects.create(
        collection=collection,
        source_type="text",
        title="First",
        content="hello",
    )
    Source.objects.create(
        collection=collection,
        source_type="document",
        title="Second",
        content="world",
    )
    resp = c.get(f"{BASE}/{collection.pk}/")
    assert resp.status_code == 200
    body = resp.json()
    out = CollectionOut.model_validate(body)
    assert len(out.sources) == 2
    # order_by created_at — first source should be "First"
    assert out.sources[0].title == "First"
    assert out.sources[1].title == "Second"


@pytest.mark.django_db
def test_get_collection_404():
    c = _auth_client()
    resp = c.get(f"{BASE}/999999/")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("type", "").endswith("/not-found")


# ---------------------------------------------------------------------------
# add_source
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_add_source_returns_201():
    user = _make_user()
    c = _auth_client(user)
    collection = Collection.objects.create(name="My Coll")
    resp = _post_json(
        c,
        f"{BASE}/{collection.pk}/sources/",
        {"source_type": "text", "content": "hello"},
    )
    assert resp.status_code == 201
    SourceOut.model_validate(resp.json())


@pytest.mark.django_db
def test_add_source_rejects_empty_content():
    user = _make_user()
    c = _auth_client(user)
    collection = Collection.objects.create(name="My Coll")
    resp = _post_json(
        c,
        f"{BASE}/{collection.pk}/sources/",
        {"source_type": "text", "content": ""},
    )
    assert resp.status_code == 422


@pytest.mark.django_db
def test_add_source_rejects_oversize_content():
    user = _make_user()
    c = _auth_client(user)
    collection = Collection.objects.create(name="My Coll")
    resp = _post_json(
        c,
        f"{BASE}/{collection.pk}/sources/",
        {"source_type": "text", "content": "x" * 1_000_001},
    )
    assert resp.status_code == 422


@pytest.mark.django_db
def test_add_source_to_missing_collection_404():
    c = _auth_client()
    resp = _post_json(
        c,
        f"{BASE}/999999/sources/",
        {"source_type": "text", "content": "hello"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("type", "").endswith("/not-found")


# ---------------------------------------------------------------------------
# Auth: anonymous → 401
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_401():
    collection = Collection.objects.create(name="Secret")
    anon = Client()
    resp = anon.get(f"{BASE}/{collection.pk}/")
    assert resp.status_code == 401
    body = resp.json()
    assert body.get("type", "").endswith("/auth")
