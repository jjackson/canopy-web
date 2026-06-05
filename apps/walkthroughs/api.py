"""Django Ninja v2 router for the walkthroughs surface."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from django.conf import settings
from django.http import Http404, HttpRequest
from pydantic import ValidationError

log = logging.getLogger(__name__)
from ninja import File, Form, Router, Status
from ninja.files import UploadedFile

from apps.api.auth import session_auth
from apps.api.errors import (
    TYPE_CONFLICT,
    TYPE_DRIVE_NOT_CONFIGURED,
    TYPE_DRIVE_UPLOAD_FAILED,
    TYPE_FORBIDDEN,
    TYPE_NOT_FOUND,
    TYPE_PAYLOAD_TOO_LARGE,
    ProblemError,
)

from apps.common.ddd import feature_from_run_id
from apps.runs.aggregate import has_narrative_version

from . import storage
from .drive_client import DriveNotConfigured
from .models import Walkthrough
from .schemas import (
    WalkthroughDetailOut,
    WalkthroughKind,
    WalkthroughLink,
    WalkthroughListItemOut,
    WalkthroughPatchIn,
    WalkthroughRotateTokenOut,
    WalkthroughVisibility,
)

router = Router(auth=session_auth, tags=["walkthroughs"])

CONTENT_TYPE_BY_KIND: dict[str, str] = {"html": "text/html", "video": "video/mp4"}
FILENAME_BY_KIND: dict[str, str] = {"html": "slideshow.html", "video": "video.mp4"}

# Terminal DDD package artifacts — the ones ddd-upload publishes. Uploading one
# without a narrative is what produces a "no narrative" package, so the server
# refuses it as a backstop to the plugin-side guard. Intermediate ddd-run
# artifacts (deck/clip) and non-DDD walkthrough-share uploads carry neither of
# these roles and are unaffected.
_NARRATIVE_REQUIRED_ROLES = {Walkthrough.ROLE_HERO_VIDEO, Walkthrough.ROLE_DOCS}


def _require_enabled() -> None:
    if not getattr(settings, "WALKTHROUGHS_ENABLED", True):
        raise Http404("walkthroughs disabled")


def _parse_links_field(raw: str) -> list[dict]:
    """Parse the multipart ``links`` form field (a JSON-encoded list).

    Each entry is validated against :class:`WalkthroughLink`. Returns a list
    of plain dicts ready to store on the JSONField. An empty/blank field
    yields ``[]``. Raises ProblemError(422) on malformed input so a buggy
    uploader fails loud rather than silently dropping the links.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProblemError(422, "Invalid links JSON", detail=str(exc))
    if not isinstance(parsed, list):
        raise ProblemError(422, "links must be a JSON list")
    try:
        return [WalkthroughLink.model_validate(item).model_dump() for item in parsed]
    except ValidationError as exc:
        raise ProblemError(422, "Invalid link entry", detail=str(exc))


def _detail_payload(w: Walkthrough, *, is_owner: bool) -> dict:
    return {
        "id": w.id,
        "title": w.title,
        "description": w.description,
        "kind": w.kind,
        "project_slug": w.project_slug,
        "visibility": w.visibility,
        "owner_email": w.owner.email,
        "size_bytes": w.size_bytes,
        "duration_sec": w.duration_sec,
        "share_token": w.share_token if is_owner else None,
        "content_type": w.content_type,
        "is_owner": is_owner,
        "links": w.links or [],
        "run_id": w.run_id,
        "feature": w.feature,
        "role": w.role,
        "created_at": w.created_at,
        "updated_at": w.updated_at,
    }


def _list_item_payload(w: Walkthrough) -> dict:
    return {
        "id": w.id,
        "title": w.title,
        "description": w.description,
        "kind": w.kind,
        "project_slug": w.project_slug,
        "visibility": w.visibility,
        "owner_email": w.owner.email,
        "size_bytes": w.size_bytes,
        "duration_sec": w.duration_sec,
        "run_id": w.run_id,
        "feature": w.feature,
        "role": w.role,
        "created_at": w.created_at,
        "updated_at": w.updated_at,
    }


