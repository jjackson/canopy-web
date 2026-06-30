"""Property-based contract tests: fuzz the OpenAPI spec against the running app.

Auto-generates a request for every (path × method) combination, hits the
endpoint, and asserts:
- response status matches one declared in the spec
- response body matches the declared response schema
- response content-type matches the spec

Auth-protected routes need `SCHEMATHESIS_AUTH_BEARER` (a raw Personal
Access Token). Mint one with:

    uv run python manage.py create_token --email ace@dimagi-ai.com \\
        --label schemathesis --create-user

Run against a live backend:
    SCHEMATHESIS_SCHEMA_URL=http://localhost:8000/api/openapi.json \\
    SCHEMATHESIS_AUTH_BEARER=<raw-pat> \\
    pytest tests/contract/
"""
from __future__ import annotations

import os

import pytest
import schemathesis
from hypothesis import HealthCheck, settings

# Per-endpoint example count. Schemathesis is property-based: each (path × method)
# runs `max_examples` generated requests. The default (100) × canopy-web's many
# endpoints made this a ~6-min blocker on every PR. So PRs run a fast smoke (a few
# examples each — still hits every endpoint and catches the contract breaks that
# matter: wrong status codes / schema mismatches), and the nightly job
# (.github/workflows/contract-nightly.yml) sets SCHEMATHESIS_MAX_EXAMPLES high for
# exhaustive fuzzing off the PR critical path.
_MAX_EXAMPLES = int(os.environ.get("SCHEMATHESIS_MAX_EXAMPLES", "6"))

SCHEMA_URL = os.environ.get(
    "SCHEMATHESIS_SCHEMA_URL", "http://localhost:8000/api/openapi.json"
)
AUTH_BEARER = os.environ.get("SCHEMATHESIS_AUTH_BEARER")

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
@settings(
    max_examples=_MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_api_conforms_to_schema(case):
    headers: dict[str, str] = {}
    if AUTH_BEARER:
        headers["Authorization"] = f"Bearer {AUTH_BEARER}"
    response = case.call(headers=headers)
    case.validate_response(response)
