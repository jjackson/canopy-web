# Schedule CRUD over the canopy-web MCP — design

**Date:** 2026-07-16
**Status:** Approved, not yet implemented
**Tier:** Framework (`apps/harness` + `apps/mcp`)

## Problem

Agents (Ada conducting the fleet, or any PAT-bearing client) can already read
and write insights over the canopy-web MCP, but scheduled turns —
`AgentSchedule` CRUD — are reachable only through the session-authed REST
surface and the browser UI. An agent cannot set up "Echo's weekly manager
report" or reason about a schedule's next fire times through its tools.

We want the six schedule operations exposed as MCP tools: **list, create,
update, delete, run-now, preview**.

## The constraint that shapes the design

`apps/mcp/tools/insights.py` documents the MCP's load-bearing invariant:

> `list_insights` (read) and `clear_insights` (write) call the SAME shared
> service functions as the REST views (`apps.projects.services`), so the two
> surfaces can never drift.

For insights that works because `apps.projects.services` exists. **For
schedules it does not** — create/update/delete/list/run-now are inline ORM and
control flow inside the Django-Ninja route handlers (`apps/harness/api_schedules.py`).
An MCP tool would have to re-implement them, and the drift is not hypothetical:

- `delete_schedule` calls `services.supersede_open_turns()` **before**
  `.delete()`. A tool that forgot would reintroduce the permanent agent wedge
  the final review of the scheduling feature caught (a deleted schedule's
  executing turn becomes unreleasable, blocking every subsequent turn for that
  agent forever).
- `create`/`update` catch `IntegrityError` from `uniq_agent_schedule_name` and
  return a 409 — inside a savepoint, because `SESSION_SAVE_EVERY_REQUEST` makes
  an un-savepointed `IntegrityError` poison the request transaction and 400.
- `update` uses `exclude_none=True` so an explicit `{"cron": null}` can't
  `setattr` None onto a non-nullable column.

So the design is not "add six tools." It is: **extract a request-free service
layer both surfaces call, then add six thin tool wrappers.**

## Architecture

```
apps/harness/schedule_services.py   ← NEW. The single implementation.
        │  request-free; takes `user`, raises domain exceptions
        ├── api_schedules.py (REST)  — keeps ScheduleIn/Out schemas; maps
        │                              domain exceptions → HTTP (404/409/422)
        └── mcp/tools/schedules.py   — NEW. 6 @mcp.tool wrappers; maps
                                       domain exceptions → tool errors
```

### The new service module — `apps/harness/schedule_services.py`

Functions, each taking the resolved user and doing the auth itself:

| Function | Signature (abbreviated) | Returns |
|---|---|---|
| `list_schedules` | `(user, agent_slug, *, workspace_slug=None)` | `list[AgentSchedule]` |
| `create_schedule` | `(user, agent_slug, fields: dict, *, workspace_slug=None)` | `AgentSchedule` |
| `update_schedule` | `(user, agent_slug, schedule_id, fields: dict, *, workspace_slug=None)` | `AgentSchedule` |
| `delete_schedule` | `(user, agent_slug, schedule_id, *, workspace_slug=None)` | `None` |
| `run_schedule_now` | `(user, agent_slug, schedule_id, *, workspace_slug=None)` | `AgentSchedule` |
| `preview_cron` | `(user, agent_slug, cron, timezone, *, workspace_slug=None)` | `list[datetime]` |