def _get_or_404(wid: UUID) -> Walkthrough:
    w = Walkthrough.objects.filter(pk=wid).first()
    if w is None:
        raise ProblemError(404, "Walkthrough not found", type_=TYPE_NOT_FOUND)
    return w


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response={201: WalkthroughDetailOut},
    summary="Upload a walkthrough (multipart)",
)
def upload_walkthrough(
    request: HttpRequest,
    file: UploadedFile = File(...),
    title: str = Form(""),
    kind: WalkthroughKind = Form(...),
    project_slug: str = Form(""),
    description: str = Form(""),
    visibility: WalkthroughVisibility = Form("private"),
    links: str = Form(""),
    run_id: str = Form(""),
    feature: str = Form(""),
    role: str = Form(""),
    narrative_review_id: str = Form(""),
) -> Status:
    _require_enabled()

    max_bytes = getattr(settings, "WALKTHROUGH_MAX_UPLOAD_BYTES", 75 * 1024 * 1024)
    if file.size > max_bytes:
        raise ProblemError(
            413,
            "Payload too large",
            type_=TYPE_PAYLOAD_TOO_LARGE,
            detail=f"Upload exceeds {max_bytes} bytes.",
        )

    resolved_title = (title.strip() or file.name or "untitled")[:200]
    resolved_project_slug = project_slug.strip() or None
    resolved_description = description.strip()
    resolved_links = _parse_links_field(links)
    content_type = CONTENT_TYPE_BY_KIND[kind]
    filename = FILENAME_BY_KIND[kind]
    data = file.read()

    # DDD-run grouping (optional). feature defaults to the narrative slug
    # derived from run_id when the uploader didn't send one explicitly.
    resolved_run_id = run_id.strip() or None
    resolved_feature = feature.strip() or None
    if resolved_run_id and not resolved_feature:
        resolved_feature = feature_from_run_id(resolved_run_id)
    resolved_role = role.strip() or None
    # The narrative version (ReviewRequest.id) this run rendered. Ignore a
    # malformed value rather than 500 — it's optional grouping metadata.
    resolved_review_id = None
    if narrative_review_id.strip():
        try:
            resolved_review_id = UUID(narrative_review_id.strip())
        except ValueError:
            resolved_review_id = None

    # Backstop guard: refuse to publish a terminal DDD package artifact
    # (hero_video / docs) for a narrative that has no story-bearing version —
    # such a package renders as "no narrative". A supplied narrative_review_id is
    # proof the narrative gate ran, so it's trusted and skips the check. Mirrors
    # the plugin-side guard in scripts/ddd/upload.py so the rule holds even for
    # older plugin versions or manual uploads.
    if (
        resolved_role in _NARRATIVE_REQUIRED_ROLES
        and resolved_feature
        and resolved_review_id is None
        and not has_narrative_version(resolved_feature)
    ):
        raise ProblemError(
            409,
            "Narrative required",
            type_=TYPE_CONFLICT,
            detail=(
                f"Refusing to publish a {resolved_role!r} artifact for narrative "
                f"{resolved_feature!r}: it has no narrative version, so the run "
                f"would render as \"no narrative\". Run the ddd-narrative-review "
                f"gate for this run first, then re-upload."
            ),
        )

    # Create ORM row first — if Drive fails, delete to avoid orphan row.
    w = Walkthrough.objects.create(
        title=resolved_title,
        description=resolved_description,
        kind=kind,
        project_slug=resolved_project_slug,
        owner=request.user,
        visibility=visibility,
        links=resolved_links,
        run_id=resolved_run_id,
        feature=resolved_feature,
        role=resolved_role,
        narrative_review_id=resolved_review_id,
        drive_file_id="",
        drive_folder_id="",
        content_type=content_type,
        size_bytes=len(data),
    )

    try:
        stored = storage.store_upload(
            walkthrough_id=str(w.id),
            filename=filename,
            content_type=content_type,
            data=data,
        )
    except DriveNotConfigured as exc:
        w.delete()
        raise ProblemError(
            500,
            "Drive not configured",
            type_=TYPE_DRIVE_NOT_CONFIGURED,
            detail=str(exc),
        )
    except Exception as exc:
        w.delete()
        raise ProblemError(
            502,
            "Drive upload failed",
            type_=TYPE_DRIVE_UPLOAD_FAILED,
            detail=str(exc),
        )

    w.drive_file_id = stored.file_id
    w.drive_folder_id = stored.folder_id
    w.save(update_fields=["drive_file_id", "drive_folder_id", "updated_at"])

    if visibility == Walkthrough.VISIBILITY_LINK:
        w.ensure_share_token()

    return Status(201, WalkthroughDetailOut.model_validate(_detail_payload(w, is_owner=True)))


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response=list[WalkthroughListItemOut],
    summary="List walkthroughs",
)
def list_walkthroughs(
    request: HttpRequest,
    project: str = "",
    kind: str = "",
    mine: str = "",
) -> list[WalkthroughListItemOut]:
    _require_enabled()

    qs = Walkthrough.objects.select_related("owner").all()
    if project:
        qs = qs.filter(project_slug=project)
    if kind in (Walkthrough.KIND_HTML, Walkthrough.KIND_VIDEO):
        qs = qs.filter(kind=kind)
    if mine == "true" and request.user.is_authenticated:
        qs = qs.filter(owner=request.user)

    return [
        WalkthroughListItemOut.model_validate(_list_item_payload(w)) for w in qs
    ]


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get(
    "/{wid}/",
    response=WalkthroughDetailOut,
    summary="Get walkthrough detail",
)
def get_walkthrough(request: HttpRequest, wid: UUID) -> WalkthroughDetailOut:
    _require_enabled()
    w = _get_or_404(wid)
    is_owner = request.user.is_authenticated and w.owner_id == request.user.id
    return WalkthroughDetailOut.model_validate(_detail_payload(w, is_owner=is_owner))


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------


