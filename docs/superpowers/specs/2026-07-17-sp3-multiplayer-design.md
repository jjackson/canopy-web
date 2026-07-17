# SP3 — Multiplayer chat

**Status:** Draft for review · **Date:** 2026-07-17 · **Author:** Jonathan + Claude

> Sub-project 3 of the Wave 4 program. Ports ace-web's co-edited **Draft** +
> **presence** + **participants** onto the SP2 chat `Session`, over a new per-session
> WebSocket. Completes the "port multiplayer to canopy" half of the goal. Fully
> testable in-process (no deploy): the stub executor from SP2a still drives turns.

## Decisions (made under "make your best call")

1. **A per-session `SessionConsumer`** (`ws/chat/{session_id}/`, group `chat.{id}`) —
   SP1's `TurnConsumer` is per-*turn*; multiplayer needs a per-*session* socket that
   carries presence, the shared draft, and the streamed turn. On connect it sends one
   snapshot (participants + present users + active draft + recent transcript), then
   incremental events.
2. **Send stays REST *and* gains a WS `draft.commit`** — any participant can commit the
   shared draft to send. Both paths call `chat.services.send_message`; the assistant
   stream reaches every participant because SP1's fan-out also publishes **session-turn
   events to `chat.{session_id}`** (a small addition — the session socket forwards them).
3. **Presence via Django's cache** (`LocMem` in dev/test, the connectlabs Redis in
   prod) with a TTL heartbeat — the same behavior as ace-web's Redis HASH, but through
   the cache abstraction so it's testable without standalone Redis. Durable membership
   lives in `SessionParticipant`; presence is the ephemeral "who's here right now."
4. **Co-edited `Draft`** — one active draft per session, an optimistic `version` guard,
   and a **derived** soft-lock (holder = `last_editor` when edited within an idle window
   AND still present). `take_over` transfers it. No CRDT — coarse single-draft locking,
   right for a few teammates per session.
5. **Access** = the session's `created_by` (owner) **or** a workspace member
   (auto-joined as editor on first touch, like ace-web). Roles: owner / editor / viewer.

## Models (in `apps/chat`)

- **`SessionParticipant`** — `(session, user)` unique, `role`, `last_seen_at`. The
  durable membership + role authority.
- **`Draft`** — `session` (FK), `slot="next"` with a partial-unique "one open draft per
  session", `body`, `version` (int, optimistic guard), `last_editor` FK, `updated_at`.

## Services / modules

- `apps/chat/participants.py` — `ensure_participant`, `can_access`, `role_for`.
- `apps/chat/drafts.py` — `active_draft`, `update_draft(expected_version, body, editor)`
  (raises `DraftVersionMismatch`), `take_over(editor)` (raises `DraftLockHeld`),
  `commit_active_draft` → text for `send_message`. Soft-lock derived from
  `last_editor` + `updated_at` + presence.
- `apps/chat/presence.py` — cache-backed `touch(session, user)`, `leave`, `present_ids`,
  TTL + heartbeat window constants.

## Realtime additions (`apps/realtime`)

- `session_group(session_id)` + on `turn_events_appended`, if `turn.chat_session_id`,
  also publish `chat.message` frames to `chat.{session_id}` (alongside the existing
  `turn.{id}` tail).
- `SessionConsumer` in `apps/realtime/consumers.py`: connect gate (participant/member),
  snapshot, and actions `presence.heartbeat` / `draft.update` / `draft.take_over` /
  `draft.commit`, broadcasting `presence.joined|left`, `draft.updated`, `chat.message`.

## Testing (in-process)
- participants: auto-join a workspace member; non-member denied.
- drafts: version-guard mismatch; take-over transfers; commit yields the text.
- presence: touch/expiry/leave via LocMem cache.
- SessionConsumer: anon/non-member rejected; member gets snapshot; a `draft.update`
  from one socket broadcasts `draft.updated` to another; a `draft.commit` sends and the
  streamed assistant `chat.message` reaches both sockets (stub executes).

## Deferred
- Frontend `useChatSession` hook + a real chat UI (SP1's `useLiveTurn` + this hook are
  the pieces; a full UI is its own slice).
- Real `claude` streaming (SP2b) — orthogonal; the stub still drives turns here.
