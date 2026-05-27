# MCP Surface

canopy-web exposes a curated set of read-only endpoints as MCP tools via
[FastMCP](https://github.com/jlowin/fastmcp). External MCP clients (Claude
Code, other agents) can call these tools to inspect canopy-web state
without learning the full REST surface.

## How an endpoint opts in

Add `openapi_extra={"x-mcp-expose": True}` to the Ninja route decorator:

```python
@router.get(
    "/slugs/",
    response=list[ProjectSlugOut],
    openapi_extra={"x-mcp-expose": True},
)
def get_project_slugs(request): ...
```

At process start, `apps/api/mcp_server.py::register_tools()` walks the
OpenAPI schema and registers one MCP tool per `x-mcp-expose: true` operation.

## Exposed endpoints (as of Task 7.2)

| Operation | Path | Method | Purpose |
|---|---|---|---|
| `get_project_slugs` | `/projects/slugs/` | GET | Slim machine-readable project slug list (used by `canopy:portfolio-review` etc.) |
| `list_insights` | `/insights/` | GET | Cross-portfolio insights feed (filtered by category, source, project) |

Write endpoints (mutations) are intentionally NOT exposed in V1.

## Auth model

MCP tools authenticate via Bearer token in the loopback HTTP call:

```
Authorization: Bearer <WORKBENCH_WRITE_TOKEN>
```

The token is sourced from the `CANOPY_MCP_BEARER` env var inside the
`apps/api/mcp_server.py` module. The bearer is matched in
`apps/common/middleware.py`'s `WORKBENCH_TOKEN_READABLE_PATHS`
allowlist for the affected paths.

## How to connect Claude Code

Add to your local `~/.claude/mcp.json` (or per-project `.mcp.json`):

```json
{
  "canopy-web": {
    "url": "https://<canopy-web>/api/mcp/",
    "headers": {
      "Authorization": "Bearer <WORKBENCH_WRITE_TOKEN>"
    }
  }
}
```

Restart Claude Code. The tools listed above should appear in the MCP
dropdown; calling one returns the JSON payload from the corresponding
REST endpoint.

## Production exposure

The MCP server is auth-gated by the same Bearer-bypass machinery as REST.
Set `CANOPY_MCP_BEARER` on the Cloud Run service env to the same
`WORKBENCH_WRITE_TOKEN` value the canopy plugin uses.
