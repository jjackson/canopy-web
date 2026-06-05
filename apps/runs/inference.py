"""Best-effort inference of a narrative slug + run_id from a walkthrough title.

Only used to backfill artifacts uploaded *before* the plugin sent run_id/narrative_slug
explicitly. Going forward those fields arrive on the upload, so this is a
one-time historical cleanup, not a runtime path.

Rules are intentionally simple and ordered (first match wins): narrower
narratives are checked before the catch-all ``microplans`` bucket.
"""
from __future__ import annotations

import re
from datetime import date

# A run "token": prefer an embedded run stamp, then an iteration/version marker,
# else the upload date — so a narrative's artifacts split into the runs they
# actually came from rather than collapsing into one.
_STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}-\d{3})")
_ITER = re.compile(r"\biter\s*(\d+)", re.IGNORECASE)
_VER = re.compile(r"\bv(\d+)\b", re.IGNORECASE)


def narrative_slug(title: str) -> str | None:
    """Map a walkthrough title to a narrative slug, or None if unclassifiable."""
    t = (title or "").lower()
    if "program admin report" in t:
        return "program-admin-report"
    if "demo-driven development" in t:
        return "demo-driven-development"
    if "left-rail" in t:
        return "microplans-left-rail"
    if "rooftop study" in t or "two-arm rooftop" in t:
        return "madobi-rooftop-study"
    if "opportunity" in t:
        return "microplan-to-opp"
    if "microplans" in t or "compare page" in t:
        return "microplans-10-wards"
    return None


def run_token(title: str, created: date) -> str:
    m = _STAMP.search(title or "")
    if m:
        return m.group(1)
    m = _ITER.search(title or "")
    if m:
        return f"iter{m.group(1)}"
    m = _VER.search(title or "")
    if m:
        return f"v{m.group(1)}"
    if "final" in (title or "").lower():
        return "final"
    return created.isoformat()


def infer(title: str, created: date) -> tuple[str, str] | None:
    """Return ``(feature_slug, run_id)`` for a title, or None if unclassifiable.

    ``run_id`` is ``"<slug>-<run_token>"`` so artifacts group into their runs.
    """
    slug = narrative_slug(title)
    if not slug:
        return None
    return slug, f"{slug}-{run_token(title, created)}"
