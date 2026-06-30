"""Per-agent `RunStore` resolution — the one place that decides *where* an
agent's runs live.

The REST surface (`api.py`) is store-agnostic: it only ever calls `RunStore`
Protocol methods. This resolver is the single seam that maps an agent to its
backing store, so the Drive-backed path is a one-function decision here, not a
change scattered across the endpoints.

Selection (env-driven, minimal):

* If the agent's slug appears in ``settings.AGENT_RUNS_DRIVE_ROOTS`` (a
  ``{slug: drive_root_folder_id}`` map) AND Drive service-account credentials
  are configured, the agent is Drive-backed → ``DriveRunStore`` wrapping a live
  ``GoogleDriveClient`` rooted at that folder.
* Otherwise (the default for every canopy-hosted, DB-as-truth agent) →
  ``DbRunStore``.

Everything is read from settings; there is no DB migration. To point an agent
at Drive an operator sets the two env knobs (root map + SA key) and nothing
else. If the slug is mapped but creds are missing/invalid we log a warning and
fall back to the DB store rather than 500 the run surface — a half-configured
Drive deploy degrades to DB, it doesn't break.
"""
from __future__ import annotations

import logging

from django.conf import settings

from .stores import DbRunStore, RunStore

log = logging.getLogger(__name__)


def _drive_root_for(slug: str) -> str | None:
    """The configured Drive root folder id for ``slug``, or None if the agent
    isn't declared Drive-backed."""
    roots = getattr(settings, "AGENT_RUNS_DRIVE_ROOTS", {}) or {}
    if not isinstance(roots, dict):
        return None
    root = roots.get(slug)
    return root or None


def get_run_store(agent) -> RunStore:
    """Return the `RunStore` backing `agent`'s runs.

    `agent` is the `apps.agents.models.Agent` instance (endpoints resolve the
    slug → Agent once, then pass the object here). A bare slug string is also
    accepted defensively.

    Drive-backed when the agent's slug is mapped in
    ``settings.AGENT_RUNS_DRIVE_ROOTS`` and SA creds are configured; otherwise
    DB-as-truth (`DbRunStore`).
    """
    slug = getattr(agent, "slug", agent)
    root_folder_id = _drive_root_for(slug)
    if not root_folder_id:
        return DbRunStore()

    # Lazily import the Drive adapter + Google client so the DB path (and module
    # import) never pulls in the Drive store or the Google SDK shim.
    from .drive.google_client import (
        DriveNotConfigured,
        credentials_configured,
        get_google_drive_client,
    )
    from .drive.store import DriveRunStore

    if not credentials_configured():
        log.warning(
            "agent %r is mapped Drive-backed (root=%s) but no Drive SA "
            "credentials are configured; falling back to DbRunStore",
            slug, root_folder_id,
        )
        return DbRunStore()

    try:
        client = get_google_drive_client()
    except DriveNotConfigured as exc:
        log.warning(
            "agent %r is mapped Drive-backed but Drive creds failed to load "
            "(%s); falling back to DbRunStore", slug, exc,
        )
        return DbRunStore()

    return DriveRunStore(client, root_folder_id, agent_slug=slug)
