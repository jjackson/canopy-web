"""Cascade deletes for the DDD aggregation surface.

A *narrative*/*version*/*run* is not a table — it's a grouping over
``ReviewRequest`` + ``Walkthrough`` rows (see ``aggregate.py``). Deleting one
therefore means deleting every row that rolls up under it, and best-effort
removing each walkthrough's rendered file from Drive (same cleanup the
single-walkthrough delete does in ``apps/walkthroughs/api.py``).

All three helpers return a small counts dict, or ``None`` when nothing matched
(the API layer turns ``None`` into a 404).
"""
from __future__ import annotations

import logging

from apps.reviews.models import ReviewRequest
from apps.walkthroughs import storage
from apps.walkthroughs.drive_client import DriveNotConfigured
from apps.walkthroughs.models import Walkthrough

from .aggregate import (
    _is_narrative_version,
    build_narrative,
    narrative_of_review,
    narrative_of_walkthrough,
)

logger = logging.getLogger(__name__)


def _drop_walkthrough(w: Walkthrough) -> None:
    """Best-effort Drive cleanup, then delete the row.

    Mirrors ``delete_walkthrough`` in ``apps/walkthroughs/api.py``: a missing or
    unconfigured Drive client means there's no orphan to clean up, so we still
    drop the row. Any other Drive error is logged but never blocks the delete —
    a stuck Drive file is better than a row we can't remove.
    """
    if w.drive_file_id:
        try:
            storage.delete_stored(file_id=w.drive_file_id, folder_id=w.drive_folder_id)
        except DriveNotConfigured:
            logger.warning(
                "ddd delete: drive not configured; dropping walkthrough %s without cleanup",
                w.id,
            )
        except Exception:  # noqa: BLE001 — never let Drive block the row delete
            logger.exception(
                "ddd delete: drive cleanup failed for walkthrough %s; dropping row anyway",
                w.id,
            )
    w.delete()


def delete_run(run_id: str) -> dict | None:
    """Delete a single run: every Walkthrough + ReviewRequest sharing ``run_id``."""
    wts = list(Walkthrough.objects.filter(run_id=run_id))
    revs = list(ReviewRequest.objects.filter(run_id=run_id))
    if not wts and not revs:
        return None
    for w in wts:
        _drop_walkthrough(w)
    n_rev = len(revs)
    for r in revs:
        r.delete()
    return {"run_id": run_id, "walkthroughs": len(wts), "reviews": n_rev}


def delete_version(slug: str, version: int) -> dict | None:
    """Delete one narrative version and the runs nested under it.

    Uses the same grouping the narrative page shows (``build_narrative``) so the
    blast radius matches exactly what the user saw under that version: its runs
    plus the version's own story review row(s).
    """
    data = build_narrative(slug)
    if data is None:
        return None
    vp = next((v for v in data["versions"] if v.get("version") == version), None)
    if vp is None:
        return None

    runs = 0
    for r in vp.get("runs", []):
        if delete_run(r["run_id"]) is not None:
            runs += 1

    # The version's story review(s) — these are not "runs", they ARE the version.
    version_revs = [
        r
        for r in ReviewRequest.objects.all()
        if narrative_of_review(r) == slug
        and _is_narrative_version(r)
        and r.version == version
    ]
    for r in version_revs:
        r.delete()

    return {"slug": slug, "version": version, "runs": runs, "reviews": len(version_revs)}


def delete_narrative(slug: str) -> dict | None:
    """Delete an entire narrative: every row (all versions + all runs) for ``slug``."""
    wts = [w for w in Walkthrough.objects.all() if narrative_of_walkthrough(w) == slug]
    revs = [r for r in ReviewRequest.objects.all() if narrative_of_review(r) == slug]
    if not wts and not revs:
        return None
    for w in wts:
        _drop_walkthrough(w)
    n_rev = len(revs)
    for r in revs:
        r.delete()
    return {"slug": slug, "walkthroughs": len(wts), "reviews": n_rev}
