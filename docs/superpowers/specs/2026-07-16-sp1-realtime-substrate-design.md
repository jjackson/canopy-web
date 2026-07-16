# SP1 — Realtime Substrate

**Status:** Draft for review · **Date:** 2026-07-16 · **Author:** Jonathan + Claude

> Sub-project 1 of the Wave 4 program
> (`2026-07-16-realtime-chat-cloud-runner-program-design.md`). Stands up canopy-web's
> first realtime transport (Django Channels + Redis) and puts two surfaces live over
> it: the per-turn `TurnEvent` ledger tail, and `/supervisor`. No chat, no cloud
> runner, no ace-web yet — this is the foundation every later slice rides on.

---

## 1. Goal & deliverable

Today canopy-web has **no realtime** — the SPA polls. SP1 adds the transport that
the Channels layer in `config/settings/connectlabs.py` was already reserved for
("lands with W4"), and proves it against the two surfaces that most want to be live:

- **Turn tail** — the turn detail view live-tails a turn's append-only `TurnEvent`
  ledger. This is the exact primitive SP2's chat streaming builds on.
- **Supervisor** — `/supervisor` shows runner status + per-agent waiting counts live
  (no more mount-time-only fetch).

Both are consumers of **one** transport, exercising both fanout shapes:
point-to-point (`turn.{id}`) and per-workspace broadcast (`w.{slug}.supervisor`).

**Explicitly out of scope for SP1** (later SPs): any chat/Session/Draft model,
presence, co-editing, the cloud runner, and cross-app (ace-web) access. SP1 pushes
data that *already exists* over a new transport; it introduces no new domain model.

---

## 2. New framework app: `realtime`

A new Django app `apps/realtime/`, **framework tier**. Layout:

- `consumers.py` — `TurnConsumer`, `SupervisorConsumer` (both `AsyncJsonWebsocketConsumer`).
- `routing.py` — websocket URL patterns.
- `channels_auth.py` — the handshake auth middleware (cookie → Bearer PAT).
- `groups.py` — group-name helpers + membership gates (pure, unit-testable).
- `signals.py` — the `post_save` → `on_commit` → `group_send` fanout receivers.
- `apps.py` — wires signals in `ready()`.

It imports only framework apps (`harness`, `agents`, `workspaces`, `tokens`,
`common`). It is added to the framework set in both `ARCHITECTURE.md` and
`tests/test_architecture_boundary.py` (§9).

---

## 3. Transport wiring

- **Deps:** add `channels` and `channels_redis` to `pyproject.toml` (uv.lock committed).
- **Channel layer:** `CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}`. Reuse the ElastiCache Redis already configured as the cache in `connectlabs.py`; namespace the channel-layer prefix so a cache flush can't disturb pub/sub. Local/dev uses the same Redis from `docker-compose`. **Tests** override to `InMemoryChannelLayer` (§10).
- **ASGI:** extend `config/asgi.py`. Today a Starlette `Router` owns lifespan and
  mounts FastMCP at `/api/mcp` + Django ASGI elsewhere (http only). Add a Channels
  `ProtocolTypeRouter` so the `websocket` scope routes into
  `AllowedHostsOriginValidator(RealtimeAuthMiddleware(URLRouter(realtime.routing.websocket_urlpatterns)))`,
  while `http` continues to Django and Starlette keeps `lifespan` + the MCP mount.
  Respect the `/canopy` `FORCE_SCRIPT_NAME` / `StripScriptName` prefix
  (`config/asgi_prefix.py`) for WS paths too.
- **Server:** unchanged — `uvicorn config.asgi:application` already speaks websockets;
  no daphne needed.

---

## 4. Groups & routing

| Surface | WS route | Channels group | Membership gate |
|---|---|---|---|
| Turn tail | `ws/turns/{turn_id}/` | `turn.{turn_id}` | turn → agent/project → workspace → caller is a member |
| Supervisor | `ws/supervisor/` | `w.{slug}.supervisor` (one per workspace the caller belongs to) | caller's workspace memberships |

