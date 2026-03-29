import json

import pytest
from django.test import Client

from apps.collections.models import Collection, Source


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def collection(db):
    return Collection.objects.create(
        name="Test Collection",
        description="A test collection of sources",
    )


class TestCollectionList:
    def test_create_collection(self, client, db):
        response = client.post(
            "/api/collections/",
            data=json.dumps({"name": "My Collection", "description": "Desc"}),
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["name"] == "My Collection"
        assert body["data"]["description"] == "Desc"
        assert "id" in body["data"]
        assert "timing_ms" in body

    def test_list_collections(self, client, collection):
        response = client.get("/api/collections/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "Test Collection"


class TestCollectionDetail:
    def test_get_collection_with_sources(self, client, collection):
        Source.objects.create(
            collection=collection,
            source_type="text",
            title="Source 1",
            content="Some content here",
        )
        response = client.get(f"/api/collections/{collection.pk}/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["name"] == "Test Collection"
        assert len(body["data"]["sources"]) == 1
        assert body["data"]["sources"][0]["title"] == "Source 1"

    def test_get_collection_not_found(self, client, db):
        response = client.get("/api/collections/9999/")
        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False


class TestAddSource:
    def test_add_source_to_collection(self, client, collection):
        response = client.post(
            f"/api/collections/{collection.pk}/sources/",
            data=json.dumps({
                "source_type": "text",
                "title": "New Source",
                "content": "This is source content.",
            }),
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["title"] == "New Source"
        assert body["data"]["content"] == "This is source content."
        assert Source.objects.filter(collection=collection).count() == 1

    def test_add_source_empty_content(self, client, collection):
        response = client.post(
            f"/api/collections/{collection.pk}/sources/",
            data=json.dumps({
                "source_type": "text",
                "title": "Empty",
                "content": "",
            }),
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False

    def test_add_source_whitespace_only_content(self, client, collection):
        response = client.post(
            f"/api/collections/{collection.pk}/sources/",
            data=json.dumps({
                "source_type": "text",
                "title": "Whitespace",
                "content": "   \n\t  ",
            }),
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False

    def test_add_source_exceeds_max_size(self, client, collection):
        large_content = "x" * 1_000_001
        response = client.post(
            f"/api/collections/{collection.pk}/sources/",
            data=json.dumps({
                "source_type": "text",
                "title": "Too Large",
                "content": large_content,
            }),
            content_type="application/json",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False

    def test_add_source_collection_not_found(self, client, db):
        response = client.post(
            "/api/collections/9999/sources/",
            data=json.dumps({
                "source_type": "text",
                "title": "Orphan",
                "content": "Some content",
            }),
            content_type="application/json",
        )
        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
