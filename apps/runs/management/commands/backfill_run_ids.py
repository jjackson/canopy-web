"""Backfill ``run_id`` / ``feature`` on existing walkthroughs.

Pre-dates the DDD-run upload contract, so artifacts uploaded before the plugin
started sending ``run_id`` need grouping inferred:

1. Authoritative — every ``ReviewRequest`` may reference its rendered video via
   ``request_json.video.walkthrough_id``. If that walkthrough has no run_id,
   stamp it from the review's run_id.
2. Heuristic (opt-in, ``--from-titles``) — match walkthroughs whose title starts
   with a known narrative slug (derived from review run_ids).

Idempotent: never overwrites a non-null run_id. ``--dry-run`` prints the plan
without writing.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.common.ddd import feature_from_run_id
from apps.reviews.models import ReviewRequest
from apps.walkthroughs.models import Walkthrough


class Command(BaseCommand):
    help = "Infer run_id/feature for walkthroughs uploaded before the DDD contract."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing.",
        )
        parser.add_argument(
            "--from-titles",
            action="store_true",
            help="Also match walkthroughs by title-prefix against known narrative slugs.",
        )

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        from_titles = opts["from_titles"]

        planned: dict[str, tuple[str, str]] = {}  # walkthrough_id -> (run_id, feature)

        # 1. Authoritative — review.request_json.video.walkthrough_id
        for r in ReviewRequest.objects.all():
            rj = r.request_json if isinstance(r.request_json, dict) else {}
            video = rj.get("video") or {}
            wid = video.get("walkthrough_id") if isinstance(video, dict) else None
            if not wid:
                continue
            w = Walkthrough.objects.filter(pk=wid).first()
            if w is None or w.run_id:
                continue
            planned[str(w.id)] = (r.run_id, feature_from_run_id(r.run_id))

        # 2. Heuristic — title prefix against known narrative slugs.
        if from_titles:
            slugs = {
                feature_from_run_id(rid)
                for rid in ReviewRequest.objects.values_list("run_id", flat=True)
            }
            for w in Walkthrough.objects.filter(run_id__isnull=True):
                if str(w.id) in planned:
                    continue
                title = (w.title or "").lower()
                match = next(
                    (s for s in slugs if s and title.startswith(s.lower())), None
                )
                if match:
                    # No run_id known from a title alone — group under the
                    # narrative via feature, leave run_id null so it doesn't
                    # masquerade as a specific run.
                    planned[str(w.id)] = ("", match)

        if not planned:
            self.stdout.write("Nothing to backfill.")
            return

        for wid, (run_id, feature) in planned.items():
            label = f"  {wid} -> run_id={run_id or '(none)'} feature={feature}"
            if dry:
                self.stdout.write(f"[dry-run]{label}")
                continue
            w = Walkthrough.objects.get(pk=wid)
            fields = []
            if run_id and not w.run_id:
                w.run_id = run_id
                fields.append("run_id")
            if feature and not w.feature:
                w.feature = feature
                fields.append("feature")
            if fields:
                w.save(update_fields=[*fields, "updated_at"])
                self.stdout.write(label)

        verb = "Would update" if dry else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {len(planned)} walkthrough(s)."))
