"""Token-gated login for automated tools (gstack walkthroughs, autonomous
PM cycles, AI-driven QA).

Unlike `mint-session` (which requires an already-authenticated browser),
this endpoint takes a pre-shared secret and logs in a service user with
no human in the loop. It exists so headless agents can drive every
OAuth-gated UI surface the same way humans can.

SECURITY:
- Disabled by default (CANOPY_E2E_AUTH_TOKEN defaults to empty string).
- The view returns 404 when the token is unset; the URL is registered
  unconditionally (the in-view check is the gate).
- Email is restricted to settings.AUTH_ALLOWED_EMAIL_DOMAIN.
- Sessions carry a `_canopy_e2e_session` marker so they can be audited
  or bulk-revoked.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

E2E_SESSION_MARKER = "_canopy_e2e_session"


def _is_allowed_domain(email: str) -> bool:
    allowed = (getattr(settings, "AUTH_ALLOWED_EMAIL_DOMAIN", "") or "").lower()
    if not allowed:
        return True
    _, _, domain = email.rpartition("@")
    return domain.lower() == allowed


@csrf_exempt
@require_http_methods(["POST"])
def e2e_login(request: HttpRequest) -> HttpResponse:
    """POST /api/auth/e2e-login/

    Body (JSON): {"email": "ace@dimagi.com", "token": "<secret>"}
    Response: 200 with {"user_id": int, "email": str, "created": bool}
    On success, the response sets the Django session cookie so subsequent
    requests on the same client are authenticated.
    """
    expected_token = (getattr(settings, "CANOPY_E2E_AUTH_TOKEN", "") or "").strip()
    if not expected_token:
        return JsonResponse({"error": "e2e login is disabled"}, status=404)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    token = (body.get("token") or "").strip()
    if not token or token != expected_token:
        logger.warning("e2e_login: invalid token attempt")
        return JsonResponse({"error": "invalid token"}, status=403)

    email = (body.get("email") or "").strip().lower()
    if not email:
        return JsonResponse({"error": "email is required"}, status=400)

    if not _is_allowed_domain(email):
        allowed = getattr(settings, "AUTH_ALLOWED_EMAIL_DOMAIN", "")
        return JsonResponse(
            {"error": f"email must be from: @{allowed}"},
            status=400,
        )

    user_model = get_user_model()
    user = user_model.objects.filter(email__iexact=email).first()
    created = False
    if user is None:
        user = user_model.objects.create_user(username=email, email=email)
        created = True

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session[E2E_SESSION_MARKER] = {
        "email": email,
        "logged_in_at": timezone.now().isoformat(),
    }
    request.session.save()
    logger.info("e2e_login: authenticated %s (created=%s)", email, created)

    return JsonResponse({
        "user_id": user.pk,
        "email": user.email,
        "created": created,
    })