`/supervisor` is deliberately cross-workspace (like `/insights`), so a single
`ws/supervisor/` socket joins the caller to **each** `w.{slug}.supervisor` group for
the workspaces they belong to; the client sends nothing to choose scope. Group-name
construction and the membership checks live in `groups.py` as pure functions
(`turn_group(turn_id)`, `supervisor_group(slug)`, `user_can_read_turn(user, turn)`,
`user_workspace_slugs(user)` — the last already exists in `workspaces` services).

---

## 5. Fanout — how a write reaches the socket

Mirror the established `apps/push/signals.py` pattern (post_save + `on_commit`), so
the write path (`harness.services.append_events`, `heartbeat`, etc.) is **not**
coupled to Channels and stays synchronous/testable.

- **Turn tail** — `post_save` on `TurnEvent` → `transaction.on_commit` →
  `group_send(turn_group(te.turn_id), {"type": "turn.event", "seq": te.seq, "event": <serialized>})`.
  Because `append_events` assigns `seq` under a `select_for_update` row lock and can
  write a batch, the receiver coalesces a batch into one `group_send` carrying the
  contiguous new events (ordered by `seq`).
- **Supervisor** — two triggers:
  1. **Runner status** — `post_save` on `Runner` (heartbeat renews `last_heartbeat_at`; pair/retire change `status`) → `group_send(supervisor_group(runner.workspace.slug), {"type": "supervisor.runner", ...})`.
  2. **Waiting counts** — hook the point where `apps/push` already recomputes an
     agent's `waiting_count` (`services.refresh_agent_waiting` / `AgentWaitingSnapshot`):
     when the snapshot changes, also `group_send(supervisor_group(agent.workspace.slug), {"type": "supervisor.waiting", "agent": slug, "waiting_count": n})`. This reuses the existing coalesced recompute — no new counting logic.

All `group_send` calls go through a tiny `groups.publish(...)` helper wrapping
`get_channel_layer()` + `async_to_sync`, so a null/misconfigured layer degrades to a
no-op (the REST surfaces still work) rather than raising in a request.

---

## 6. WS handshake auth

Port ace-web's `AceSessionAuthMiddleware` as `realtime/channels_auth.py::RealtimeAuthMiddleware`:

1. Resolve `scope["user"]` from the **session cookie** first (canopy's session cookie
   name; honors the `/canopy` deploy), then fall back to `Authorization: Bearer <PAT>`
   (reusing `apps/tokens` resolution) for scripted clients.
2. Anonymous → the consumer rejects with close code `4001` on `connect()`.
3. Per-surface authorization happens in the consumer's `connect()`, not the
   middleware: `TurnConsumer` rejects `4003` if `user_can_read_turn` is false;
   `SupervisorConsumer` joins only the caller's workspace groups (empty set → still
   connect, just silent).

Bearer WS auth is included now because it's cheap alongside the cookie path and SP4
will need it; SP1's primary consumer is the browser SPA on the cookie path.

---

## 7. Replay & connect semantics

- **Turn tail (cursor replay).** Client connects with its last-seen `seq` as a query
  param (`?after=<seq>`, default 0). On `connect()`, after joining the group, the
  consumer reads `harness` ledger `after=seq` (the existing
  `GET /turns/{id}/events` read path, called in-process) and sends those events, then
  live-tails. A monotonic `seq` makes replay-then-tail idempotent: any event delivered
  both in the replay and via a race is de-duped by `seq` on the client. Strictly better
  than a full-snapshot re-fetch for an append-only ledger.
- **Supervisor (snapshot on connect).** On `connect()`, send one
  `supervisor.snapshot` frame = current runners (with derived `live_status`) + current
  per-agent `waiting_count` for the caller's workspaces (reads the same services the
  REST `/supervisor` endpoints use), then stream `supervisor.runner` /
  `supervisor.waiting` deltas. Runner/waiting state is small and mutable (not an
  append log), so a snapshot is the right primitive here — the opposite choice from the
  turn tail, on purpose.

---

## 8. Frontend

