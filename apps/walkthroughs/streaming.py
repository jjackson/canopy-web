"""Streaming endpoint for the public walkthrough viewer.

Preserved as a bare Django view (NOT ported to Ninja) — HTTP Range +
token-based public-link auth don't fit cleanly into Ninja's contract.

Mounted at /w/<uuid:wid>/content in config/urls.py.
"""
from __future__ import annotations

import re

from django.conf import settings
from django.http import Http404, HttpResponse, StreamingHttpResponse

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


def walkthrough_content(request, wid):
    """GET /w/<id>/content — stream the file bytes from Drive.

    Auth: caller is the authenticated owner OR visibility=link with a
    valid ?t=<share_token>. Mismatch returns 404 (don't leak existence
    of private walkthroughs).
    """
    if not getattr(settings, "WALKTHROUGHS_ENABLED", True):
        raise Http404("walkthroughs disabled")

    w = _get_or_404(wid)
    if w is None:
        raise Http404("walkthrough not found")

    token = request.GET.get("t", "")
    is_authed = request.user.is_authenticated
    token_ok = (
        w.visibility == Walkthrough.VISIBILITY_LINK
        and bool(w.share_token)
        and token == w.share_token
    )
    if not (is_authed or token_ok):
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
