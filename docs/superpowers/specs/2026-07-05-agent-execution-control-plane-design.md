# Agent Execution Control Plane — laptop-first runners, cloud fallback, Slack surface

**Date:** 2026-07-05
**Status:** Draft for review
**Owner:** Jonathan Jackson
**Prior art researched:** OpenClaw, omnara, coder/agentapi, HumanLayer (classic + hld), vibe-kanban, OpenHands, claude-squad, Anthropic claude-code-action / Claude Code on the web. Findings inline, tagged `[project]`.

## 1. Problem

Canopy's agents (Echo and the growing fleet) execute only when Jonathan's laptop is awake and someone manually runs a turn. Meanwhile:

- **Anthropic policy risk.** The May 13 announcement (paused June 15) signals the direction: `claude -p` / Agent SDK / third-party usage moves to a separate metered credit; subscription limits get reserved for *interactive* use. Canopy-web's `AI_BACKEND=cli` (`claude -p` + setup-token OAuth) is exactly the at-risk pattern. The durable postures are (a) interactive sessions on the laptop and (b) API-key billing in the cloud.
- **Visibility is the operating requirement, not a nice-to-have.** Running agents on OpenClaw failed for us because we couldn't see what they were doing. Research confirms this is OpenClaw's #1 ecosystem-wide failure (an aftermarket of observability tools exists because of it; they bolted on a task ledger + OTel only after the backlash). Design consequence: **the run ledger is built first, not last.**
- **Work should not depend on one machine.** When the laptop is closed, turns should fall back to an executor we control in the cloud — with the same visibility.

## 2. Goals / non-goals

**Goals**

