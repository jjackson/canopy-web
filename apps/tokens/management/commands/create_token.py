"""Mint a Personal Access Token for a user.

Usage:
    uv run python manage.py create_token --email ace@dimagi-ai.com --label "smoke-script"

Prints the raw token to stdout. Capture it once — it isn't stored.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.tokens.models import PersonalToken


class Command(BaseCommand):
    help = "Mint a Personal Access Token for a user."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="User email address.")
        parser.add_argument("--label", required=True, help="Human-readable purpose for this token.")
        parser.add_argument(
            "--create-user",
            action="store_true",
            help="Create the user if they don't exist (useful for CI bootstrap).",
        )

    def handle(self, *args, **opts):
        email = opts["email"].strip().lower()
        label = opts["label"].strip()
        if not label:
            raise CommandError("--label cannot be empty")

        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=email).first()
        if user is None:
            if opts["create_user"]:
                user = user_model.objects.create_user(username=email, email=email)
                self.stdout.write(self.style.WARNING(f"Created user {email} (id={user.pk})"))
            else:
                raise CommandError(
                    f"No user with email {email!r}. Pass --create-user to create one."
                )

        raw, token = PersonalToken.create_for_user(user=user, label=label)
        self.stdout.write(self.style.SUCCESS(f"Minted token id={token.pk} for {user.email}"))
        self.stdout.write("")
        self.stdout.write("Capture this once — it's never stored on the server:")
        self.stdout.write("")
        self.stdout.write(raw)
