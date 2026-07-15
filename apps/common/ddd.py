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


#: Gates whose reviews hang off the RUN, not the narrative timeline. These carry no
#: narrative_slug and no narrative version, they never render as a version row, and
#: they may ATTACH to a narrative but never CREATE one (``apps.runs.aggregate``).
#:
#: This lives here, beside the slug derivation, for the same reason that does: both
#: ``apps.reviews`` (which assigns the slug) and ``apps.runs`` (which groups by it)
#: must agree, and a disagreement is invisible until a phantom narrative shows up in
#: the rail. ``apps.runs`` cannot import it from ``apps.reviews.api`` without dragging
#: in a Ninja router.
#:
#: NOT the same set as ``aggregate._NON_NARRATIVE_GATES``, and the difference is load-
#: bearing: ``external_release`` is not a *version* of a narrative but does belong to
#: one (it approves publishing it). ``product_findings`` belongs to no narrative at all.
RUN_CHILD_GATES = ("product_findings",)


def is_run_child_gate(gate: str | None) -> bool:
    """True for a review that hangs off the run rather than the narrative."""
    return (gate or "") in RUN_CHILD_GATES
