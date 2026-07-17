# SP2 — Cloud Runner + Unified Execution (spine first)

**Status:** Draft for review · **Date:** 2026-07-16 · **Author:** Jonathan + Claude

> Sub-project 2 of the Wave 4 program
> (`2026-07-16-realtime-chat-cloud-runner-program-design.md`). Builds the unified
> chat-execution spine — a chat `Session` whose "send" enqueues a harness `Turn`,
> executed into the `TurnEvent` ledger, projected into `Message` rows, and streamed
> live over SP1's transport.
>
> **Split into SP2a (this doc, no deploy) and SP2b (deploy-gated).** SP2a proves the
> whole loop *in-process* with a **stub executor**; SP2b swaps the stub for ace-web's
> real `claude -p` subprocess pool running as a `kind=cloud` ECS service. This lets
> the architecture be built and fully tested now, leaving only the container/deploy
> for when infra is available.

---

## Decisions (made under "make your best call")

1. **A chat Session is a third `Turn` target** — `Turn` targets agent XOR project XOR
   **session**. A session turn gives each conversation its **own execution lane** via a
   new `one_executing_turn_per_session` partial-unique constraint, so two people
   chatting with the same agent in different sessions don't serialize behind
   `one_executing_turn_per_agent`. Tenancy derives from `session.workspace`.
2. **`Message` is a materialized projection** kept in sync from the ledger via the
   `turn_events_appended` signal SP1 already emits (not derived-on-read). Simpler to
   query and paginate; matches ace-web's transcript model.
3. **Stub executor first.** SP2a drives execution with a canned stub
   (`execute_turn_stub`) that appends assistant/tool events to the ledger — proving
   send→Turn→execute→project→stream end-to-end without a `claude` binary or a deploy.
   SP2b ports the real subprocess.

## Non-goals for SP2a (deferred)

- Multiplayer `Draft` / presence / participants → **SP3**.
- Real `claude -p` subprocess + the `kind=cloud` ECS service + `claim_next_turn`
  routing of session turns → **SP2b** (needs deploy). Session turns simply don't match
  existing runners' agent/project filters, so they wait harmlessly until SP2b.
- Token-delta folding in the projection → SP2b (the stub emits coarse events; the
  projection is one Message per assistant/tool event for now).
- A chat UI → later; SP2a is the backend spine (`useLiveTurn` from SP1 already streams
  a turn, ready to drive it).

---

## Architecture (SP2a)

```
POST /api/chat/{id}/send  (text)
   │  create user Message · enqueue session Turn (queued)
   ▼
harness Turn (target=session)  ──execute_turn_stub──►  TurnEvent ledger
   │                                                        │
   │  turn_events_appended signal (SP1)                     │
   ▼                                                        ▼
Message projection (assistant/tool rows)          realtime turn.{id} live tail (SP1)
   ▼
GET /api/chat/{id}  → session + projected transcript
```

- **`chat` app (framework tier, label `chat`).** Router mounts at **`/api/chat/`**.
  (Note: the app is `chat`, not `sessions` — Django's built-in
  `django.contrib.sessions` already owns the `sessions` app label, and
  `session_sharing` still owns the `/api/sessions` route. `chat` sidesteps both
  collisions and names the surface honestly.) Models: `Session`, `Message`.
- **`Session`** — `id` (uuid), `agent` FK (nullable — you chat *with* an agent, or an
  agent-agnostic session), `workspace` FK (tenant), `title`, `status`
  (`active`/`archived`), `created_by`, `cli_session_id` (continuity for SP2b),
  `metadata` JSON (opaque product linkage, e.g. ace-web's `opp_slug`), `created_at`.
- **`Message`** — `session` FK, `turn` FK (nullable — user messages have no turn),
  `turn_index` (monotonic per session), `role` (`user`/`assistant`/`tool_use`/
  `tool_result`/`system`), `content` JSON, `plaintext`, `created_at`. Unique
  `(session, turn_index)`.
- **`send_message(session, text, user)`** — creates the user `Message`, then
  `enqueue_turn(session=session, origin=api, idempotency_key=…, prompt=text)`.
- **Projection** — a receiver on `turn_events_appended`: for a turn with a
  `session_id`, materialize each assistant/tool event as a `Message` (next
  `turn_index`). Idempotent by `(session, turn_index)`.
- **`execute_turn_stub(turn)`** — `mark_running` → append a canned assistant event
  (+ optional tool pair) → `finish_turn(done)`. Stands in for the cloud runner.

### harness changes
- `Turn.session` FK → `sessions.Session` (nullable, string ref to avoid an import
  cycle; the FK lives on harness, service imports go sessions→harness).
- `turn_targets_agent_xor_project` → **exactly one** of {agent, project, session}.
- New `one_executing_turn_per_session` partial unique (session set, status in
  executing states).
- `enqueue_turn(session=…)` accepts the new target; session turns derive
  `workspace` from `session.workspace`.
- `Turn.target` / tenancy helpers updated for session turns.

---

## Testing (SP2a, all in-process)

- harness: session-target enqueue; the per-session lock serializes a session but two
  sessions run in parallel; existing agent/project turns unaffected (full harness suite
  stays green).
- sessions: `send_message` creates a user Message + a queued session Turn; the
  projection materializes assistant/tool events into ordered Messages; idempotent.
- stub executor: drives a queued turn to `done` with events on the ledger.
- integration: POST send → stub execute → GET session returns the full transcript in
  order; and (reusing SP1) the `turn.{id}` socket streams the same events live.
- boundary: `sessions` classified framework; imports only framework apps.

## SP2b (deploy-gated follow-up, documented here for the seam)
Swap `execute_turn_stub` for a `kind=cloud` runner that claims session turns and runs
ace-web's ported `claude -p` stream-json subprocess pool, appending real
assistant/tool events (same ledger, same projection, same live tail). Adds
`claim_next_turn` routing for session turns + `SessionLink` affinity + the ECS service
+ credential staging. No change to the SP2a data model or API.
