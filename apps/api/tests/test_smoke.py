import pytest
from django.test import Client


@pytest.mark.django_db
def test_openapi_schema_serves():
    client = Client()
    response = client.get("/api/v2/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "canopy-web API"
    assert payload["openapi"].startswith("3.1")


@pytest.mark.django_db
def test_unknown_route_returns_404():
    """Unmatched paths under /api/v2/ resolve to 404. The response shape
    depends on whether Django's URLconf or Ninja's dispatch fires first.
    A content-type assertion is intentionally omitted; a routing-level
    catchall for problem+json is deferred to Phase 0.4 or later.
    """
    client = Client()
    response = client.get("/api/v2/does-not-exist")
    assert response.status_code == 404


@pytest.mark.django_db
def test_scalar_docs_serves_html():
    client = Client()
    response = client.get("/api/v2/docs/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert b"api-reference" in response.content


@pytest.mark.django_db
def test_redoc_docs_serves_html():
    client = Client()
    response = client.get("/api/v2/redoc/")
    assert response.status_code == 200
    assert b"redoc" in response.content
