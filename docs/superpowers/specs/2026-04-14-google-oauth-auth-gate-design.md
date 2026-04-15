# Google OAuth Auth Gate — Design

**Date:** 2026-04-14
**Status:** Draft for review
**Scope:** Add a lightweight authentication gate to canopy-web so only users with `@dimagi.com` Google accounts can access the app. Data remains single-tenant for now, but the implementation is structured so per-user ownership can be layered on later.

## Goals

- Anyone with an `@dimagi.com` Google account can log in and use canopy-web.
- Everyone else is blocked at login with a friendly message.
- No code or deploy paths remain unauthenticated (except the login flow itself and `/health/`).
- The user model and session framework are in place so a future "per-user data" phase is additive, not a rewrite.

## Non-goals

- Per-user data isolation (deferred).
- Third-party OAuth providers beyond Google (deferred).
- Email/password login fallback (deferred).
- Token-based API auth for non-browser clients (deferred).

## Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Auth boundary | Application-level (Django) | Works locally; enables future multi-tenancy with a user model in place. |
| OAuth library | `django-allauth` | Battle-tested; includes user management, admin integration, and a clean extension point (`SocialAccountAdapter`) for the domain check. |
| Session transport | httpOnly session cookie | Safer than JWT-in-localStorage; Django sessions give server-side revocation and first-class CSRF. |
| CSRF | Enabled, cookie + header pattern | Required once a session cookie exists. Frontend reads `csrftoken` cookie, sends as `X-CSRFToken` header. |
| Frontend login UI | Django-rendered allauth pages | Avoid reimplementing OAuth state handling in React. SPA only needs to detect 401 and redirect. |
| Deployment topology | Single Cloud Run service | Django serves API, allauth, admin, and the built SPA. Same-origin cookies, no CORS, one URL, one deploy. |

## Components

### Backend

**`apps/common/auth_adapter.py` (new)**
```python
class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = (sociallogin.account.extra_data.get('email') or '').lower()
        if not email.endswith('@dimagi.com'):
            raise ImmediateHttpResponse(render(request, 'auth/domain_rejected.html', status=403))
```

**`apps/common/middleware.py` (new) — `LoginRequiredMiddleware`**
- Default-deny: every request requires `request.user.is_authenticated`.
- Allowlist: `/accounts/*` (allauth), `/admin/*` (Django admin has its own auth), `/health/`, `/api/csrf/` (must be reachable to bootstrap the CSRF cookie before login), static/asset paths.
- For `/api/*` unauthenticated requests (other than the allowlist), return `JsonResponse({'detail': 'Authentication required'}, status=401)`. `/api/me/` is intentionally *not* allowlisted — it's the signal the SPA uses to learn it needs to log in.
- For other routes, redirect to `/accounts/google/login/?next=<path>`.
- Gated by a settings flag `REQUIRE_AUTH` (default `True`, but can be toggled during rollout).

**`apps/common/views.py` (extend)**
- `me_view` — `GET /api/me/` returns `{email, name, avatar_url}` for the current user; 401 if unauthenticated.
- `csrf_view` — `GET /api/csrf/` decorated with `@ensure_csrf_cookie`; forces CSRF cookie to be set on first SPA load. Returns `{}`.

**`templates/auth/domain_rejected.html` (new)**
Simple page: "Canopy is restricted to @dimagi.com accounts. [Try another account]." Styled consistent with the app.

**CSRF sweep**
Remove `@csrf_exempt` from every API view in:
- `apps/projects/views.py`
- `apps/collections/views.py`
- `apps/workspace/views.py`
- `apps/skills/views.py`
- `apps/evals/views.py`
- `apps/common/views.py` (Claude CLI auth endpoints)

### Settings

