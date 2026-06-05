"""Shared DDD-run helpers.

A DDD run_id looks like ``"<narrative_slug>-YYYY-MM-DD-NNN"``. The *narrative_slug* (a.k.a.
the **narrative** slug) is everything before the trailing date+sequence stamp.
Both ``apps.reviews`` and ``apps.runs`` group by this, so the derivation lives
here to keep them in agreement.
"""
from __future__ import annotations

import re

# Trailing "-YYYY-MM-DD-NNN" stamp on a run_id.
_RUN_ID_STAMP = re.compile(r"-\d{4}-\d{2}-\d{2}-\d+$")


def narrative_slug_from_run_id(run_id: str) -> str:
    """``'microplans-study-design-2026-05-29-001'`` -> ``'microplans-study-design'``.

    Falls back to the raw run_id, then ``'(untitled)'``, so the result is always
    a non-empty grouping key.
    """
    base = _RUN_ID_STAMP.sub("", run_id or "").strip("-")
    return base or run_id or "(untitled)"
