"""Property-based contract tests: fuzz the OpenAPI spec against the running app.

Auto-generates a request for every (path × method) combination, hits the
endpoint, and asserts:
- response status matches one declared in the spec
- response body matches the declared response schema
- response content-type matches the spec

Auth-protected routes are skipped unless `SCHEMATHESIS_AUTH_COOKIE` is set
(populate via the e2e-login flow before running).

Run against a live backend:
    SCHEMATHESIS_SCHEMA_URL=http://localhost:8000/api/openapi.json \\
    SCHEMATHESIS_AUTH_COOKIE=<session-id> \\
    pytest tests/contract/
"""
from __future__ import annotations

import os

import pytest
import schemathesis

SCHEMA_URL = os.environ.get(
    "SCHEMATHESIS_SCHEMA_URL", "http://localhost:8000/api/openapi.json"
)
AUTH_COOKIE = os.environ.get("SCHEMATHESIS_AUTH_COOKIE")

# Load schema lazily so collection passes when no server is running.
try:
    schema = schemathesis.from_uri(SCHEMA_URL)
    _schema_available = True
except Exception:
    schema = None
    _schema_available = False

_parametrize = (
    schema.parametrize()
    if _schema_available
    else pytest.mark.skip(reason="No live backend — set SCHEMATHESIS_SCHEMA_URL")
)


@_parametrize
def test_api_conforms_to_schema(case):
    headers: dict[str, str] = {}
    cookies: dict[str, str] = {}
    if AUTH_COOKIE:
        cookies["sessionid"] = AUTH_COOKIE
    response = case.call(headers=headers, cookies=cookies)
    case.validate_response(response)
