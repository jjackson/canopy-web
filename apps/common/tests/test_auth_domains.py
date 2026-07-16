"""Tests for the multi-domain email allowlist helper."""
from __future__ import annotations


from apps.common.auth_domains import allowed_email_domains, email_in_allowlist


def test_single_domain(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com"
    assert allowed_email_domains() == ["dimagi.com"]
    assert email_in_allowlist("ace@dimagi.com")
    assert not email_in_allowlist("ace@dimagi-ai.com")


def test_multi_domain_comma_separated(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com,dimagi-ai.com"
    assert allowed_email_domains() == ["dimagi.com", "dimagi-ai.com"]
    assert email_in_allowlist("ace@dimagi.com")
    assert email_in_allowlist("ace@dimagi-ai.com")
    assert not email_in_allowlist("outsider@example.com")


def test_whitespace_tolerance(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = " dimagi.com , dimagi-ai.com "
    assert allowed_email_domains() == ["dimagi.com", "dimagi-ai.com"]
    assert email_in_allowlist("ace@dimagi-ai.com")


def test_case_insensitive(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "Dimagi.com"
    assert email_in_allowlist("ACE@DIMAGI.COM")


def test_empty_allowlist_admits_anything(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = ""
    assert allowed_email_domains() == []
    assert email_in_allowlist("anyone@anywhere.com")


def test_unset_allowlist_admits_anything(settings):
    delattr(settings, "AUTH_ALLOWED_EMAIL_DOMAIN")
    assert allowed_email_domains() == []
    assert email_in_allowlist("anyone@anywhere.com")


def test_drops_empty_segments(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com,,dimagi-ai.com,"
    assert allowed_email_domains() == ["dimagi.com", "dimagi-ai.com"]