@router.patch(
    "/{wid}/",
    response=WalkthroughDetailOut,
    summary="Update walkthrough (owner only)",
)
def patch_walkthrough(
    request: HttpRequest,
    wid: UUID,
    payload: WalkthroughPatchIn,
) -> WalkthroughDetailOut:
    _require_enabled()
    w = _get_or_404(wid)

    if not (request.user.is_authenticated and w.owner_id == request.user.id):
        raise ProblemError(403, "Forbidden — owner only", type_=TYPE_FORBIDDEN)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(w, field, value)
    w.save()
    w.refresh_from_db()

    if w.visibility == Walkthrough.VISIBILITY_LINK and not w.share_token:
        w.ensure_share_token()

    return WalkthroughDetailOut.model_validate(_detail_payload(w, is_owner=True))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{wid}/",
    response={204: None},
    summary="Delete walkthrough (owner only)",
)
def delete_walkthrough(request: HttpRequest, wid: UUID) -> Status:
    _require_enabled()
    w = _get_or_404(wid)

    if not (request.user.is_authenticated and w.owner_id == request.user.id):
        raise ProblemError(403, "Forbidden — owner only", type_=TYPE_FORBIDDEN)

    if w.drive_file_id:
        try:
            storage.delete_stored(file_id=w.drive_file_id, folder_id=w.drive_folder_id)
        except DriveNotConfigured:
            # No Drive client means no orphan to clean up — still drop the
            # row so the UI matches reality.
            log.warning(
                "delete_walkthrough: drive not configured; row dropped without "
                "Drive cleanup (walkthrough_id=%s)", w.id,
            )
        except Exception:
            # Don't block the row delete on a Drive hiccup — recovering an
            # orphan Drive file is cheap; an orphan DB row blocks the user
            # from re-deleting. But log loudly so we can sweep later.
            log.exception(
                "delete_walkthrough: drive cleanup failed (walkthrough_id=%s, "
                "drive_file_id=%s)", w.id, w.drive_file_id,
            )

    w.delete()
    return Status(204, None)


# ---------------------------------------------------------------------------
# Rotate token
# ---------------------------------------------------------------------------


@router.post(
    "/{wid}/rotate-token/",
    response=WalkthroughRotateTokenOut,
    summary="Rotate share token (owner only)",
)
def rotate_token(request: HttpRequest, wid: UUID) -> WalkthroughRotateTokenOut:
    _require_enabled()
    w = _get_or_404(wid)

    if not (request.user.is_authenticated and w.owner_id == request.user.id):
        raise ProblemError(403, "Forbidden — owner only", type_=TYPE_FORBIDDEN)

    new_token = w.rotate_share_token()
    return WalkthroughRotateTokenOut(share_token=new_token)