**`config/settings/base.py`**
- `INSTALLED_APPS`: add `django.contrib.sites`, `allauth`, `allauth.account`, `allauth.socialaccount`, `allauth.socialaccount.providers.google`.
- `MIDDLEWARE`: add `allauth.account.middleware.AccountMiddleware` and `apps.common.middleware.LoginRequiredMiddleware` (last, after session + auth middleware).
- `AUTHENTICATION_BACKENDS`: `['django.contrib.auth.backends.ModelBackend', 'allauth.account.auth_backends.AuthenticationBackend']`.
- `SITE_ID = 1`.
- `SOCIALACCOUNT_PROVIDERS = {'google': {'APP': {'client_id': env('GOOGLE_OAUTH_CLIENT_ID'), 'secret': env('GOOGLE_OAUTH_CLIENT_SECRET'), 'key': ''}, 'SCOPE': ['profile', 'email']}}`.
- `SOCIALACCOUNT_ADAPTER = 'apps.common.auth_adapter.CustomSocialAccountAdapter'`.
- `SOCIALACCOUNT_LOGIN_ON_GET = True`.
- `ACCOUNT_EMAIL_VERIFICATION = 'none'`.
- `LOGIN_REDIRECT_URL = '/'`, `ACCOUNT_LOGOUT_REDIRECT_URL = '/'`.
- `REQUIRE_AUTH = env.bool('REQUIRE_AUTH', default=True)`.

**`config/settings/production.py`**
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `SESSION_COOKIE_SAMESITE = 'Lax'`.
- Remove `CORS_ALLOW_ALL_ORIGINS = True` and the `corsheaders` middleware entirely (no longer needed — single-origin).
- WhiteNoise for static files: add `whitenoise.middleware.WhiteNoiseMiddleware` right after `SecurityMiddleware`.
- `STATIC_ROOT`, `STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'`.

**`.env.example`**
Add:
```
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
REQUIRE_AUTH=True
```

### URL routing

**`config/urls.py`**
- Add `path('accounts/', include('allauth.urls'))`.
- Add `path('api/me/', me_view)`, `path('api/csrf/', csrf_view)`.
- Add a catch-all view (last) that serves the built SPA `index.html`, so React Router handles client-side routes. Django's existing routes (`/admin/`, `/api/*`, `/accounts/*`, `/health/`, `/static/*`) take precedence.

### Frontend

**`frontend/src/api/client.ts`**
- Add a CSRF helper: read `csrftoken` cookie, include as `X-CSRFToken` header on non-GET requests.
- All fetches use `credentials: 'include'` (already same-origin, but explicit).
- Centralized 401 handler: on 401, redirect `window.location` to `/accounts/google/login/?next=${encodeURIComponent(currentPath)}`.

**`frontend/src/auth/AuthProvider.tsx` (new)**
- On mount: `GET /api/csrf/`, then `GET /api/me/`.
- Exposes `{user, loading}` via React context.
- Renders a loading state until `/api/me/` resolves.

**`frontend/src/router.tsx`**
- Wrap the router in `<AuthProvider>`.
- No route guards needed — backend enforces; 401 triggers redirect.

**Header / nav**
- Add user chip (avatar + email) and logout button.
- Logout: submits a form POST to `/accounts/logout/` (allauth requires POST; `<form method="post" action="/accounts/logout/"><input type="hidden" name="csrfmiddlewaretoken" value={token}/><button/></form>`).

### Deployment topology change — single Cloud Run service

Today: two Cloud Run services (frontend, backend).
Target: one Cloud Run service running Django; Django serves the built SPA as static files via WhiteNoise.

**`Dockerfile` changes**
- Multi-stage: stage 1 builds the frontend (`npm run build` → `frontend/dist/`).
- Stage 2 (Python) copies `frontend/dist/` into the Django static layout.
- `python manage.py collectstatic --noinput` at build time.
- Uvicorn serves the ASGI app; WhiteNoise handles static assets.

**`deploy.sh` changes**
- Drop the frontend deploy entirely.
- Backend deploy picks up the new combined image.
- Keep `--allow-unauthenticated` on the Cloud Run service (the app enforces the gate; the service must be publicly reachable for the OAuth login flow).
- Add `--set-secrets` for `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` from Secret Manager.
- Delete the old frontend Cloud Run service after verifying.

