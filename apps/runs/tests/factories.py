"""Tiny builders for runs-aggregation tests."""
from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.reviews.models import ReviewRequest
from apps.walkthroughs.models import Walkthrough

User = get_user_model()


def make_user(email="owner@dimagi.com"):
    return User.objects.get_or_create(username=email, defaults={"email": email})[0]


def make_walkthrough(owner, *, kind, run_id=None, narrative_slug=None, role=None, **kw):
    defaults = dict(
        title=kw.pop("title", f"{run_id or 'oneoff'}-{kind}"),
        kind=kind,
        owner=owner,
        run_id=run_id,
        narrative_slug=narrative_slug,
        role=role,
        project_slug=kw.pop("project_slug", None),
        links=kw.pop("links", []),
        content_type="video/mp4" if kind == "video" else "text/html",
        size_bytes=kw.pop("size_bytes", 123),
        duration_sec=kw.pop("duration_sec", None),
        drive_file_id="f1",
        drive_folder_id="d1",
        visibility=kw.pop("visibility", "private"),
    )
    defaults.update(kw)
    return Walkthrough.objects.create(**defaults)


def make_review(owner, *, run_id, gate="narrative-agreement", request_json=None, **kw):
    rj = request_json if request_json is not None else {"run_id": run_id, "gate": gate}
    return ReviewRequest.objects.create(
        owner=owner,
        run_id=run_id,
        gate=gate,
        request_json=rj,
        **kw,
    )
