"""Upsert the django.contrib.sites Site row used by allauth."""
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Upsert the Site row with the given domain (used by allauth)."

    def add_arguments(self, parser):
        parser.add_argument("domain", help="Public host for this deployment, e.g. example.run.app")
        parser.add_argument("--name", default="Canopy", help="Display name for the Site")
        parser.add_argument("--pk", type=int, default=1, help="Site PK (matches SITE_ID setting)")

    def handle(self, *args, domain, name, pk, **options):
        site, created = Site.objects.update_or_create(
            pk=pk, defaults={"domain": domain, "name": name}
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} Site(pk={site.pk}, domain={site.domain}, name={site.name})"))
