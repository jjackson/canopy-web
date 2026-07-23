# Unified Canopy Runner Sessions — design

- **Date:** 2026-07-23
- **Status:** Approved (design); implementation plan to follow
- **Author:** Jonathan + Claude
- **Supersedes (in part):** the split between `apps/chat` (native web chat) and the `apps/harness` `EmdashSession`/`OpenSessions` live-session read-model.

## Problem

The supervisor **Sessions** tab today renders **two different session-chat surfaces back to back**, backed by two different models:

- **Native web chat** — `apps/chat.Session` (+ `Message`, `SessionParticipant`, `Draft`), a durable full transcript streamed over `ws/chat/{id}/` via `SessionConsumer`. Started in-app; a send enqueues a harness `Turn` that a session-capable runner executes, and the reply is projected back into the transcript.
- **Live emdash sessions** — `apps/harness.EmdashSession` (an ephemeral per-tick read-model the runner wholesale-replaces) surfaced by `OpenSessions`, with an inline "Continue this session…" box that dispatches a `Turn` and polls. Only a bounded **tail** (8 messages for the top 30 sessions) is reported up; the full `.jsonl` never leaves the laptop.

They are the *same concept* — a chat with a session running on a canopy runner — expressed as two subsystems. Execution already converged (chat runs through the runner too); only the **surfacing and the session model** are forked.

Two forces shape the fix:

1. **One model, one surface.** It is all **canopy runner sessions**, whether the runner is a local emdash daemon or a remote cloud runner. There should be one model and one chat surface, not two.
2. **Do not ship full history to the client by default.** The vast majority of sessions are never opened, and when they are (often from the phone) the **tail** is what's needed to continue. Server-side *storage* of full transcripts is fine where it makes sense (cloud/multiplayer already do it); the constraint is on **server→client** shipping. The native chat currently violates this — its REST load is uncapped and its WS snapshot ships the first 200 messages.

## Goals

- Collapse the two session models into **one first-class `Session`** ("a canopy runner session"), with the runner (local or cloud, any engine) as a first-class relation.
- **Tail-first loading everywhere** — the client gets a small tail by default, with explicit scroll-back and "load full session" backfill. The phone never receives a full transcript unasked.
- **Tiered persistence** — cloud-runner sessions persist their full transcript server-side as they run; local-runner sessions persist only a tail + rolling summary, with full history pulled from the runner on demand.
- **Fully live while viewing** — opening a session streams its events live (local or cloud) for as long as a viewer is attached; idle sessions cost nothing.
- **One unified Sessions surface** — a single list; every row opens into the same streaming `ChatPanel`; the bespoke `OpenSessions` continue-box is retired.
- **Keep the session system framework-generic** so ace-web can later drop its parallel chat and run through canopy's. (Not built here.)

## Non-goals

- **No backwards compatibility, no data migration.** Single user, no other consumers; existing chat `Session`/`Message` data may be wiped.
- **No ace-web integration in this spec** — only keep the boundary clean for it later.
- No multi-tenant/permission rework beyond what already exists (workspace membership + `SessionParticipant`).

## Design

### 1. The unified model

Promote `apps/chat` into the canonical session system — **rename the app to `apps/sessions`** (a framework app; the `sessions` name was freed earlier for exactly this). One model, evolved from `chat.Session`:

