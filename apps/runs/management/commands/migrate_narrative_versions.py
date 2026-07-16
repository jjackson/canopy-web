"""Backfill the narrative/version model onto existing data.

Idempotent, DB-only (no Drive deletes — artifact cleanup goes through the API):

1. ``ReviewRequest.narrative_slug`` = the narrative slug (explicit, else from run_id).
2. ``ReviewRequest.version`` = monotonic per narrative_slug, narrative-version reviews
   (story-bearing, non-external_release) numbered 1..N by created_at; other
   reviews share the current version.
3. ``Walkthrough.narrative_review_id`` = the narrative_slug's current (latest) narrative
   version, for any run that isn't already stamped — so existing runs link to
   their story.

``--dry-run`` reports without writing.
"""
from __future__ import annotations

import collections

from django.core.management.base import BaseCommand

from apps.runs.ddd import narrative_slug_from_run_id
from apps.reviews.models import ReviewRequest
from apps.runs.aggregate import _is_narrative_version, narrative_of_review
from apps.walkthroughs.models import Walkthrough


class Command(BaseCommand):
    help = "Backfill ReviewRequest.narrative_slug/version and Walkthrough.narrative_review_id."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        reviews = list(ReviewRequest.objects.all())

        # 1 + 2: narrative_slug + version, per narrative.
        by_narrative_slug: dict[str, list[ReviewRequest]] = collections.defaultdict(list)
        for r in reviews:
            slug = narrative_of_review(r)
            by_narrative_slug[slug].append(r)

        rev_changed = 0
        # current (latest) narrative-version review id per narrative_slug, for stamping.
        current_version_id: dict[str, str] = {}
        for slug, revs in by_narrative_slug.items():
            revs.sort(key=lambda r: r.created_at)
            counter = 0
            latest_narr = None
            for r in revs:
                new_feature = slug
                if _is_narrative_version(r):
                    counter += 1
                    latest_narr = r
                new_version = counter or 1
                if r.narrative_slug != new_feature or r.version != new_version:
                    rev_changed += 1
                    if not dry:
                        r.narrative_slug = new_feature
                        r.version = new_version
                        r.save(update_fields=["narrative_slug", "version"])
            if latest_narr is not None:
                current_version_id[slug] = str(latest_narr.id)

        # 3: stamp walkthrough runs that aren't linked yet.
        wts = list(
            Walkthrough.objects.exclude(run_id__isnull=True).exclude(run_id="")
        )
        wt_changed = 0
        for w in wts:
            if w.narrative_review_id:
                continue
            slug = (w.narrative_slug or "").strip() or narrative_slug_from_run_id(w.run_id)
            rid = current_version_id.get(slug)
            if not rid:
                continue
            wt_changed += 1
            if not dry:
                w.narrative_review_id = rid
                w.save(update_fields=["narrative_review_id", "updated_at"])

        verb = "would update" if dry else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"narrative versions: {verb} {rev_changed} review(s), "
                f"stamped {wt_changed} walkthrough(s)."
            )
        )