**`docker-compose.yml`**
- Frontend and backend are still separate services in local dev (Vite's HMR is too valuable to give up). The Vite dev server proxies `/api`, `/accounts`, `/admin`, `/health` to Django. Production is single-service only.

### Google Cloud setup

- One OAuth 2.0 Client ID in the Dimagi GCP project (Web application).
- Authorized redirect URIs:
  - `http://localhost:8000/accounts/google/login/callback/` (dev)
  - `https://<prod-domain>/accounts/google/login/callback/` (prod)
- Client ID + secret stored in Secret Manager; referenced by `deploy.sh`.

## Data flow (login)

1. User visits `/`. Frontend calls `GET /api/csrf/` (CSRF cookie set) then `GET /api/me/`.
2. `/api/me/` returns 401. Frontend redirects browser to `/accounts/google/login/?next=/`.
3. Allauth redirects to Google. User consents.
4. Google redirects to `/accounts/google/login/callback/`. Allauth handles the code exchange.
5. `CustomSocialAccountAdapter.pre_social_login` runs; checks `@dimagi.com`.
   - Pass: allauth creates/fetches the `User`, opens a session, sets the `sessionid` cookie, redirects to `/` (or `next`).
   - Fail: `ImmediateHttpResponse` with the 403 domain-rejected page.
6. Frontend reloads at `/`. `GET /api/me/` returns 200. App renders.

## Data flow (logout)

1. User clicks logout in header. Frontend POSTs to `/accounts/logout/` with CSRF token.
2. Django clears the session, redirects to `/`.
3. Frontend calls `/api/me/`, gets 401, redirects to login.

## Migrations

- `allauth` and `django.contrib.sites` add tables. Running `migrate` applies them.
- One-time data migration to create the `Site` row with the production domain (replaces the default `example.com`).

## Testing (`tests/test_auth.py` new)

- Unauthenticated `GET /api/projects/` → 401 JSON.
- Unauthenticated `GET /some-page` → 302 to `/accounts/google/login/`.
- `/health/` remains reachable unauthenticated.
- `CustomSocialAccountAdapter.pre_social_login` with `@gmail.com` → raises `ImmediateHttpResponse` with status 403.
- `CustomSocialAccountAdapter.pre_social_login` with `@dimagi.com` → succeeds, user is created.
- `GET /api/me/` authenticated → returns email, name.
- CSRF: POST to `/api/projects/` with session but no `X-CSRFToken` → 403.
- CSRF: POST with session + valid `X-CSRFToken` → 200.

Existing tests: a shared `authed_client` pytest fixture that creates a test user and logs them in. Apply to any test that hits a protected endpoint.

## Rollout plan

1. Merge the code with `REQUIRE_AUTH=False` in production env. Everything still works unauthenticated.
2. In production, run `migrate`, create the `Site` row, create a Django superuser (for `/admin/`).
3. Verify the Google OAuth client works end-to-end: log in locally and in prod, confirm the domain gate rejects a non-dimagi account.
4. Flip `REQUIRE_AUTH=True` in production. Redeploy.
5. Delete the old frontend-only Cloud Run service.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| CSRF sweep breaks existing flows. | Explicit test for each state-mutating endpoint after the sweep; fix one call site at a time on the frontend. |
| OAuth callback URI mismatch in prod. | Staging check against the prod domain before flipping `REQUIRE_AUTH`. |
| Static asset path confusion in the single-service Dockerfile. | Verify `collectstatic` output and WhiteNoise serving locally via `docker build && docker run` before deploying. |
| Cloud SQL session table growth unbounded. | Django's default session backend writes to DB. Cleanup is a `clearsessions` cron — defer; low volume. |
| Single-tenant assumption leaks into code during implementation. | Keep all views framed as "the current user's X" where sensible, even if the query is currently global. Makes the multi-tenancy diff smaller later. |

## Open questions

None at this time; the spec can proceed to planning.
