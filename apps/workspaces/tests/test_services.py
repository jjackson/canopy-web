"""Tenancy service helpers: the default workspace + domain auto-join — the glue
that makes scoping non-breaking (existing + new domain users keep access)."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.workspaces import services
from apps.workspaces.models import WorkspaceMembership

pytestmark = pytest.mark.django_db
User = get_user_model()


def test_ensure_default_workspace_is_idempotent_and_domain_seeded(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com,dimagi-ai.com"
    su = User.objects.create(username="su", email="su@dimagi.com", is_superuser=True)
    ws = services.ensure_default_workspace()
    assert ws is not None
    assert ws.slug == services.DEFAULT_WORKSPACE_SLUG
    assert ws.created_by == su
    assert ws.auto_join_domains == ["dimagi.com", "dimagi-ai.com"]
    # owner is an owner-member; idempotent
    assert WorkspaceMembership.objects.get(workspace=ws, user=su).role == "owner"
    assert services.ensure_default_workspace().pk == ws.pk


def test_ensure_default_workspace_none_without_users():
    assert services.ensure_default_workspace() is None


def test_auto_join_adds_matching_domain_user_only(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com"
    User.objects.create(username="su", email="su@dimagi.com", is_superuser=True)
    services.ensure_default_workspace()

    insider = User.objects.create(username="i", email="i@dimagi.com")
    services.auto_join_workspaces(insider)
    assert WorkspaceMembership.objects.get(
        workspace_id=services.DEFAULT_WORKSPACE_SLUG, user=insider
    ).role == "editor"

    outsider = User.objects.create(username="o", email="o@other.com")
    services.auto_join_workspaces(outsider)
    assert not WorkspaceMembership.objects.filter(user=outsider).exists()


def test_user_workspace_slugs_and_is_member(settings):
    settings.AUTH_ALLOWED_EMAIL_DOMAIN = "dimagi.com"
    su = User.objects.create(username="su", email="su@dimagi.com", is_superuser=True)
    services.ensure_default_workspace()
    assert services.user_workspace_slugs(su) == {services.DEFAULT_WORKSPACE_SLUG}
    assert services.is_member(su, services.DEFAULT_WORKSPACE_SLUG) is True
    other = User.objects.create(username="x", email="x@other.com")
    assert services.user_workspace_slugs(other) == set()
    assert services.is_member(other, services.DEFAULT_WORKSPACE_SLUG) is False
