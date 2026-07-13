"""Streaming endpoint for the public walkthrough viewer.

Preserved as a bare Django view (NOT ported to Ninja) — HTTP Range support
(for ``<video>`` scrubbing) doesn't fit cleanly into Ninja's contract.

Mounted at /walkthrough/<uuid:wid>/content in config/urls.py (/w/ is now the
workspace tenant prefix).
"""
from __future__ import annotations

import re

from django.conf import settings
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from . import storage
from .drive_client import DriveNotConfigured
from .models import Walkthrough

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)$")


def _parse_range(header: str, total: int) -> tuple[int, int] | None:
    """Parse a single-range HTTP Range header. Multi-range not supported."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    start = int(m.group(1))
    end_raw = m.group(2)
    end = int(end_raw) if end_raw else total - 1
    if start > end or start >= total:
        return None
    return start, min(end, total - 1)


def _get_or_404(wid):
    try:
        return Walkthrough.objects.get(pk=wid)
    except (Walkthrough.DoesNotExist, ValueError):
        return None


@xframe_options_sameorigin
def walkthrough_content(request, wid):
    """GET /w/<id>/content — stream the file bytes from Drive.

    Auth: any authenticated session user OR a public (visibility=link)
    walkthrough presented with its ?t=<share_token>. Anything else 404s
    so existence isn't leaked.

    Django's SecurityMiddleware sets ``X-Frame-Options: DENY`` globally,
    which breaks our own viewer page (``/w/<id>``) when it tries to embed
    this endpoint via ``<iframe src=...>``. Override to ``SAMEORIGIN`` —
    the viewer is the only intended embedder and lives on the same host.
    """
    if not getattr(settings, "WALKTHROUGHS_ENABLED", True):
        raise Http404("walkthroughs disabled")

    w = _get_or_404(wid)
    if w is None:
        raise Http404("walkthrough not found")

    # Token-gated public access (spec 2026-07-13): anonymous read requires
    # visibility=link AND a matching ?t=<share_token>. Bare-UUID anonymous
    # access 404s exactly like private, so existence never leaks.
    if not (
        request.user.is_authenticated
        or w.token_matches(request.GET.get("t"))
    ):
        raise Http404("walkthrough not found")

    range_hdr = request.META.get("HTTP_RANGE", "")
    try:
        if range_hdr:
            # We need the total to clamp the range — do a tiny head download.
            _, _, _, total = storage.download(
                file_id=w.drive_file_id, start=0, end=0,
            )
            parsed = _parse_range(range_hdr, total)
            if parsed is None:
                resp = HttpResponse(status=416)
                resp["Content-Range"] = f"bytes */{total}"
                return resp
            start, end = parsed
            data, s, e, t = storage.download(
                file_id=w.drive_file_id, start=start, end=end,
            )
            resp = StreamingHttpResponse(
                iter([data]),
                status=206,
                content_type=w.content_type,
            )
            resp["Content-Range"] = f"bytes {s}-{e}/{t}"
            resp["Content-Length"] = str(len(data))
            resp["Accept-Ranges"] = "bytes"
            return resp

        data, s, e, t = storage.download(file_id=w.drive_file_id)
        resp = StreamingHttpResponse(
            iter([data]),
            status=200,
            content_type=w.content_type,
        )
        resp["Content-Length"] = str(len(data))
        resp["Accept-Ranges"] = "bytes"
        return resp
    except DriveNotConfigured:
        return HttpResponse(status=500)
    except Exception:
        return HttpResponse(status=502)
