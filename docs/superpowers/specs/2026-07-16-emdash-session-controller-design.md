# canopy-mobile: emdash session controller — see + continue open sessions

**Status:** design approved 2026-07-16 (Jonathan). Supersedes the "deferred" note in
`2026-07-14-canopy-mobile-design.md` § "The emdash session controller".

## The goal

From the phone, **see your open emdash sessions and continue one** — including the
session you are working in right now. This is the piece Jonathan said he'd "immediately
get frustrated" without: revise the canopy app from the phone while using it.

Concretely, two verbs:
- **See** — a list of open emdash sessions (project, task name, status, last-active),
  and on click-in, the session's **recent messages** (last ~8, NOT the full transcript).
- **Continue** — drop a prompt into a specific existing session, which lands in *that
  exact emdash task* on the laptop.

## The one hard constraint: the runner is the only bridge

The phone is a browser client of canopy-web (cloud). emdash and its sessions live only
on the laptop. **Nothing on the phone can reach the laptop directly.** The runner already
polls canopy-web on a ~20s tick and already reads `emdash4.db` (that is how
`emdash.task_state` decides session reuse). So the data flow is forced:

```
runner (reads emdash4.db)  --report-->  canopy-web (stores + serves)  <--list/continue--  phone
```

The runner **pushes** on its poll tick; there is no inbound path to the laptop.

## What the investigation established (2026-07-16, read-only against the live db)

`~/Library/Application Support/Emdash/emdash4.db`:

- **`tasks`** — `id, project_id, name, status, source_branch, task_branch, linked_issue,
  archived_at, last_interacted_at, status_changed_at, is_pinned, type, workspace_id, …`.
  Un-archived rows, ordered by `last_interacted_at DESC`, are the session list. `name` is
  emdash's own (e.g. `cloud-runner`, `ddd`, `turn`), NOT a branch. `task_branch` was empty
  on every live row — **branch is not a reliable identifier**; name + recent messages +
  last-active are.
- **`projects`** — `id, name, path` (repo root, e.g. `/Users/jjackson/emdash-projects/
  canopy-web`). Joins to `tasks.project_id` for the repo name.
- **`messages`** — schema exists (`conversation_id, content, sender, timestamp`) but is
  **EMPTY (0 rows)**. emdash does not store conversation content here. **The messages live
  in Claude Code's transcript `.jsonl`** under `~/.claude/projects/<dashed-worktree-path>/
  <session>.jsonl`. `conversations.config` is only `{"provider":"claude","type":"pty",…}` —
  no session id, no path. So reading messages requires resolving the transcript by
  convention, not a DB read. This is the single fact that splits the work into two phases.

## Phases

### Phase A — List + Continue (robust; ships first)

Neither half touches transcripts, so neither is exposed to Claude Code / emdash layout
drift. This is the whole "see my open sessions and continue this one" loop.

**A1. Runner reports open sessions.** Each poll tick (or a slower cadence — a config knob,
default every tick since it is one cheap read), the runner reads un-archived `tasks` joined
to `projects`, most-recent-first, capped at `SESSION_REPORT_LIMIT` (default 30). It POSTs:

```
POST /api/harness/runners/{runner_id}/sessions
  { sessions: [ { emdash_task: "<name>", project: "<repo>", status: "in_progress",
                  last_interacted_at: "<iso>" }, … ] }
```

The read is READ-ONLY and therefore **not** behind the `check_schema` write-vet pin
(same rule as `task_state`): a read cannot corrupt emdash and stays correct across
upgrades. A missing/unreadable/renamed column degrades to "no sessions reported", never a
crash — the runner loop must survive it.

**A2. canopy-web stores + serves.** A new framework-tier model:

```
EmdashSession                      # apps/harness — the reported live-session snapshot
  runner        FK Runner          # who reported it (and can reach it)
  workspace     FK Workspace       # tenant; defaults to dimagi (see below)
  emdash_task   CharField          # the task NAME — what open_and_send targets
  project       CharField          # the repo
  status        CharField
  last_interacted_at DateTime
  recent_messages JSONField default=[]   # Phase B fills this; [] in Phase A
  reported_at   DateTime
  unique_together (runner, emdash_task)
