# Wave 4 — Realtime, Chat & the Canopy Cloud Runner

**Status:** Draft for review · **Date:** 2026-07-16 · **Author:** Jonathan + Claude

> Program / strategy design doc, not an implementation plan. It settles the
> architecture for bringing ACE-web's chat + multiplayer approach into canopy-web
> as generic framework substrate, and for making canopy-web execute agent runs in
> the cloud — with **ace-web as the first consumer** of that cloud runner.
> Each sub-project (SP1–SP4) gets its own spec → plan → implementation cycle.
>
> This is **Wave 4** under the framework-harvest strategy
> (`2026-06-24-canopy-framework-harvest-design.md`). The dependency arrow is
> unchanged: **ACE → Canopy.** Canopy is the home; ace-web depends on it.

---

## 1. The settled stance

One sentence: **canopy-web becomes the hosted hub for live agent execution —
generic chat, multiplayer, and a real cloud runner — and ace-web becomes its
first consumer, retiring its in-container `claude -p` subprocess model.**

Four load-bearing decisions, settled in brainstorming:

1. **Hosted hub, not a shared library.** canopy-web *runs* the shared control
   plane + realtime + cloud-runner fleet as a live service. ace-web calls its API
   as tenant #1. (Consistent with the harvest invariant: no neutral third package;
   Canopy is the home.)
2. **Generic chat moves to canopy; ace-web keeps its product layer.** canopy owns
   the agent-agnostic `Session` / `Message` / `Draft` / presence / execution
   substrate. ace-web keeps only its opp-specific product concerns (workbench UI,
   Drive tools, decision buffer, opp linkage) and talks to canopy's chat API.
   This is the framework/product split, honored across a repo boundary.
3. **Unify on the harness ledger.** A chat "send" enqueues a harness `Turn` (the
   durable execution envelope); the assistant's streamed output is appended to the
   existing `TurnEvent` ledger by the cloud runner; `Message` rows are a
   **projection** over the ledger. Chat is the interactive front-door to a durable
   cloud run — **one** execution substrate, not two.
4. **Warm runner service.** The canopy cloud runner is a `kind=cloud` daemon on
   its **own** ECS service (separate from the web tier), porting ace-web's proven
   `claude -p` stream-json subprocess pool. Session affinity rides the existing
   harness `SessionLink` / `resolve-session` mechanism. Start warm; add
   task-per-run isolation later only if a workload demands it.

### 1.1 Why this is the natural shape

The two halves already exist, split across the two repos:

- **canopy-web already owns the control plane** — `apps/harness/` has the `Runner`
  registry, the `Turn` queue with atomic claim + leases, the append-only
  `TurnEvent` ledger, cron `AgentSchedule`, and `SessionLink` cross-account session
  reuse. It has **no realtime** — everything is HTTP polling today.
- **ace-web already owns the chat/multiplayer pattern** — Django Channels + Redis
  WebSockets, co-edited `Draft`, Redis-HASH presence, and a `turn_driver` that
  streams a turn and survives the initiating client's disconnect. But its cloud
  **execution** is the pain: the Django ASGI container spawns `claude -p`
  **in-process**, one subprocess per session, pooled in memory per ECS task —
  so it needs ALB stickiness and **every deploy/OOM SIGKILLs all live runs**
  (patched today with post-deploy auto-resume).

Wave 4 unifies them in canopy: canopy contributes the durable queue/claim/lease it
already has; ace-web contributes the realtime chat pattern it already proved. The
result fixes ace-web's deploy-kill pain for free — because execution moves off the
web tier onto a durable, reclaimable runner tier.

canopy-web was pre-wired for exactly this: `config/settings/connectlabs.py`
reserves the Channels layer for "W4," and `session_sharing` was **renamed from
`sessions`** specifically "to free that name for the live-session harness."

---

## 2. Target architecture

```
Browser (canopy-web SPA — or ace-web SPA as a client)
        │  WebSocket (live) + REST (commands)
        ▼
┌──────────────────────────────────────────────────────┐
│ canopy-web  (ASGI: uvicorn + Django Channels)          │
│                                                        │
│   realtime  ──pushes──►  TurnEvent ledger appends      │  new · framework
│   sessions  ──"send"──►  enqueues harness Turn         │  new · framework
│   harness   (queue · claim · lease · ledger · links)   │  exists · framework
│   Redis     (channel layer · presence · cache)         │
└──────────────────────────────────────────────────────┘
        ▲  claim Turn · append TurnEvent  (REST, + WS for cancel)
        │
┌───────┴────────────────────────┐
│  canopy cloud runner            │  new · its OWN ECS service
│   kind=cloud daemon             │
│   ports ace-web CLIBackend pool │
│   spawns `claude -p` stream-json│
│   SessionLink affinity          │
└─────────────────────────────────┘
```

### 2.1 The unified data model (the crux of "unify on the ledger")

- **`Session`** — a durable conversation thread. Framework, **agent-agnostic**: it
  carries opaque product metadata (ace-web's `opp_slug` / `opp_run_id` /
  `opp_step_skill` become generic string labels the framework never interprets).
- **`Draft`** — the shared, co-edited outgoing message (multiplayer input model).
  A "send" commits the active Draft.
- Committing a Draft **enqueues a harness `Turn`** — the durable execution
  envelope: `queued → claimed → leased → executing → done/failed`, reclaimable if
  a runner dies.
- The cloud runner executes `claude -p` and **appends the assistant + tool stream
  to the existing `TurnEvent` ledger** — no second streaming engine is introduced.
- The **`realtime`** layer fans ledger appends (+ presence + draft events) to the
  session's WebSocket group.