1. Command lands in canopy-web → an agent turn executes deterministically on the best available executor — within ~2 minutes in Phase 0 (runner poll + emdash's 60s scheduler tick), trending to seconds once the emdash HTTP API/CLI lands upstream.
2. Laptop-first: when the laptop is alive, turns run as **visible, intervenable interactive `claude` sessions inside emdash** (subscription economics, full-mode TUI — mechanically identical to typing in a terminal).
3. Cloud fallback: when the laptop is not available, turns run in a **clean-user-space container on ECS** under an API key (the sanctioned always-on path).
4. Every turn produces a message-level ledger watchable live in canopy-web, and (Phase 1+) mirrored into a Slack thread with question/approval buttons.
5. All control-plane state in Postgres; any web replica can serve. No singleton daemon. `[avoid: OpenClaw]`
6. Framework-tier: nothing here imports product apps; the whole substrate is harvestable.

**Non-goals (v1)**

- Multi-tenant runner fleets beyond Jonathan's own machines/workspaces (models carry `workspace` FKs; enforcement comes with the broader tenancy work).
- Raw terminal streaming to the browser (ledger-level visibility first; relay channel is Phase 3). `[omnara relay]`
- Server-initiated SSH execution (see §6.3 — SSH machines run the same dial-out runner instead).
- Replacing `/api/ai/*` product AI backend. This spec is about *agent turns*, not the in-app chat features.

## 3. Design principles (distilled from research)

1. **Ledger-first.** Every detached work item is a row with `queued → running → terminal` states before anything else is built. `[OpenClaw tasks ledger — shipped late, should've been first]`
2. **Executors dial out; the control plane never dials in.** No inbound ports on the laptop, no server-held SSH keys. `[OpenClaw nodes; omnara]`
3. **Pairing + per-runner credentials, never shared secrets.** OpenClaw's ~1,800 exposed gateways were default/shared-token misconfigurations. Runners authenticate with scoped PATs (existing `apps/tokens`).
4. **Deterministic routing.** Which runner executes a turn is config + liveness, never an LLM decision. `[OpenClaw bindings]`
5. **Server-enforced capabilities and frozen approvals.** A runner's declared capabilities are claims; the server allowlist decides. An approved action executes the *stored* plan, not a re-read of caller fields. `[OpenClaw exec approvals]`
6. **One run per agent-session at a time; bounded global concurrency.** `[OpenClaw lanes; omnara]`
7. **Content from transcripts, state from signals.** Never screen-scrape for content; tail Claude's own JSONL (`--session-id` makes the path deterministic). Screen/process signals only for idle/permission detection. `[omnara claude_wrapper_v3; agentapi as the cautionary 3k-line alternative]`

## 4. Architecture overview

```
                       ┌────────────────────────────────────────────┐
  Slack ── events ────▶│  canopy-web (Django, Postgres)             │
  Web UI ─────────────▶│  apps/sessions (NEW, framework tier)       │
  Board commands ─────▶│   Turn ─ TurnEvent ─ Approval ─ Runner     │
  Cron (later) ───────▶│   Router (claim/lease, policy)             │
                       └───────────────▲────────────────────────────┘
                          poll/claim/heartbeat/events (HTTPS + PAT)
              ┌────────────────────────┼─────────────────────────┐
              ▼                        ▼                         ▼
   canopy-runner (laptop)    canopy-runner (ECS task)   canopy-runner (any box
   → emdash automation_runs  → claude in clean userspace  via SSH-installed
     INSERT → visible PTY      w/ API key, worktree/run    daemon, dial-out)
     session in emdash         per turn
```

One runner binary/package, three deployments. The control plane cannot tell them apart except by declared kind and capabilities.

## 5. Control plane (`apps/sessions`, framework tier)

New Django app (the "live-session harness" the `session_sharing` rename freed this name for). Pydantic-first Ninja routers like every other app. Nothing imports product code.

### 5.1 Models

**Runner** — the executor registry. `[omnara agent_instances + OpenClaw node registry]`
- `id`, `workspace` FK, `name`, `kind` (`emdash` | `cloud` | `remote`), `capabilities` JSON (declared; e.g. `{"agents": ["echo"], "worktrees": true}`), `status` (`online` | `stale` | `disconnected` | `degraded` | `retired`), `last_heartbeat_at`, `paired_at`, `token` FK → PersonalToken, `meta` JSON (emdash schema version, host, etc.).
- Liveness is a *written* heartbeat, not inference: the runner POSTs every ~30s; `online` = heartbeat < 90s. `stale` ≠ `failed` — the UI says "laptop asleep," not "crashed." `[omnara]`
- `degraded` = runner alive but refusing work (e.g. emdash schema-version mismatch, §6.1).
- Pairing: a runner is created by an authenticated human (mint PAT, register runner). Capability changes require re-approval (server stores the approved capability set; a heartbeat declaring more than approved → `degraded` + notify). `[OpenClaw pairing binds the command surface]`

**Turn** — one unit of agent work. Generalizes "drain the board" beyond `AgentTaskCommand`.
- `id` (uuid), `workspace` FK, `agent` FK, `origin` (`board` | `api` | `slack` | `cron` | `manual`), `origin_ref` (e.g. command ids, slack thread), `prompt` (what the session is seeded with — usually just `/canopy:drain-turn <agent>`), `routing` (`prefer_local` | `local_only` | `any`), `idempotency_key` (unique; every side-effecting create carries one `[OpenClaw]`),
- lifecycle: `queued → claimed → running → needs_human → done | failed | lost`, with `claimed_by` FK → Runner, `claimed_at`, `lease_expires_at`, `started_at`, `finished_at`, `session_id` (the claude `--session-id`, set by the executor), `result_note`.
- `needs_human` = an unresolved Approval or question exists (maps to the agent's existing needs-you semantics).
- **Lease semantics:** claim sets a TTL (default 15 min, renewed by runner progress events). Expired lease → `lost` → router re-queues per `routing`. A laptop-restart mid-turn is therefore self-healing. Serialization rule: **at most one non-terminal Turn per agent** (OpenClaw's session lane, expressed as a partial unique index).
- Relationship to existing models: `AgentTaskCommand` stays the *product-visible* command queue; a Turn is the *execution envelope*. The drain-turn skill reads pending commands and applies them exactly as today — Turns don't replace commands, they carry the session that processes them. A Turn also creates an `agent_runs` Run so the existing run read-model UI renders it.

**TurnEvent** — append-only ledger. `[OpenHands event stream; agentapi replay-on-subscribe]`
- `turn` FK, `seq` (monotonic per turn), `ts`, `kind` (`status` | `assistant` | `tool_start` | `tool_end` | `question` | `approval` | `error` | `heartbeat`), `payload` JSON (secrets masked at write time `[OpenHands]`).
- Producer: the runner tails the session's JSONL transcript and POSTs batches (content from transcript, never screen `[omnara]`).
- Consumer: `GET /api/sessions/turns/{id}/events?after=<seq>` — replay from cursor, then poll/SSE. Client reconnect is free because the cursor is the contract. SSE upgrade (Postgres LISTEN/NOTIFY) is an optimization, not the MVP contract.

**Approval** — human-in-the-loop, first-class row. `[HumanLayer hld]`
- `turn` FK, `tool_use_id` (correlates to the transcript's tool_call event so UIs render it inline), `tool_name`, `frozen_input` JSON (**the server dispatches this stored plan on approve; later edits to the request are ignored** `[OpenClaw TOCTOU defense]`), `status` (`pending` | `approved` | `denied` | `expired`), `options` JSON (`ResponseOption{name, title, prompt_fill}` — deny reasons as buttons, not just approve/deny `[HumanLayer]`), `responded_by`, `comment`, `slack_message_ts`.
- Creation path: the executor injects a canopy **MCP permission shim** and launches claude with `--permission-prompt-tool` pointing at it; the shim POSTs the Approval and long-polls for resolution, then returns Claude Code's `{"behavior":"allow"|"deny", ...}` contract. This is the proven recipe (HumanLayer hld, omnara headless, vibe-kanban all converge on it). In emdash PTY sessions, permission prompts surface in the TUI as usual — the shim applies to auto/unattended modes.
- Auto-approve modes copied from hld: `skip_permissions` **with expiry** (swept by a monitor), and `auto_accept_edits` (Edit/Write only).

### 5.2 Router

Pure function, evaluated on: turn enqueue, heartbeat transitions, lease expiry.

1. Eligible runners = `online` ∧ capability covers the agent ∧ not `degraded`.
2. Order by kind priority from the agent's policy (default `emdash > remote > cloud`).
3. `local_only` turns wait (state `queued`, surfaced in UI/Slack as "waiting for laptop") rather than falling back.
4. Assignment is **pull-based**: the router marks the turn offered to a runner kind; runners long-poll `GET /api/sessions/runners/{id}/work` and claim atomically (`UPDATE … WHERE status='queued' RETURNING`, idempotency key honored). No server→runner push needed; survives NAT/ECS/SSH identically. `[omnara long-poll with read cursor]`
   - *Considered and rejected for v1:* omnara's webhook-behind-Cloudflare-tunnel push (lower latency but adds a tunnel dependency and an inbound surface on the laptop; our 15–30s poll on top of emdash's 60s tick is already inside the latency budget).

### 5.3 API surface (new router mounted at `/api/sessions/`, all PAT/session-authed)

- `POST /runners/` (pair), `POST /runners/{id}/heartbeat`, `GET /runners/{id}/work` (long-poll + claim), `POST /runners/{id}/degraded`
- `POST /turns/` (enqueue; idempotency key required), `GET /turns/`, `GET /turns/{id}`, `POST /turns/{id}/events` (runner batch-append), `GET /turns/{id}/events?after=`, `POST /turns/{id}/finish`
- `POST /approvals/{id}/respond` (web + Slack interactivity both land here; responder allowlist enforced server-side `[HumanLayer]`)

## 6. Executors — one runner package, three deployments

A small Python package (`canopy_runs` sibling, installable): heartbeat loop, work long-poll, transcript tailer, event batcher, and per-kind execution adapters. Crash-safe: running-turn state serialized locally; on restart the runner rehydrates and re-attaches instead of assuming a clean slate. `[claude-squad pattern — pattern only, AGPL]`

### 6.1 Laptop / emdash adapter (Phase 0 — mechanism proven 2026-07-05 on this machine)

- launchd agent runs the runner. On claimed turn: **INSERT one `queued` row into emdash's `automation_runs`** (snapshots copied from a pre-created, cron-less "canopy — automated turn execution" automation); emdash's own scheduler picks it up on its ≤60s tick and runs the entire provisioning + session spawn through its own code path — the experiment produced a real `type=pty` interactive claude session, visible and intervenable, in ≤60s.
- Immediately after emdash creates the task, flip `tasks.type` `automation-run → 'task'` (byte-identical to emdash's own convert action) so turns appear in the project sidebar as they land; they always appear live under Automations regardless.
- **Schema guard:** on startup and before every write, compare `__drizzle_migrations` max id against the vetted version; mismatch → report `degraded`, notify, stop writing. Degrades to "Run now by hand," never corrupts.
- Turn completion: the session itself finishes via the drain-turn skill (applies commands, POSTs `/turns/{id}/finish`). The runner's transcript tailer provides the ledger and idle detection (output-stability window `[agentapi]`).
- **Upstream migration path:** emdash #1995 (local HTTP API for task creation — upvoted) or the #2321 CLI replaces the INSERT with a POST/exec; adapter interface unchanged. We optionally contribute the automations `precondition`/webhook trigger upstream.

### 6.2 Cloud adapter — clean user space on ECS (Phase 2)

- A `canopy-cloud-runner` ECS service on the existing labs cluster: one container, **non-root dedicated user**, the same runner package, `ANTHROPIC_API_KEY` from Secrets Manager. Separate trust domain per OpenClaw's own guidance: hostile-user isolation comes from OS-user/host separation, not container-per-session cleverness.
- Per turn: `git worktree add` (or fresh shallow clone) with deterministic branch `canopy/<agent>-<short-turn-id>` `[vibe-kanban]`; launch `claude -p --output-format stream-json --session-id <turn-session>` (or the Agent SDK — same billing surface; pick whichever streams cleaner at build time) with the MCP permission shim as `--permission-prompt-tool`; tail transcript → TurnEvents.
- Git credentials: scoped deploy token; push restricted to the turn's branch (credential lives outside the agent's env where feasible). `[Anthropic cloud pattern, simplified]`
- Readiness/health: container heartbeat is the same runner heartbeat; ECS task stop mid-turn = lease expiry = `lost` → re-route. `[OpenHands 503→paused analog]`
- Visibility parity: cloud turns are watched in canopy-web's run view (ledger replay + live tail) — same rows the emdash leg writes.

### 6.3 Remote machines ("SSH") adapter (Phase 3)

Decision: **no server-initiated SSH.** Any extra machine gets the same runner package installed (one-line installer over SSH is fine as a *provisioning* step) and dials out like every other runner, `kind=remote`. Rationale: no inbound ports, no server-held SSH keys, one protocol to maintain. `[OpenClaw nodes: outbound-only clients]`

## 7. Slack integration (Phase 1)

**Agents are first-class Slack identities: `@echo`, `@eva` — never `@canopy echo`.** Slack permits one bot identity per app, so each agent gets its own lightweight Slack app, all sharing canopy-web's endpoints. A thin `slack.py` module inside `apps/sessions` handles them all (extractable to `apps/channels` if a second channel ever appears).

- **Per-agent app provisioning:** agent Slack apps are generated from one manifest template via Slack's App Manifest API (name, avatar, scopes, shared request URLs) — the agent factory mints `@<agent>` when an agent is created; no manual admin clicking. Per-app credentials (signing secret, bot token, `api_app_id`, `bot_user_id`) live in a `ChannelIdentity` row keyed to the agent, secrets encrypted at rest.
- **Disambiguation:** events arrive at per-app URLs (`/api/sessions/slack/events/<agent-slug>`), so signature verification is unambiguous and the agent is known before any parsing; the payload's `api_app_id`/`bot_user_id` is cross-checked against the `ChannelIdentity` row.
- **Addressing:** `@echo …` in any shared channel or a DM to @echo routes straight to Echo — a direct mention *is* the binding, top of the specificity ladder. Channel-default bindings (below) still cover "posts in `#echo-ops` without a mention." When several agent bots share a channel, each app receives channel messages independently; an agent ignores messages that neither mention it nor match one of its bindings, so exactly one Turn is produced.

- **Thread-per-turn.** `slack_thread_ts` stored on the Turn at first notification; every status change, question, and approval posts into that thread. `[HumanLayer thread_ts pinning]`
- **Sticky status message** edited in place (checklist: queued → claimed by <runner> → running → n commands applied → done), not 20 posts; doubles as audit trail. `[claude-code-action sticky comment]`
- **Approvals/questions as Block Kit buttons** rendered from `Approval.options`; a single interactivity endpoint resolves payloads into `POST /approvals/{id}/respond`; approver allowlist by Slack user ID enforced server-side; resolved `slack_message_ts` recorded for audit. Terminal message carries "View turn" (canopy-web run URL) buttons. `[HumanLayer + Anthropic @Claude]`
- **Inbound (Phase 1.5):** `@<agent> …` mention or DM to the agent's bot → `POST /turns/` with `origin=slack`, `origin_ref={channel, thread_ts}`; replies stream back into the thread (edit-in-place draft mode `[OpenClaw slack streaming]`). Routing = an ordered binding table (channel-ID-keyed — IDs validated at write time; name-based keys silently fail `[OpenClaw footgun]`) with a specificity ladder (thread > channel > team > default).
- **Needs-you mirror:** `needs_human` turns and stale-runner transitions DM Jonathan ("Echo is waiting on an approval — laptop asleep, holding turn" / buttons inline).

## 8. Failure handling

| Failure | Detection | Behavior |
|---|---|---|
| Laptop closes mid-turn | lease expiry (no renewal) | turn `lost` → re-queued per `routing`; Slack thread notes the handoff |
| emdash updates schema | migration-id guard | runner `degraded`, no writes, notification; manual re-vet bumps the pin |
| Runner crash | missed heartbeats → `stale`/`disconnected` | router stops offering work; on restart runner rehydrates local state and reconciles in-flight turns |
| Claude session hangs | no transcript progress within idle window | runner emits `error` event; lease expires naturally; turn `lost` |
| Double execution | atomic claim + idempotency keys + one-non-terminal-turn-per-agent index | second claim loses the UPDATE race; duplicate enqueues collapse on the key |
| Approval raced/edited | frozen_input dispatched, not caller fields | post-approval edits ignored by construction |

## 9. Security

- Per-runner PATs (existing `apps/tokens`), scoped by pairing; no shared secrets anywhere in the protocol. Revoking the PAT retires the runner.
- Capabilities are claims; the server-stored approved set is the allowlist (two-gate rule).
- Approvals: frozen plans, server-side responder allowlists, full audit (who, when, via which surface).
- Cloud leg: dedicated OS user, secrets from Secrets Manager, scoped git credential, branch-restricted push, no product DB access from the runner (API-only).
- TurnEvent payloads secret-masked at write time.

## 10. Framework/product boundary

`apps/sessions` is framework-tier: it knows `agents`, `agent_runs`, `workspaces`, `tokens` — never product apps. The drain-turn *skill* (canopy plugin) is where product semantics live. `tests/test_architecture_boundary.py` gets the new app added to the framework tier table.

## 11. Phasing

- **Phase 0 — laptop loop (this repo + canopy plugin + runner package):** `apps/sessions` models/API (Runner, Turn, TurnEvent minimal), runner package with emdash adapter (poller, injection, schema guard, type-flip, heartbeat, lease), `drain-turn` skill, lean runner project dir. Exit criterion: post a board command with laptop open → visible emdash session executes and applies it in ≤2 min; close laptop → turn waits, states visible in canopy-web.
- **Phase 1 — Slack out + approvals:** thread-per-turn, sticky status, Approval model + MCP permission shim (web resolve, then Slack buttons), needs-you DMs.
- **Phase 2 — cloud fallback:** ECS runner, router fallback policies, scoped git creds, run-view live tail polish.
- **Phase 3 — reach:** inbound Slack turns, remote-machine runners, terminal relay channel `[omnara]`, teleport-style cloud→laptop handoff, emdash upstream API swap.

## 12. Open questions

1. Cloud runtime: `claude -p --output-format stream-json` vs Python Agent SDK — same billing, choose on streaming ergonomics during Phase 2 build (lean: SDK, it *is* the supported programmatic surface).
2. Does Phase 0 create `agent_runs` rows immediately, or wait for the Turn↔Run mapping to settle in Phase 1? (Lean: immediately, thin.)
3. Slack workspace constraints at Dimagi for per-agent apps — manifest-API app creation may require workspace-admin approval per app; confirm whether N agent apps are acceptable or Phase 1 starts with @echo only. Needs a check before Phase 1.
4. Whether to also PR the `precondition`/webhook trigger to emdash or ride #1995/#2321 — decide after watching those threads for a few weeks.