```

The report is **wholesale per runner**: delete this runner's rows, recreate from the
payload, in one transaction. A session that vanished from emdash (archived, deleted) simply
stops being reported and disappears — no tombstone bookkeeping. The list query hides
sessions whose **runner is not live** (`Runner.live_status`, the same signal `/supervisor`
already uses), so an offline runner's stale rows are suppressed without being destroyed — a
briefly-offline runner does not lose its list, and comes back the instant it reports again.

For each reported session the report **also upserts a `SessionLink`** so continue rides the
existing reuse path (below): `thread_key = "emdash:{emdash_task}"`, `project`, `workspace`,
`live_runner`/`live_host`/`live_emdash_task_id` = the reporter + task. This reuses the exact
machinery `record_session` already implements — the report is just another caller of it.

- `GET /api/harness/sessions` — the phone's list. Tenant-scoped (the caller's workspaces),
  ranked by `last_interacted_at DESC`, only sessions whose runner is live.

**A3. Phone lists + continues.** `/supervisor` gains an "Open sessions" section (a sibling
of the composer): project · task name · status · last-active. Each row has a **Continue**
affordance that opens the composer pre-targeted at that session — the user types a prompt
and sends. Continue dispatches:

```
enqueueTurn({ project, workspace, prompt, threadKey: "emdash:{emdash_task}" })
```

`resolve_session(project, thread_key, workspace)` finds the SessionLink the report
upserted → `reuse=True` (same runner+host owns the live hint) → the runner
`open_and_send`s the prompt into **that exact emdash task**. **No `execute.py` change** —
continue is a normal reuse, seeded by the runner's own report instead of a prior phone turn.

If the reuse falls through (the other macOS account's runner is live, or the task was
archived between report and claim), the existing path rehydrates a fresh session from the
durable summary — the inherited two-account limit, surfaced, not a new failure.

### Phase B — Read recent messages on click-in (follow-up)

**B1. Resolve the transcript.** For a task, derive the worktree path from emdash's
convention (`~/emdash/worktrees/<repo>/emdash/<task>` — pinned by a fingerprint like the
write-vet, since it is convention not schema), dash-encode it to
`~/.claude/projects/<dashed>`, take the newest `.jsonl`, and parse the **last N** entries
with canopy's existing `session_sharing` transcript parser (already battle-tested on
`.jsonl`). Bound to last ~8 messages — "recent", explicitly not the full transcript.

**B2. Fill `recent_messages`.** The runner includes the tail for the **most-recently-active**
session eagerly (the one you are most likely to open — "this session"), so its click-in is
instant; other sessions fetch on open (the phone flags a "watch", the runner includes that
session's tail on its next report → ~1 poll-tick latency). Reporting message tails for
*every* session every tick is the thing this avoids.

**B3. Degrade loudly-but-safely.** When the worktree/transcript convention does not resolve
(emdash changed its layout, a non-Claude provider, a session with no transcript yet), report
`recent_messages: []` with a reason; the phone shows "recent messages unavailable" and still
offers Continue. The feature never blocks on the fragile half.

## Design decisions

- **Continue reuses `SessionLink` + the reuse path — no new send code.** The alternative
  (a `Turn.origin_ref.emdash_task` that `execute.py` opens directly) would add a second
  "open a specific task" path next to the one `task_state`-guards against duplicate
  sessions. Seeding a SessionLink from the report keeps ONE reuse path, already hardened
  against the two-Hal-sessions bug.
- **`EmdashSession` is a separate model, not more fields on `SessionLink`.** SessionLink is
  the durable thread↔session *reuse* record; a reported session is an *ephemeral display
  snapshot* (replaced every tick, carries status/messages SessionLink has no business
  holding). They overlap only at "which task on which runner", which the report writes to
  both. Framework-tier, so no product import.
- **Reads are not behind the write-vet pin.** `emdash.task_state` already establishes this:
  a read cannot corrupt emdash, so the session-list read stays correct across emdash
  upgrades. Only the transcript *path convention* (Phase B) gets a fingerprint, because a
  wrong path is a silent wrong-answer, not a safe failure.
- **Tenant: reported sessions default to `dimagi`.** Consistent with repo dispatch
  (2026-07-16): workspace ownership is first-class (the `EmdashSession.workspace` FK), the
  value defaults to dimagi until multiplayer/cloud makes repo→workspace assignment real.
- **Wholesale replace per report, hide-don't-delete on staleness.** The list is a
  projection of "what emdash shows right now", so the report is authoritative and total;
  but a runner mid-restart must not blank the phone, so stale rows are hidden by query, not
  destroyed.

## What this is NOT (scope guards)

- Not the full transcript on the phone — recent tail only (Jonathan, explicit).
- Not hijacking a session the phone did not start via some new channel — continue goes
  through the same turn→runner→open_and_send path as everything else; "this session" appears
  because the runner *reports* it, and continue *reuses* it.
- Not a write path into emdash beyond what `open_and_send` already does.
- Not cross-account reach — the two-macOS-account limit is inherited and surfaced.

## Testing

- **Runner:** the session-list read returns the un-archived rows newest-first, capped;
  degrades to `[]` on a missing column / unreadable db (never raises). Phase B: transcript
  path resolves for a known task; returns `[]` + reason when it cannot.
- **canopy-web:** report upserts N EmdashSessions + N SessionLinks wholesale; a re-report
  with one session gone removes it; `GET /sessions` is tenant-scoped (a non-member sees
  none) and hides sessions whose runner is not live; a report from a runner the caller does
  not own 404s (mirrors the other runner routes).
- **Continue:** a dispatch with `thread_key="emdash:{name}"` resolves to reuse against the
  reported SessionLink (not new_thread); the served list + continue round-trip end to end.
- **Phone:** the Open sessions list renders at phone width (no page-level horizontal
  scroll); Continue pre-targets the composer and posts the right thread_key; click-in shows
  recent messages or the unavailable state.
- Verify like CI: `uv run pytest` with `.env` aside; package suites for `canopy_runner`;
  `npm run build` + vitest; Playwright locally (CI does not run it).

## Rollout

Phase A is safe to ship dark: no runner claims an EmdashSession report path until the laptop
daemon is updated, and the phone list is additive. Phase A's continue depends on the laptop
runner declaring `projects` + running the Phase-3 `execute.py` (already the prerequisite for
repo dispatch). Phase B ships after A and is independently additive (empty `recent_messages`
until the runner fills it).
