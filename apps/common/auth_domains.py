"""Allowed-email-domain helpers.

`AUTH_ALLOWED_EMAIL_DOMAIN` is a comma-separated list of allowed domains.
Single-value usage continues to work (no commas → list of 1). Empty value
disables the check (allow any domain).
"""
from __future__ import annotations

from django.conf import settings


def allowed_email_domains() -> list[str]:
    """Return the parsed list of allowed email domains, lowercased."""
    raw = (getattr(settings, "AUTH_ALLOWED_EMAIL_DOMAIN", "") or "").strip().lower()
    if not raw:
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


def email_in_allowlist(email: str) -> bool:
    """True if `email`'s domain matches one of the allowed entries.

    An empty allowlist short-circuits to True (matches the prior behavior
    when AUTH_ALLOWED_EMAIL_DOMAIN was unset or empty).
    """
    allowed = allowed_email_domains()
    if not allowed:
        return True
    _, _, domain = email.rpartition("@")
    return domain.lower() in allowed
