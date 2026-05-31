# MCP Surface

canopy-web exposes a curated set of tools as a
[FastMCP](https://github.com/jlowin/fastmcp) 3.x server, mounted at
`/api/mcp/` over **Streamable HTTP**. External MCP clients (Claude Code,
other agents) call these tools to inspect and mutate canopy-web state.

Tools are **explicit in-process Python functions** that run **as the
authenticated user** — there is no OpenAPI auto-derivation and no HTTP
self-loopback anymore. The implementation lives in `apps/mcp/`.

## Module layout (`apps/mcp/`)

| File | Responsibility |
|---|---|
| `auth.py` | `CanopyPATVerifier` — a FastMCP `TokenVerifier` that resolves a Personal Access Token to a Django user (mirrors `apps.tokens.middleware`). |
| `server.py` | The `FastMCP("canopy-web")` instance with `MultiAuth` (PAT + optional OAuth), and `build_http_app()` for the ASGI mount. |
| `tools/insights.py` | `list_insights` (read) + `clear_insights` (write) tools. |
| `rate_limit.py` | Per-user write rate limit (mutating tools). |
| `audit.py` | `current_user_id()` + `write_audit()` (writes `MCPAuditLog`). |
| `models.py` | `MCPAuditLog` — one row per tool call. |

Tools reuse the SAME service functions as the REST views
(`apps.projects.services`), so the REST and MCP surfaces cannot drift.

## Auth model — dual auth (MultiAuth)

```python
MultiAuth(
    server=<GoogleProvider or None>,     # interactive OAuth (env-gated seam)
    verifiers=[CanopyPATVerifier()],     # per-user PAT (always on)
)
```

* **PAT (priority, always on).** A per-user Personal Access Token
  (`apps.tokens`) presented as `Authorization: Bearer <raw>`.
  `CanopyPATVerifier.verify_token()` calls `PersonalToken.lookup()`,
  stamps `last_used_at`, and returns a FastMCP `AccessToken` whose claims
  carry the user (`sub`/`user_id`/`email`). Tools read the user via
  `get_access_token()`. A miss returns `None` → 401.

* **OAuth (interactive, env-gated seam).** When `MCP_OAUTH_ENABLED=true`
  and the Google OAuth creds are present, a FastMCP `GoogleProvider` is
  wired as the MultiAuth `server=`, letting interactive clients
  browser-login. **Off by default** — completing it requires registering
  FastMCP's redirect URI (`<MCP_BASE_URL>/auth/callback`) on the existing
  Google OAuth client. See the docstring in `apps/mcp/server.py`.

The legacy single shared `CANOPY_MCP_BEARER` and the hand-rolled ASGI
gate in `config/asgi.py` are GONE — auth is now enforced inside the MCP
app by MultiAuth.

## Tools

| Tool | Kind | Purpose |
|---|---|---|
| `list_insights` | read | Cross-portfolio insights feed (filter by `category`/`source`/`project`/`limit`). |
| `clear_insights` | write (rate-limited) | Delete insights by `source`/`category`/`project`/`older_than_days`. No filters clears all. |

## Mount + lifespan (`config/asgi.py`)

Streamable HTTP requires the MCP app's lifespan to run (session
management). The Django bare ASGI app has no lifespan, so the app is a
Starlette router that mounts the MCP app under `/api/mcp` and the Django
app at `/`, with `lifespan=mcp_app.lifespan`:

```python
mcp_app = build_http_app()  # mcp.http_app(path="/", transport="streamable-http")
application = Starlette(
    routes=[Mount("/api/mcp", app=mcp_app), Mount("/", app=django_asgi_app)],
    lifespan=mcp_app.lifespan,
)
```

## How to connect Claude Code

```json
{
  "canopy-web": {
    "url": "https://<canopy-web>/api/mcp/",
    "headers": { "Authorization": "Bearer <your-PAT>" }
  }
}
```

Mint a PAT with `manage.py create_token --email <you> --label <name>` or
the `/canopy:canopy-web-pat-mint` flow.

## Note on `x-mcp-expose` tags

The old server auto-derived tools from `openapi_extra={"x-mcp-expose":
True}` OpenAPI tags. Tools are now explicit functions, so those tags are
**inert** — they remain on a couple of Ninja routes as harmless OpenAPI
metadata and no longer drive tool registration.
