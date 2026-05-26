"""REST endpoints for walkthroughs."""
from __future__ import annotations

from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from . import storage
from .drive_client import DriveNotConfigured
from .models import Walkthrough
from .serializers import (
    WalkthroughDetailSerializer,
    WalkthroughListItemSerializer,
    WalkthroughUpdateSerializer,
)

KIND_BY_EXTENSION = {".html": "html", ".htm": "html", ".mp4": "video"}
CONTENT_TYPE_BY_KIND = {"html": "text/html", "video": "video/mp4"}


def _require_enabled():
    if not getattr(settings, "WALKTHROUGHS_ENABLED", True):
        raise Http404("walkthroughs disabled")


@api_view(["GET", "POST"])
def walkthroughs_list_or_create(request):
    _require_enabled()
    start_timing()

    if request.method == "POST":
        return _upload(request)
    return _list(request)


def _upload(request):
    upload = request.FILES.get("file")
    if upload is None:
        return Response(
            error_response("VALIDATION_ERROR", "file is required"),
            status=status.HTTP_400_BAD_REQUEST,
        )

    title = (request.data.get("title") or "").strip() or upload.name
    kind = (request.data.get("kind") or "").strip().lower()
    if kind not in CONTENT_TYPE_BY_KIND:
        return Response(
            error_response(
                "VALIDATION_ERROR",
                f"kind must be one of: {sorted(CONTENT_TYPE_BY_KIND)}",
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    max_bytes = getattr(settings, "WALKTHROUGH_MAX_UPLOAD_BYTES", 75 * 1024 * 1024)
    if upload.size > max_bytes:
        return Response(
            error_response(
                "PAYLOAD_TOO_LARGE",
                f"upload exceeds {max_bytes} bytes",
            ),
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    project_slug = (request.data.get("project_slug") or "").strip() or None
    description = (request.data.get("description") or "").strip()
    visibility_raw = (request.data.get("visibility") or "").strip().lower()
    visibility = (
        Walkthrough.VISIBILITY_LINK
        if visibility_raw == Walkthrough.VISIBILITY_LINK
        else Walkthrough.VISIBILITY_PRIVATE
    )

    content_type = CONTENT_TYPE_BY_KIND[kind]
    data = upload.read()

    # Create row first so we have the UUID for the folder name. If the
    # Drive write fails we delete the row in the same request — no
    # orphan metadata.
    w = Walkthrough.objects.create(
        title=title[:200],
        description=description,
        kind=kind,
        project_slug=project_slug,
        owner=request.user,
        visibility=visibility,
        drive_file_id="",
        drive_folder_id="",
        content_type=content_type,
        size_bytes=len(data),
    )
    try:
        stored = storage.store_upload(
            walkthrough_id=str(w.id),
            filename=("slideshow.html" if kind == "html" else "video.mp4"),
            content_type=content_type,
            data=data,
        )
    except DriveNotConfigured as e:
        w.delete()
        return Response(
            error_response("drive-not-configured", str(e)),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception as e:
        w.delete()
        return Response(
            error_response("drive-upload-failed", str(e)),
            status=status.HTTP_502_BAD_GATEWAY,
        )

    w.drive_file_id = stored.file_id
    w.drive_folder_id = stored.folder_id
    w.save(update_fields=["drive_file_id", "drive_folder_id", "updated_at"])
    if visibility == Walkthrough.VISIBILITY_LINK:
        w.ensure_share_token()

    body = WalkthroughDetailSerializer(w).data
    body["is_owner"] = True
    return Response(success_response(body), status=status.HTTP_201_CREATED)


def _list(request):
    qs = Walkthrough.objects.all()
    project = request.query_params.get("project")
    if project:
        qs = qs.filter(project_slug=project)
    kind = request.query_params.get("kind")
    if kind in (Walkthrough.KIND_HTML, Walkthrough.KIND_VIDEO):
        qs = qs.filter(kind=kind)
    if request.query_params.get("mine") == "true" and request.user.is_authenticated:
        qs = qs.filter(owner=request.user)
    data = WalkthroughListItemSerializer(qs, many=True).data
    return Response(success_response(data))


# ---- Detail / Patch / Delete ----

def _get_or_404(wid):
    try:
        return Walkthrough.objects.get(pk=wid)
    except (Walkthrough.DoesNotExist, ValueError):
        return None


def _serialize_detail(w, *, is_owner: bool):
    data = WalkthroughDetailSerializer(w).data
    data["is_owner"] = is_owner
    if not is_owner:
        data["share_token"] = None
    return data


@api_view(["GET", "PATCH", "DELETE"])
def walkthrough_detail(request, wid):
    _require_enabled()
    start_timing()
    w = _get_or_404(wid)
    if w is None:
        return Response(
            error_response("NOT_FOUND", "walkthrough not found"),
            status=status.HTTP_404_NOT_FOUND,
        )

    is_owner = request.user.is_authenticated and w.owner_id == request.user.id

    if request.method == "GET":
        return Response(success_response(_serialize_detail(w, is_owner=is_owner)))

    # Mutations require owner.
    if not is_owner:
        return Response(
            error_response("FORBIDDEN", "owner only"),
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "DELETE":
        if w.drive_file_id:
            try:
                storage.delete_stored(file_id=w.drive_file_id, folder_id=w.drive_folder_id)
            except DriveNotConfigured:
                # Without Drive configured we can't clean Drive, but we
                # should still drop the row so the UI matches reality.
                pass
            except Exception:
                # Log and continue — orphan Drive files are recoverable;
                # an orphan row would block the user from re-deleting.
                pass
        w.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    serializer = WalkthroughUpdateSerializer(w, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    w.refresh_from_db()
    if w.visibility == Walkthrough.VISIBILITY_LINK and not w.share_token:
        w.ensure_share_token()
    return Response(success_response(_serialize_detail(w, is_owner=True)))


# ---- Rotate token ----

@api_view(["POST"])
def walkthrough_rotate_token(request, wid):
    _require_enabled()
    start_timing()
    w = _get_or_404(wid)
    if w is None:
        return Response(
            error_response("NOT_FOUND", "walkthrough not found"),
            status=status.HTTP_404_NOT_FOUND,
        )
    if not request.user.is_authenticated or w.owner_id != request.user.id:
        return Response(
            error_response("FORBIDDEN", "owner only"),
            status=status.HTTP_403_FORBIDDEN,
        )
    new_token = w.rotate_share_token()
    return Response(success_response({"share_token": new_token}))
