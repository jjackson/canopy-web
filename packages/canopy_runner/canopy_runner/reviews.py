"""Deterministic review-ingestion: turn a human-approved fleet review into harness turns.

Ada (the fleet conductor) posts a canopy-web review (`gate=product_findings`) whose
clusters each carry a `turns[]` routing block — the exact fields the harness needs:
`{target_agent, prompt, origin, origin_ref}`. Jonathan goes through the review in the
web UI and submits `implement | skip | defer` per cluster. This module is the runner's
side: it polls RESOLVED reviews and, for every cluster he decided `implement`, enqueues
the turn(s) Ada attached — routed to the right agent, with session-continuity context.

No LLM in the hot path — "approved cluster → its turns[]" is a fixed rule. Idempotency
is keyed `review-<review_id>-<cluster_id>-<i>`, so re-polling never double-enqueues and
never re-runs a finished turn. A local seen-set skips reviews already fully ingested.

Ada's clusters look like:
    {"id": "eva-first-turn", "title": "…", "severity": "high", "fix_kind": "mechanical",
     "suggested_fix": "…",
     "turns": [{"target_agent": "eva", "origin": "email", "prompt": "/eva:turn --thread <id>",
                "origin_ref": {"thread_id": "<id>", "subject": "…"}}]}
"""
from __future__ import annotations

import logging

logger = logging.getLogger("canopy_runner.reviews")

# The only review gate we ingest — the fleet-conductor findings surface. Other gates
# (DDD narrative review, etc.) are for humans only and never become fleet turns.
INGESTIBLE_GATE = "product_findings"
IMPLEMENT = "implement"


def check_reviews(client, *, seen: frozenset[str] = frozenset(), max_reviews: int = 25) -> dict:
    """Enqueue the turns for every `implement`-decided cluster in resolved, not-yet-seen
    reviews. Returns {"enqueued": [(review_id, cluster_id, agent), …],
                      "processed": {review_id, …}}  — review ids that were fully ingested
    (every implemented cluster had a routing block) and can be skipped next poll. A review
    with an implemented-but-unrouted cluster is left UNprocessed so a later Ada fix + a
    re-poll picks it up."""
    enqueued: list[tuple[str, str, str]] = []
    processed: set[str] = set()

    for row in (client.list_reviews(status="resolved") or [])[:max_reviews]:
        rid = str(row.get("id") or "")
        if not rid or rid in seen or row.get("gate") != INGESTIBLE_GATE:
            continue

        detail = client.get_review(rid) or {}
        req = detail.get("request_json") or {}
        resp = detail.get("response_json") or {}
        decisions = resp.get("decisions") or {}

        complete = True  # every implemented cluster had a routing block
        for cluster in req.get("clusters") or []:
            cid = cluster.get("id") or ""
            if (decisions.get(cid) or {}).get("decision") != IMPLEMENT:
                continue
            specs = cluster.get("turns") or []
            if not specs:
                complete = False
                logger.warning("review %s cluster '%s' was approved but has no turns[] "
                               "routing block — Ada must emit {target_agent, prompt, origin, "
                               "origin_ref}; skipping (will retry once fixed)", rid, cid)
                continue
            for i, spec in enumerate(specs):
                agent = (spec.get("target_agent") or "").strip()
                if not agent:
                    complete = False
                    logger.warning("review %s cluster '%s' turn #%d missing target_agent; "
                                   "skipping", rid, cid, i)
                    continue
                client.enqueue_turn(
                    agent,
                    spec.get("origin") or "api",
                    f"review-{rid}-{cid}-{i}",
                    prompt=spec.get("prompt") or f"/{agent}:turn",
                    origin_ref=spec.get("origin_ref") or {},
                )
                enqueued.append((rid, cid, agent))

        if complete:
            processed.add(rid)

    if enqueued:
        logger.info("reviews: enqueued %d turn(s) from %d review(s) — %s",
                    len(enqueued), len({e[0] for e in enqueued}),
                    ", ".join(f"{cid}->{agent}" for _, cid, agent in enqueued))
    return {"enqueued": enqueued, "processed": processed}