- **`useLiveTurn(turnId)`** — owns a `WebSocket` to `ws/turns/{id}/?after=<seq>`,
  exponential-backoff reconnect (`[1,2,5,10]s`, ported from ace-web's
  `useSessionSocket`), tracks the highest `seq` seen so a reconnect resumes from the
  cursor (no full re-fetch), and merges events de-duped by `seq`. Returns
  `{events, connected, lastError}`. The turn detail view swaps its REST poll for this
  hook; the REST `GET …/events` stays as the manual/fallback fetch.
- **`useLiveSupervisor()`** — one `WebSocket` to `ws/supervisor/`, applies the snapshot
  then runner/waiting deltas into the existing supervisor view-model. `SupervisorPage`,
  `RunnerStatus`, `WaitingOnYou`, `AgentKpiCard` read from it instead of a mount-time
  fetch.
- **`lib/wsUrl.ts`** — a ws/wss URL builder that respects `import.meta.env.BASE_URL`
  (the `/canopy` prefix), ported from ace-web.
- **Types** — hand-written WS frame types in `frontend/src/api/types.ws.ts`
  (`TurnEventFrame`, `SupervisorSnapshot`, `SupervisorRunner`, `SupervisorWaiting`);
  the OpenAPI generator does not cover the WS protocol.

---

## 9. Framework boundary

`apps/realtime` is **framework**. Add it to the framework set in
`tests/test_architecture_boundary.py` and the `ARCHITECTURE.md` tier table
(`test_every_app_is_classified` fails CI otherwise). It imports `harness`, `agents`,
`workspaces`, `tokens`, `common` — all framework — and no product app. It touches no
product concept; a turn's opaque metadata is never interpreted here.

---

## 10. Testing

- **Consumer tests** (`channels.testing.WebsocketCommunicator`, `InMemoryChannelLayer`
  via the test settings already used by ace-web's e2e/test configs): connect →
  auth reject paths (`4001` anon, `4003` non-member) → cursor replay delivers prior
  events → a fresh `append_events` is received live → supervisor snapshot + a runner
  heartbeat delta is received.
- **Group/gate unit tests** — `groups.py` pure functions (name construction,
  `user_can_read_turn`, workspace-set membership) tested without a socket.
- **Signal tests** — saving a `TurnEvent` inside a transaction fans out exactly once
  on commit (and coalesces a batch); a rollback fans out nothing; a null channel layer
  is a no-op, not an error.
- **Frontend** — `useLiveTurn` reducer/merge logic unit-tested (seq de-dupe, reconnect
  resumes from cursor), mirroring ace-web's `sessionReducer` tests.

---

## 11. Deployment / infra

- **ALB** — the shared labs ALB already carries HTTP/1.1; enable websocket upgrade on
  the canopy target group and raise the target-group idle timeout above the WS
  heartbeat interval so idle sockets aren't culled. (ace-web already runs Channels
  behind this same ALB — a proven path.)
- **Redis** — reuse the existing shared ElastiCache instance; the channel layer is
  additive to the current cache use. No new infra to provision.
- **ECS** — single web container is unchanged (uvicorn already serves WS). No new
  service in SP1 (the cloud-runner service arrives in SP2).
- **Settings** — `CHANNEL_LAYERS` added to `base.py` (dev/docker Redis) and confirmed
  in `connectlabs.py` (the reserved seam).

---

## 12. Error handling & degradation

- A missing/misconfigured channel layer → `groups.publish` no-ops; REST surfaces
  keep working. Realtime is an enhancement, never a hard dependency of a write.
- A dropped socket → client backoff-reconnects and resumes turn tail from its `seq`
  cursor / re-requests a supervisor snapshot. No server-side per-socket durable queue
  in SP1 (the ledger + snapshot are the durable state).
- Fanout is best-effort: the durable record is always the DB (ledger row / runner row
  / waiting snapshot); the socket is a live view over it.

---

## 13. Deferred to later SPs

- Chat `Session`/`Message`/`Draft`, presence, co-editing, stream-survives-disconnect,
  cross-process stop → **SP2/SP3** (they reuse this transport + `useLiveTurn`).
- The cloud runner appending events (SP1 pushes whatever *any* writer appends today) →
  **SP2**.
- Cross-app (ace-web) WS access + CORS/origin policy for a second frontend → **SP4**
  (the Bearer handshake is in place; the origin allowlist widens then).