- **`Message`** rows are a **projection** over the session's ordered Turns +
  TurnEvents — the durable transcript, *derived* from the ledger, not primary.

Consequence: "chat" and "cloud agent execution" become the same thing. You get
durable execution (lease/reclaim survives any deploy), the append-only ledger the
control plane already trusts, and the cloud-runner path — all without a parallel
system.

### 2.2 What ace-web keeps vs. sheds

- **Keeps (product):** opp workbench UI, Drive tool integration, the decision-edit
  buffer, opp↔session linkage, and any opp-specific chrome. These ride as opaque
  session/Turn metadata into canopy.
- **Sheds (now canopy's job):** its Django Channels stack, `Session`/`Message`/
  `Draft` models, `turn_driver`, and the `CLIBackend` in-process subprocess pool.
  ace-web stops running `claude -p` in its own container entirely.

---

## 3. The program — four sub-projects

This is a program, not one spec. Each SP is its own spec → plan → build. The risky
architecture (unify-on-ledger + warm cloud runner + live stream) is **proven by the
end of SP2**, not deferred to the finish.

### SP1 — Realtime substrate  *(build first)*
Stand up the reserved Channels + Redis channel layer, a generic WebSocket consumer,
the ASGI + ALB websocket wiring, and push the **existing** `TurnEvent` ledger live
to a per-turn / per-session group.
**Deliverable:** `/supervisor` and the turn views go live (no more polling).
**Why first:** standalone value, needs no ace-web, lowest risk, and it is a hard
prerequisite for every later slice.

### SP2 — Cloud runner + unified execution  *(vertical slice)*
The `kind=cloud` warm runner service (ported subprocess pool) claims a Turn, runs
`claude -p`, and appends TurnEvents; plus the minimal chat front-door — a `Session`,
a "send" that enqueues a Turn, and a single-user live view over SP1's transport.
**Deliverable:** chat with a *canopy* agent whose execution runs on the cloud
runner, streamed live end-to-end.
**Why here:** proves the whole architecture — unify-on-ledger, the warm cloud
runner, and realtime — together, early.

### SP3 — Multiplayer
Co-edited `Draft` (version guard + derived idle soft-lock), Redis-HASH presence
with debounced DB writes, participants/roles, full-state snapshot on (re)connect,
stream-survives-disconnect, and cross-process stop.
**Deliverable:** teammates co-drive a session (full ace-web parity).

### SP4 — ace-web as first consumer
ace-web's opp workbench points at canopy's chat/realtime API and enqueues Turns to
canopy's cloud runner; it retires its own Channels / Session / `CLIBackend` stack.
Opp-specific concerns stay in ace-web and travel as session/Turn metadata.
**Deliverable:** ace-web cloud runs go through canopy — no in-container `claude -p`,
no deploy-kills, independent scaling.

---

## 4. Framework/product boundary

Enforced by `tests/test_architecture_boundary.py` (pure `ast`, in CI) against
`ARCHITECTURE.md`. The two new apps are **generic substrate → framework tier**:

- `realtime` (SP1) and `sessions` (SP2/SP3) are classified **framework**, added to
  both the boundary test's framework set and the `ARCHITECTURE.md` tier table.
  (`test_every_app_is_classified` fails CI on any untiered new app.)
- They may import only framework apps (`harness`, `agents`, `common`, `workspaces`,
  `tokens`, …) — never product apps.
- ace-web's opp coupling never enters canopy: it arrives as opaque session/Turn
  metadata, so the framework stays agent-agnostic and liftable.

The name `sessions` is the one reserved by the `session_sharing` rename — use it for
the live-session app.

---

## 5. Decisions deferred to each sub-project's spec

Recorded here so they are not lost; each is resolved when its SP is brainstormed:

- **Cross-app auth / tenancy / CORS** — ace-web → canopy over PATs (both apps
  already have a PAT model). Which token, which workspace, CORS/WS-origin policy.
- **Turn targeting for chat** — a new `session` target on `Turn`, vs. reuse
  agent/project targeting plus a `session_id`. (`Turn` currently enforces agent XOR
  project.)
- **Per-session execution lock** — interactive chat wants one executing turn *per
  session*, not the harness's per-agent `one_executing_turn_per_agent`. New partial
  index vs. reuse.
- **Message projection mechanics** — materialized rows kept in sync from the ledger
  vs. derived-on-read; how tool_use/tool_result pairing and cost land.
- **Cloud runner internals** — credential staging in the container (ace-web's
  staged-`$HOME` + symlinked `~/.claude`), warm-pool sizing / idle reaper /
  autoscaling, and whether/when to add optional Fargate task-per-run isolation.
- **ALB / infra** — websocket target-group config, sticky-vs-stateless now that the
  pool lives on the runner tier, ECS service definition for the runner.

---

## 6. Relationship to existing canopy work

- **`apps/harness/`** — reused as-is for the queue/claim/lease/ledger. Extended
  (not replaced) for session-scoped execution and the realtime push.
- **`apps/agent_runs/` + `packages/canopy_agent_runs`** — the run→step→verdict read
  model is orthogonal; a cloud run can still surface as an `AgentRun`. No change
  required for SP1–SP3; revisited in SP4 if ACE run structure should project here.
- **`packages/canopy_runner`** — the existing polling daemon is the seed of the
  cloud runner; SP2 grows it a cloud execution path (ported subprocess pool)
  alongside its current emdash/CDP path.
- **`apps/agents/`** — unchanged; `AgentTurn` (packaged report) stays distinct from
  the harness `Turn` (execution envelope), as today.
