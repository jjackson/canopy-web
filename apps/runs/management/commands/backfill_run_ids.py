"""Backfill ``run_id`` / ``narrative_slug`` on walkthroughs uploaded before the DDD
upload contract (which now sends both explicitly).

Two passes, in priority order:

1. **Authoritative** — a ``ReviewRequest`` whose ``request_json.video`` points
   at a walkthrough via ``walkthrough_id`` pins that walkthrough to the review's
   ``run_id``.
2. **Title inference** — for everything still unstamped, infer a narrative slug
   + run_id from the title (see ``apps/runs/inference.py``). This produces the
   real multiple-runs-per-narrative shape from human-authored titles.

Idempotent: never overwrites a non-null ``run_id``. ``--dry-run`` prints the
full plan (grouped by narrative) without writing.
"""
from __future__ import annotations

import collections

from django.core.management.base import BaseCommand

from apps.common.ddd import narrative_slug_from_run_id
from apps.reviews.models import ReviewRequest
from apps.runs.inference import infer
from apps.walkthroughs.models import Walkthrough


class Command(BaseCommand):
    help = "Infer run_id/narrative_slug for walkthroughs uploaded before the DDD contract."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Print the plan without writing."
        )

    def handle(self, *args, **opts):
        dry = opts["dry_run"]

        # walkthrough_id -> (run_id, narrative_slug, source)
        planned: dict[str, tuple[str, str, str]] = {}

        # 1. Authoritative: review.request_json.video.walkthrough_id
        for r in ReviewRequest.objects.all():
            rj = r.request_json if isinstance(r.request_json, dict) else {}
            video = rj.get("video") or {}
            wid = video.get("walkthrough_id") if isinstance(video, dict) else None
            if not wid:
                continue
            w = Walkthrough.objects.filter(pk=wid).first()
            if w is None or w.run_id:
                continue
            planned[str(w.id)] = (r.run_id, narrative_slug_from_run_id(r.run_id), "review")

        # 2. Title inference for the rest.
        for w in Walkthrough.objects.filter(run_id__isnull=True):
            if str(w.id) in planned:
                continue
            result = infer(w.title, w.created_at.date())
            if result is None:
                self.stdout.write(f"  [skip — unclassifiable] {w.id} :: {w.title}")
                continue
            narrative_slug, run_id = result
            planned[str(w.id)] = (run_id, narrative_slug, "title")

        if not planned:
            self.stdout.write("Nothing to backfill.")
            return

        # Group the plan by narrative for a readable summary.
        by_narrative_slug: dict[str, set[str]] = collections.defaultdict(set)
        for _wid, (run_id, narrative_slug, _src) in planned.items():
            by_narrative_slug[narrative_slug].add(run_id)

        self.stdout.write("Plan (narrative -> runs -> artifacts):")
        for narrative_slug in sorted(by_narrative_slug):
            runs = by_narrative_slug[narrative_slug]
            n_art = sum(
                1 for v in planned.values() if v[1] == narrative_slug
            )
            self.stdout.write(f"  {narrative_slug}: {len(runs)} run(s), {n_art} artifact(s)")
            for rid in sorted(runs):
                arts = [wid for wid, v in planned.items() if v[0] == rid]
                self.stdout.write(f"      {rid}  ({len(arts)})")

        if dry:
            self.stdout.write(self.style.WARNING(f"[dry-run] {len(planned)} walkthrough(s) would change. No writes."))
            return

        written = 0
        for wid, (run_id, narrative_slug, _src) in planned.items():
            w = Walkthrough.objects.get(pk=wid)
            fields = []
            if run_id and not w.run_id:
                w.run_id = run_id
                fields.append("run_id")
            if narrative_slug and not w.narrative_slug:
                w.narrative_slug = narrative_slug
                fields.append("narrative_slug")
            if fields:
                w.save(update_fields=[*fields, "updated_at"])
                written += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {written} walkthrough(s)."))
