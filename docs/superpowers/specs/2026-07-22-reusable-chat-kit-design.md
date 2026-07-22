# Reusable Chat Kit — the frontend the multiplayer backend has been waiting for

**Status:** design (brainstormed 2026-07-22)
**Program:** Wave 4 realtime/chat (SP1–SP4). This is the missing **chat UI slice** SP2/SP3
both explicitly deferred, plus the protocol alignment that makes ace-web adoption (SP4) a swap.

## Motivation — the reframe

The multiplayer chat **backend** is already built, tested, and live in canopy-web
(`apps/chat` + `apps/realtime`): `Session`/`Message`/`Draft`/`SessionParticipant`,
co-edited drafts (version guard + derived soft-lock), cache-backed presence, roles, and a
per-session `SessionConsumer` at `ws/chat/{id}/` that broadcasts presence + draft edits +
streamed turn output. Real cloud-runner execution is even routed (session-capable runners
claim session turns); the default just uses an inline stub (`CHAT_STUB_EXECUTOR=True`).

**What is missing is the entire frontend.** Nothing on the client talks to that socket.
"The chat we have" is three unrelated ad-hoc surfaces (the `/share` transcript viewer, the
supervisor `OpenSessions` 10s-poll tail, the dispatch-only `Composer`) with three different
message shapes and no shared component. The streaming hook `useLiveTurn` exists but is
consumed by nothing. There is no chat component in `canopy-ui`.

ace-web, by contrast, has a **complete, battle-tested chat frontend** (`useSessionSocket` +
`sessionReducer`, `MessageList`/`MessageItem`/`ToolCallPair`, `SendBox` with soft-lock +
take-over, `PresenceChips`, `pairToolMessages`, `drafts.ts`) speaking a richer protocol than
canopy's consumer currently emits. canopy's backend was ported *from* ace-web; the frontend
never came over.

## The committed constraint: one implementation, ace-web consumes it

We have committed to **ACE → Canopy** (the framework-harvest thesis). So the reusable kit is
not merely "reusable across canopy surfaces" — it must be the artifact **ace-web adopts** so
the fleet ends with *one* chat implementation, not two. This is a first-class design goal,
and it is why we align *up* to ace-web's protocol (below) rather than down to canopy's lean
frames: ace-web already speaks the richer contract, so adoption is a swap, not a rewrite.

## Decision 1 — Canonical protocol = ace-web's contract

Adopt ace-web's WebSocket contract (its `types.ws.ts`, lines 16–132: enums, `Message`,
`Draft`, `Participant`, `SessionState`, `WsAction`, `WsEvent`) as the **canonical wire
format**, published inside `canopy-ui`. Port the ace client stack ~verbatim and **upgrade
canopy's `SessionConsumer` up to that contract**, rather than dumbing the client down to
canopy's single-`chat.turn_event` model.

Why: (a) maximum reuse — reducer/types/hooks/components port nearly as-is; (b) it is the
real-time win — token-by-token `chat.delta` streaming *is* "more real-time chat"; canopy's
whole-message model cannot stream tokens; (c) it stays true to "unify on the ledger" — the
`TurnEvent` ledger remains source of truth and the `SessionConsumer` *translates* ledger
events into the richer `chat.*` vocabulary per connection; (d) it makes ace-web adoption a
swap because both then speak one contract.

The canonical protocol (server→client events, client→server actions, snapshot shape) is the
ace-web contract as documented in the protocol diff, with these being the frames both ends
implement:

- **client→server:** `chat.send`, `chat.stop {message_id}`, `draft.update {version, body}`,
  `draft.take_over`, `draft.discard`, `presence.heartbeat`.
- **server→client:** `session.state` (snapshot), `session.error {code,message,detail?}`,
  `chat.stream_start`, `chat.delta {message_id,text}`, `chat.tool_use`, `chat.tool_result`,
  `chat.stream_complete {message_id,plaintext}`, `chat.stream_error`, `chat.stream_cancelled`,
  `draft.updated`, `draft.lock_changed`, `draft.committed`, `draft.discarded`,
  `presence.joined {user_id,email,display_name}`, `presence.left {user_id}`,
  `session.title_updated {title}` (optional).

## Decision 2 — The kit lives in `canopy-ui`, seams injected