**`Session`** — *a canopy runner session*.
- Keeps: `id` (UUID), `workspace` (FK), `title`, `status`, `created_by`, `metadata`, timestamps, and the `Message` / `SessionParticipant` / `Draft` relations. A session **targets an agent or a project** (agent FK nullable + project reference, per #347 "chat with a project") — orthogonal to which runner backs it.
- Adds `origin`: `web` (started in-app) | `runner` (discovered on a runner) — provenance, independent of where it currently runs.
- Adds a one-to-one **`runner_binding`** (nullable — null when nothing is live). The binding **absorbs today's `EmdashSession` + `SessionLink`**:
  - `runner` (FK → `Runner`) — the runner currently backing the session.
  - `session_key` — an **engine-agnostic** handle the runner uses to resume/inject (renamed from `emdash_task`; the engine may not be emdash).
  - `tail` (JSON) — the last N conversational messages (rolling; the cheap read-model).
  - `summary` (text) — rolling context for rehydration (from `SessionLink.summary`).
  - `live_seen_at` — last report/heartbeat for this binding.

**`Runner`** (existing `apps/harness.Runner`, made first-class about its environment):
- Adds `kind`/`location`: `local` | `cloud` (with room for richer region/host labels).
- Adds `engine`: `emdash` today — nothing assumes it; a future local runner on a different engine is a new value.
- Keeps host/status/heartbeat/`paired_by`/workspace.

The **persistence tier is derived from `runner.kind`**, not stored on the `Session`. A session that migrates between runners just gets its `runner_binding.runner` repointed — no session-level state to reconcile, and N runners across mixed locales/engines fall out naturally.

The `EmdashSession` table is **dropped**. A runner-reported session that has no `Session` yet **auto-creates a lightweight one** (`origin=runner`, no `Message` rows, just a `runner_binding` with `tail`+`summary`). So every laptop session is a first-class `Session` from first report, and chat-started sessions are the same model.

### 2. Persistence tiers

- **Cloud-runner sessions:** full transcript persists server-side as it runs — reuse the existing ledger→`Message` projection (`turn_events_appended` → `project_events`). "Load full" is a DB query.
- **Local-runner sessions:** persist only `runner_binding.tail` + `summary`. **No `Message` rows** until a backfill.
- **On-demand backfill (promotion):** scroll-back / "load full session" on a local session makes the server ask the bound runner to ship history from its transcript; those messages are written as `Message` rows **once**, and the session is server-full thereafter. Runner offline → surface "full history unavailable — runner offline" (the tail still renders).

### 3. Loading contract (tail-first, every session)

Applies regardless of tier, so the phone never gets a full dump:
- **WS snapshot** (`SessionConsumer`) stops sending `messages[:200]` (head) and sends the **last N** (tail; start at ~20, tunable).
- **REST** `GET /api/sessions/{id}` stops being uncapped — returns the tail + a backward cursor.
- **Scroll-back** ("Load earlier") pages *backward* by cursor: server-full sessions page from the DB; local sessions trigger the runner backfill (§2).
- **"Load full session"** is the explicit escape hatch (server-full: one query; local: full runner backfill).

### 4. Liveness (attach / detach)

- Opening a session = joining its WS group (presence, already built). While ≥1 viewer is attached, the server signals the **bound runner** to **stream that session's events up live**; when the last viewer detaches, it stops. Cloud sessions already stream (the turn runs there); local sessions begin tailing their transcript on attach and stop on detach.
- Live events flow over the **same session WS** as `stream_start` / `delta` / `tool_use` / `tool_result` / `complete` frames — identical to today's chat stream, so the panel is agnostic to local vs cloud.
- Sending a message enqueues a `Turn` on the bound runner (`open_and_send` into `session_key`); its events stream into the panel already open.

### 5. The unified surface (frontend)

- **One Sessions list.** Chat-started and runner-discovered sessions are now the same `Session`, so the tab is a single list — no separate "Start a chat" panel *and* live-sessions list. Group/filter by runner (local/cloud) and running/idle; a per-row chip shows the runner + engine.
- **Every row opens into the streaming `ChatPanel`** (`canopy-ui/chat`). The `OpenSessions` inline continue-box is retired — a live session is just a session you click into and chat with.
- **ChatPanel gains:** tail-first load; a **"Load earlier"** (scroll-back) affordance and an explicit **"Load full session"**; a running/idle indicator; and a **runner-offline / history-unavailable** state for local sessions whose runner is unreachable (tail still shows).
- **"New chat with `<agent>` or project"** stays as the session-creation entry point (the standalone `Composer` widget was already removed in #347) — it creates a `Session` that gets bound to a runner.

### 6. Framework boundary (sets up later ace-web adoption)

Keep the whole system in a framework app (`apps/sessions`), agent-agnostic, talking the already-canonical `SessionConsumer` protocol (the `canopy-ui/chat` kit contract). That protocol is the seam ace-web adopts later to drop its parallel chat. **Not built now** — the design only avoids coupling to canopy product specifics so the door stays open. Both `sessions` and `realtime` remain framework apps; no framework→product imports.

### 7. Runner protocol changes (`packages/canopy_runner`)

The largest net-new work. The laptop runner must:
- Report an **engine-agnostic `session_key`** (rename from `emdash_task`) and its **`engine`** + **`kind`** on pairing/heartbeat.
- **Stream-on-attach / stop-on-detach:** on a server signal that a session has viewers, stream that session's transcript events up live; stop when it has none.
- **Backfill-on-demand:** answer a server request for a session's full (or older-than-cursor) history from its local transcript.
- Existing tail reporting (`read_recent_messages`, `session_tail_limit=8`, `session_tail_count=30`) stays as the cheap idle read-model that fills `runner_binding.tail`.

Requires a runner version bump + redeploy (launchd `com.canopy.runner`).

### 8. Migration & cutover (destructive, no compat)

- Rename `apps/chat` → `apps/sessions` (models, routers mounted at `/api/sessions`, `SessionConsumer`, `ws/` path). Note: `apps/session_sharing` (uploaded static transcripts) is unrelated and untouched.
- Add `Runner.kind` + `Runner.engine`; add the `runner_binding` (one-to-one on `Session`); **drop** `EmdashSession`; fold `SessionLink` into the binding.
- **Wipe** existing `Session`/`Message` data — acceptable to lose.
- Regenerate OpenAPI types (`npm run gen:api`); update the frontend `api/*`, the supervisor Sessions tab, and retire `OpenSessions`.
- Update CLAUDE.md + ARCHITECTURE.md (app rename, tier table).

## Testing

- **Backend:** tiered persistence (cloud writes `Message` rows as it runs; local writes none until backfill); the tail-first contract (WS snapshot returns last N, not head `[:200]`; REST capped + returns a cursor); backfill-promotion writes rows once and flips the session server-full; attach/detach toggles the runner stream signal; runner-offline → unavailable state; the architecture-boundary test still passes (no framework→product import) after the rename.
- **Frontend:** build/typecheck; one list renders both origins; ChatPanel tail-first + load-earlier/full controls; offline state renders.
- **Runner:** `session_key` reporting, stream-on-attach/stop-on-detach, backfill request/response.

## Tuning parameters (defaults, revisit after use)

- Tail size shipped to the client: **~20** messages (WS snapshot + REST default).
- Idle tail read-model: existing **8 messages / top 30 sessions** (`canopy_runner` config).
- Scroll-back page size: to be set in the plan (align with the existing `REPLAY_PAGE`/cursor conventions in `apps/realtime`).

## Open questions (resolve in the plan, not blocking)

- Exact `session_key` format and how a re-bound session (runner A → runner B) reconciles its `runner_binding` without losing the tail.
- Whether `Draft`/co-edit multiplayer applies to `origin=runner` sessions immediately or only to `origin=web` at first (YAGNI: likely web-first, presence for both).
- Backfill transport: reuse the runner control channel (`2026-07-22-runner-control-channel-design.md`) vs a dedicated request/response.
