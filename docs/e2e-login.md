# Token-gated E2E login

`POST /api/auth/e2e-login/` lets automated tools (gstack walkthroughs,
autonomous PM cycles, AI-driven QA) sign in without going through Google
OAuth. Same surfaces a human gets, no human in the loop.

## Enable

Set `CANOPY_E2E_AUTH_TOKEN` to a long random string. Empty (default)
means the endpoint returns 404 — no exposure unless explicitly enabled.

In Cloud Run prod, the secret is wired in `deploy.sh` from Secret
Manager (`canopy-e2e-auth-token:latest`). Mint a new value with:

```bash
TOKEN=$(openssl rand -hex 32)
echo -n "$TOKEN" | gcloud secrets create canopy-e2e-auth-token \
  --project=canopy-494811 --data-file=-
# or, for a new version:
echo -n "$TOKEN" | gcloud secrets versions add canopy-e2e-auth-token \
  --project=canopy-494811 --data-file=-
```

## Use

```bash
curl -c cookies.txt -X POST \
  https://canopy-web-hhhi4yut3q-uc.a.run.app/api/auth/e2e-login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"ace@dimagi.com","token":"<CANOPY_E2E_AUTH_TOKEN>"}'

# Now the cookie jar carries `sessionid`; reuse it on any gated route:
curl -b cookies.txt https://canopy-web-hhhi4yut3q-uc.a.run.app/api/projects/
```

For headless browsers (gstack, Playwright): hit the endpoint, then drive
the SPA — the response sets the `sessionid` cookie on the same client.

## Contract

- **Method:** `POST` only (`GET` returns 405).
- **Body:** JSON `{"email": "<addr>", "token": "<secret>"}`.
- **Email gate:** must match `AUTH_ALLOWED_EMAIL_DOMAIN` (defaults to
  `dimagi.com`); other domains return 400.
- **Token gate:** must equal `CANOPY_E2E_AUTH_TOKEN` exactly; mismatch
  returns 403.
- **User:** an `auth.User` is created on first call (`username == email`),
  reused on subsequent calls.
- **Audit marker:** the session blob carries `_canopy_e2e_session = {email,
  logged_in_at}` so e2e sessions can be filtered/revoked separately from
  human OAuth sessions or `mint-session` cookies.