`canopy-ui` (already `canopy-ui@0.3.0` on public npm) gains a **`./chat` subpath export**
holding the whole reusable chat kit. Nothing canopy-app-specific is baked into the kit — app
specifics are injected so both canopy-web AND ace-web can consume it:

- **Injected seams:** a `wsUrl`/socket-URL builder (each app owns its ws origin/base/auth
  convention), the `currentUserId` (sourced from each app's auth context — the canopy
  snapshot may or may not carry it), an optional REST `resolveIdentities` for participant
  chips, and an optional **`banner`/`disabledReason` slot** (ace needs its CLI-auth banner;
  canopy needs none) plus an `emptyState` slot (replacing ace's ace-specific `WelcomePanel`).
- **Left behind (not ported):** ace's `useCliAuthStatus` + CLI-auth banners, all opp/step
  coupling (`WorkbenchChatPane`, `discussStep`, `OppHeaderBreadcrumb`, `getLinkedChats`),
  `views/PresenceStrip`, and ace's `X-ACE-Workspace`/`csrftoken_ace`/`/auth/login` client
  specifics.

### Kit contents (`canopy-ui/src/chat/`)

Pure / zero-dep (copy ~verbatim from ace-web):
- `protocol.ts` — the canonical types (ace `types.ws.ts:16–132`). **Single source of truth.**
- `sessionReducer.ts` — pure, tested; `notifySessionsUpdated` becomes an injected callback.
- `drafts.ts` — `isDraftIdle`, `msUntilDraftIdle`, `IDLE_THRESHOLD_MS`.
- `pairToolMessages.ts` — tool_use↔tool_result pairing, `deriveToolStatus`, `toolPreview`.

Hooks (generic, URL/identity injected):
- `useSessionSocket({ path, wsUrl })` — reconnect/backoff, 20s presence heartbeat, optimistic
  debounced draft, pending-frame queue. Ported ~as-is.
- `useStickyBottom(dep)` — streaming-aware autoscroll. Copy verbatim.

Presentational components (props-in / callbacks-out, styled on canopy-ui tokens):
- `ChatPanel` — composes header (`ConnectionStatus` + `PresenceChips`) → scrollable
  `MessageList` → `SendBox`. Takes `state`, `connected`, `currentUserId`, action callbacks,
  and the optional `banner`/`emptyState` slots. No data fetching, no WS, no CLI-auth.
- `MessageList` / `MessageItem` / `ToolCallPair` — markdown via an injected/again-simple
  renderer; tool disclosure; streaming "thinking"/cursor affordances; neutral (non-red)
  error styling.
- `SendBox` — soft-lock gating (`canEdit`), take-over button, Enter-to-send, stop button,
  idle-tick timer. CLI-auth block removed / exposed as the `banner` slot.
- `PresenceChips`, `ConnectionStatus`.

## Decision 3 — Backend: upgrade `SessionConsumer` to the canonical protocol

canopy-web `apps/chat/consumers.py` (+ `serializers`, and the `apps/realtime`
`turn_events_appended` fan-out) change so the socket speaks the canonical contract:

- **Snapshot enrichment** — `session.state` carries `current_user_id`, full participant
  identity (`email`, `display_name`, `role`, timestamps), `active_draft` (id/slot/status),
  and richer `messages` (id/content/status/timestamps). (New serializers; the DB already has
  the data.)
- **Frame alignment** — send verb `draft.commit`→**`chat.send`**; `draft.conflict`/
  `draft.locked` → route via the canonical `draft.*`/`session.error` names; add
  `draft.committed`/`draft.discarded`/`draft.lock_changed`; accept `draft.update {version}`
  (canonical) alongside; error envelope `error`→**`session.error`** with `{code,message}`.
- **Streaming translation** — the consumer's group handler translates each `TurnEvent`
  ledger row into the canonical `chat.*` stream frames: `status(running)`→`chat.stream_start`,
  `assistant`→`chat.delta`/`chat.stream_complete`, `tool_start`/`tool_end`→
  `chat.tool_use`/`chat.tool_result`, `status(done)`→`chat.stream_complete`,
  `error`→`chat.stream_error`. **The ledger stays source of truth**; this is a per-connection
  presentation mapping, so `apps/realtime` fan-out remains generic.
- **Stop/cancel** — add a `chat.stop {message_id}` path (a `Turn` cancel), which canopy's
  consumer currently lacks.

Token-delta granularity is a *backend detail the client already tolerates*: with the stub
executor the consumer emits whole-message `chat.stream_complete` (no `chat.delta`), and the
reducer renders fine; true token `chat.delta` streaming lands for free when a real
delta-emitting cloud runner replaces the stub (slice 3), with **no client change**.

## The thin app container (canopy-web)

A small canopy-web layer wires the kit: the route/shell, `getSession` meta, `currentUserId`
from `/api/me`, canopy's `wsUrl` builder, and a canopy `src/api/chat.ts`. This is the only
part that is *not* shared with ace-web; ace-web writes its own equivalently-thin container.

## Slice plan

1. **Foundation (this spec's build target).** The `canopy-ui/chat` kit + the `SessionConsumer`
   protocol upgrade + canopy `src/api/chat.ts` + a **standalone chat route** `/w/:ws/chat/:id`
   (create-or-open a chat `Session`, full `ChatPanel`). Backend = stub executor
   (whole-message streaming). Deliverable: a working, multiplayer-capable chat on canopy,
   proving the kit end-to-end against the already-built backend.
2. **Embed in supervisor.** Drop `ChatPanel` into the supervisor Sessions surface, killing the
   10s poll. Reconcile "supervisor sessions" (emdash/harness live-sessions) vs chat `Session`s
   — its own small design decision, deferred to that slice.
3. **Multiplayer + real execution.** Flip `CHAT_STUB_EXECUTOR` off with a session-capable,
   delta-emitting cloud runner → true token streaming; validate two-browser co-edit/presence;
   embed the kit in the agent workspace.

## ace-web adoption path (explicit — the whole point)

- **Stage A — frontend DRY (cheap, low risk).** ace-web `npm i canopy-ui@<next>` and replaces
  its local `ChatPanel`/`useSessionSocket`/`sessionReducer`/`drafts`/`pairToolMessages`/
  message components with the kit, rendering against **ace-web's own backend** (both speak the
  canonical protocol). ace-web keeps its CLI-auth banner by passing it into the `banner` slot.
  One chat frontend, two consumers.
- **Stage B — backend cutover (SP4, already committed).** ace-web retires `apps/sessions` and
  points the same kit at canopy's hosted chat API + `SessionConsumer` + cloud runner; opp
  linkage rides as opaque `Session.metadata`. No kit change.

Because the kit and the protocol have a single home (`canopy-ui`), there is never a second
divergent implementation to reconcile — the reason we align to ace's protocol now.

## Isolation & boundaries

- **Framework/product:** the kit is generic (framework-tier concept); it imports nothing
  product-specific. `apps/chat` + `apps/realtime` remain framework-tier (enforced by
  `tests/test_architecture_boundary.py`).
- **The reusable/app seam is the injected props.** The kit knows nothing about routes, auth,
  workspace headers, or execution model — those are container concerns.
- **The ledger stays the source of truth.** Streaming vocabulary is a presentation mapping in
  the consumer, not a second execution/stream engine.

## Testing (slice 1)

- Port ace's `sessionReducer` unit tests; add canopy protocol-mapping tests for the
  `TurnEvent`→`chat.*` translation in the consumer.
- Backend: extend `tests/test_chat_session_consumer.py` for the enriched snapshot + canonical
  frame names + the stream translation + the `chat.stop` path.
- Frontend: `pairToolMessages`, `drafts` idle math, `useSessionSocket` reconnect/optimistic
  draft (jsdom), and a `ChatPanel` render smoke test.
- Full-stack: an authenticated `ws/chat/{id}/` round-trip proving snapshot → draft.update →
  chat.send → streamed reply through the canonical frames.

## Deferred / open questions

- Supervisor emdash-session vs chat-`Session` reconciliation (slice 2).
- Real token-delta emission from the cloud runner (slice 3; runner change, SP2b-adjacent).
- `chat.stop`/cancel semantics on a harness `Turn` (canopy has no cancel today; a `Turn`
  cancel + a `chat.stream_cancelled` mapping).
- Presence backend atomicity (canopy's cache get→mutate→set lossiness; prod Redis HASH
  field-atomics — pre-existing, tracked in `apps/chat/presence.py`).
- Cross-app auth/CORS/WS-origin for Stage B (the long-deferred SP4 items).
- Markdown renderer: reuse an existing canopy renderer vs. bundle one in the kit.