The module holds the logic that lives in the routes today: the
supersede-before-delete rule, the duplicate-name detection, the savepoint, the
`exclude_none` reconciliation. **`create`/`update` take a plain `fields` dict**
(already validated by the caller's schema) rather than a Pydantic model, so the
service depends on neither Ninja nor the MCP's shapes. Cron/timezone validation
stays in the Pydantic schema for REST and is applied explicitly in the tool
layer for MCP (both call `canopy_cron.validate_cron`/`validate_timezone`, the
single validators) — the service assumes validated input, exactly as the ORM
layer does today.

`preview_cron` takes an `agent_slug` purely to authorize (you must be able to
see the agent to preview against it) — matching the REST `preview` route, which
calls `_agent_or_404` and ignores the agent otherwise.

### Authorization without a `request`

The REST gate (`_agent_or_404`) does three things: `auto_join_workspaces(user)`
→ `request.workspace_slug` tenant-pin → `is_member`. The middle step is a
*tenant-URL* concept (`/api/w/{ws}/…`) the MCP has no equivalent for.

So the resolution helper is request-free and takes the pin as a parameter:

```
_resolve_agent(user, agent_slug, workspace_slug=None) -> Agent
```

- REST passes `getattr(request, "workspace_slug", None)` → **behavior identical
  to today**.
- MCP passes `None` → membership gating only, no tenant-URL pin.

Every failure (missing agent, wrong tenant, non-member) raises the same
`ScheduleNotFound` — REST maps it to 404, MCP to a tool error — so
non-membership never leaks existence, on either surface.

### Domain exceptions (the seam that keeps the service HTTP-free)

The service must not import Ninja or raise `HttpError` (the MCP would inherit an
HTTP dependency it has no use for). It raises two plain exceptions:

- `ScheduleNotFound` — agent missing / wrong tenant / non-member / schedule
  id not under this agent. One type for all, so existence never leaks.
- `DuplicateScheduleName(name)` — the `uniq_agent_schedule_name` violation.

REST maps them in its handlers (`ScheduleNotFound` → `HttpError(404)`,
`DuplicateScheduleName` → the existing `_duplicate_name` 409 `ProblemError` with
`TYPE_CONFLICT`). The MCP tools re-raise them after auditing, exactly as
`insights.py` re-raises on its except path (`raise`) — FastMCP surfaces the
exception message to the caller; we do not wrap a bespoke error type unless the
raw message leaks something, which these two (a not-found and a name clash) do
not. The savepoint that wraps the `IntegrityError` lives **in the service**,
since `SESSION_SAVE_EVERY_REQUEST` is a property of the request path both
surfaces hit.

## The six MCP tools — `apps/mcp/tools/schedules.py`

Each follows `insights.py` exactly: `@mcp.tool` async → resolve
`current_user_id()` → (writes) `check_write_limit()` → run the ORM work via
`sync_to_async(fn, thread_sensitive=True)` → `write_audit()` on **both** the
success and exception paths.

| Tool | Kind | Wraps |
|---|---|---|
| `list_schedules(agent_slug, limit=100)` | read | `schedule_services.list_schedules` |
| `preview_cron(agent_slug, cron, timezone="UTC")` | read | `schedule_services.preview_cron` |
| `create_schedule(agent_slug, name, prompt, cron, timezone="UTC", …)` | write | `schedule_services.create_schedule` |
| `update_schedule(agent_slug, schedule_id, …)` | write | `schedule_services.update_schedule` |
| `delete_schedule(agent_slug, schedule_id)` | write | `schedule_services.delete_schedule` |
| `run_schedule_now(agent_slug, schedule_id)` | write | `schedule_services.run_schedule_now` |

Tools return plain dicts (a `_serialize_schedule` helper in the service returns
a dict, and REST builds its `ScheduleOut` from that dict — one serialization
shape, computed once, including `fire_after` and `next_runs`).

The tool module is imported for its side effect (the `@mcp.tool` registration),
exactly as `insights.py` is: add `from . import schedules  # noqa: F401` to
`apps/mcp/tools/__init__.py`, beside the existing insights import.

### `run_schedule_now` — the one tool with teeth

It is the only tool that spawns a real Claude session and burns tokens, and the
only one an AI could loop on. Two deliberate choices:

- It **stays in scope** (the user chose full CRUD + run-now): Ada's job is
  deciding what the fleet runs next, and off-cycle firing is part of that.
- Its audit row records the **schedule name + agent slug**, so a runaway is
  visible in `MCPAuditLog` rather than inferred from spawned sessions. It
  inherits the generic per-user write rate limit (sized for `clear_insights`);
  we do **not** add a bespoke limit now — one is a YAGNI until the audit log
  shows it's needed. The audit visibility is the guardrail that tells us.

## Non-goals

- No new rate-limit tier for `run_now` (audit visibility first; add a limit only
  if the log shows abuse).
- No change to the REST surface's behavior — the extraction must be
  behavior-preserving, proven by the existing `tests/test_schedule_api.py`
  passing unchanged.
- No new MCP auth model — per-user PAT, as today.

## Testing

- **The extraction is behavior-preserving.** `tests/test_schedule_api.py` (the
  REST suite: create/list/patch/delete/run-now/preview, the duplicate-name 409,
  the explicit-null PATCH, the tenancy 404) must pass **unchanged**. That is the
  regression gate on the refactor.
- **New service tests** (`tests/test_schedule_services_crud.py`): the request-free
  functions directly — auth resolution (member vs non-member vs wrong-tenant all
  → `ScheduleNotFound`), `DuplicateScheduleName`, delete-supersedes-open-turns
  (assert the executing turn is retired and a new executing turn is insertable —
  the wedge regression), `workspace_slug=None` path (MCP shape) vs a pinned slug
  (REST shape).
- **New MCP tests** (mirror `apps/mcp/tests/`): each tool round-trips; writes
  audit on success and on error; `run_schedule_now`'s audit row carries the
  schedule name; a non-member's `agent_slug` yields a tool error, not a leak;
  the write rate limit applies to the five writers.
- **MCP surface doc:** update `docs/architecture/mcp-surface.md`'s tool inventory
  (today it lists only `list_insights` + `clear_insights`).

## Files

| File | Change |
|---|---|
| `apps/harness/schedule_services.py` | **new** — the shared service layer + domain exceptions + dict serializer |
| `apps/harness/api_schedules.py` | route handlers become thin: call the service, map domain exceptions → HTTP, keep the Pydantic schemas |
| `apps/mcp/tools/schedules.py` | **new** — 6 tool wrappers |
| `apps/mcp/tools/__init__.py` | one line: `from . import schedules  # noqa: F401` |
| `tests/test_schedule_services_crud.py` | **new** |
| `apps/mcp/tests/test_schedule_tools.py` | **new** |
| `docs/architecture/mcp-surface.md` | tool inventory |
| `CLAUDE.md` | MCP tool list (currently "Tools today: `list_insights` + `clear_insights`") |

## Open for iteration

- A per-tool rate limit on `run_schedule_now` if the audit log shows looping.
- Exposing `next_runs`/`last_status` richness in the tool return is free (the
  serializer already computes them); trim only if the payload proves noisy.
