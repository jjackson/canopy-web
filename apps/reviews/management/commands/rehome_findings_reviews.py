"""Re-home legacy product_findings reviews off the narrative timeline.

Before the run-child fix, a ``product_findings`` review was created with a
``narrative_slug`` (derived from the run_id) and a monotonic ``version`` — so it
surfaced in the DDD shell as a bogus narrative-version row (e.g. "v3 CURRENT").

This command finds every ``gate=product_findings`` review that still carries a
``narrative_slug`` and/or a non-zero ``version`` and pins it to the run-child
shape (``narrative_slug=None``, ``version=0``). It does NOT delete the reviews —
the findings and any submitted decisions are preserved; only their placement in
the timeline changes. Dry-run by default; pass ``--apply`` to write.

    python manage.py rehome_findings_reviews            # preview
    python manage.py rehome_findings_reviews --apply     # write
    python manage.py rehome_findings_reviews --apply --run-id program-admin-report-2026-06-11-001
"""
from django.core.management.base import BaseCommand

from apps.reviews.models import ReviewRequest


class Command(BaseCommand):
    help = "Pin legacy product_findings reviews to the run-child shape (narrative_slug=None, version=0)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist changes (default: dry-run).")
        parser.add_argument("--run-id", default=None, help="Limit to a single run_id.")

    def handle(self, *args, **opts):
        qs = ReviewRequest.objects.filter(gate="product_findings")
        if opts["run_id"]:
            qs = qs.filter(run_id=opts["run_id"])
        # Only those still mis-placed on the narrative timeline.
        stale = qs.exclude(narrative_slug__isnull=True, version=0)

        n = stale.count()
        if not n:
            self.stdout.write(self.style.SUCCESS("No mis-placed product_findings reviews — nothing to do."))
            return

        for r in stale:
            self.stdout.write(
                f"  {r.id}  run={r.run_id}  narrative_slug={r.narrative_slug!r} version={r.version} -> None/0"
            )

        if not opts["apply"]:
            self.stdout.write(self.style.WARNING(f"DRY-RUN: {n} review(s) would be re-homed. Re-run with --apply."))
            return

        updated = stale.update(narrative_slug=None, version=0)
        self.stdout.write(self.style.SUCCESS(f"Re-homed {updated} product_findings review(s) to run-child shape."))
