# Supervisor: Runners as a first-class tab

**Date:** 2026-07-21
**Status:** Approved (design)
**Surface:** `/supervisor` (phone PWA + menubar WKWebView + desktop browser)

## Problem

The `/supervisor` page has three tabs — **Inbox**, **Sessions**, **Agents** — and
runners are buried *inside* the Agents tab (a `RunnerStatus` list that drills into
a `RunnerDetail` card), sharing space with the per-agent KPI cards and the
install/push prompts. Two gaps:

1. Runners are not a first-class surface — they're a sub-section of "Agents".
2. The fleet's routing reality is invisible here. "Which agents prioritize which
   runners" exists as data (`Agent.runner_preference`, an ordered list of runner
   **kinds**) but is only viewable/editable one agent at a time on each agent's
   own overview page (`RunnerOrder.tsx`). There is no cross-agent view, and none
   on the supervisor.

## Goal

Promote runners to their own **Runners** tab on `/supervisor` that shows (a) each
runner's health/info and (b) which agents prioritize it — with the ability to
reorder an agent's preference in place.

## Key constraint that shapes everything

`Agent.runner_preference` is an ordered list of runner **kinds**
(`["cloud", "emdash", "remote"]`), **not** specific runner instances. So "which
agents prioritize *this runner*" resolves to "which agents rank *this runner's
kind*." An empty preference means "any eligible runner, first-poll-wins" — the
agent implicitly accepts every kind.

## This is a pure-frontend change

Every input is already exposed; no backend, API, schema, or migration work.

- `listRunners()` (`GET /api/harness/runners/`) → `RunnerOut` with `kind`, health,
  `host`, `code_branch`, `workspace`, `ready`/`ready_note`, `capabilities`.
- `listAgents()` (already called by `SupervisorPage`) → `AgentOut` including
  `runner_preference`.
- `updateAgentRunnerPreference(slug, prefs)` (`PATCH
  /api/agents/{slug}/runner-preference`) persists edits.
- `useLiveSupervisor()` already live-patches runner `status`/`last_heartbeat_at`.

## Design

### 1. Tab bar — add a 4th tab "Runners"

`frontend/src/pages/SupervisorPage.tsx`:

- Tab order becomes **Inbox / Sessions / Agents / Runners**.
- Widen the URL-derived `tab` union to include `'runners'`
  (`raw === 'sessions' || raw === 'agents' || raw === 'runners' ? raw : 'inbox'`).
- Add `<TabsTrigger value="runners" data-testid="tab-runners">`.
- Add a `<TabsContent value="runners">` block.
- **Move the runner UI out of the Agents tab.** The Agents tab keeps only the
  per-agent `AgentKpiCard` grid + `InstallPrompt`/`PushToggle`.
- The Runners tab reuses the already-in-scope `renderRunners` (live-patched
  `RunnerOut[]`) and `agents` (`AgentOut[]` with `runner_preference`) — no new
  fetches. The existing selected-runner state (`selectedRunner` /
  `RunnerStatus onSelect → RunnerDetail`) moves with it.
- The loud non-main-`code_branch` alert above the tabs is unchanged.

### 2. Runner list — reuse `RunnerStatus.tsx`

Same rows (status dot, name, `not ready` badge, host, relative heartbeat). Add a
small **"N agents"** chip per row = the number of agents that rank this runner's
**kind** #1 (its true prioritizers), so the mapping is legible before drilling in.
The chip's count comes from the derivation helper (§4). Zero → render nothing (no
"0 agents" noise).

### 3. Runner detail — `RunnerDetail.tsx` gains an "Agent priority" section

Keep the existing info rows (status / kind / host / workspace / `code_branch` /
`ready` + `ready_note` / agents / projects from `capabilities`). Add a new
**Agent priority** section keyed to this runner's `kind`:

- **Ranked list.** Every agent whose `runner_preference` *includes* this kind,
  sorted ascending by rank, each labeled with its 1-based position rendered as an
  ordinal (**1st / 2nd / 3rd**).
- **Accepts-all group.** Agents with an **empty** `runner_preference` listed under
  a "any — accepts all kinds" subheading (they implicitly accept this kind).
- Agents whose non-empty preference **excludes** this kind are not shown (they
  will never claim it).
- **Inline edit (interaction A).** Each agent row has a chevron/disclosure that
  expands a compact `RunnerOrder` reorder widget in place. Saving calls
  `updateAgentRunnerPreference` and lifts the new preference up to the supervisor
  so the list + the list-view chip re-derive live (see §5). Expansion state is
  local per row; multiple rows may be expanded at once (no single-open
  constraint).

Empty states: if no agent references this kind and none accept-all, show a muted
"No agents prioritize this runner kind."

### 4. Pure derivation helper (isolated + unit-tested)

New module `frontend/src/components/supervisor/runnerPriority.ts`:

```ts
export interface RankedAgent { agent: AgentOut; rank: number } // rank is 1-based

export interface KindPriority {
  ranked: RankedAgent[];   // agents whose preference includes `kind`, sorted by rank asc
  acceptsAll: AgentOut[];  // agents with empty preference
}

export function agentsForKind(agents: AgentOut[], kind: string): KindPriority
export function firstChoiceCount(agents: AgentOut[], kind: string): number // for the list chip
export function ordinal(n: number): string // 1 -> "1st", 2 -> "2nd", 3 -> "3rd"
```

Rules:
- `runner_preference` non-empty and contains `kind` → `rank = indexOf(kind) + 1`,
  added to `ranked`.
- `runner_preference` empty → added to `acceptsAll`.
- `runner_preference` non-empty and missing `kind` → excluded.
- `firstChoiceCount` = number of agents whose `runner_preference[0] === kind`.

Unit tests cover: first-choice vs lower-ranked, empty=accepts-all, excluded kind,
ordinal formatting, and stable sort by rank.

### 5. Small reuse tweaks to `RunnerOrder.tsx`

`RunnerOrder` today is self-contained (fetches its own `listRunners()` on mount,
owns a "Save order" button, takes `slug`/`name`/`preference`). Two additive,
backward-compatible props:

- `onSaved?(pref: string[])` — invoked after a successful
  `updateAgentRunnerPreference`, so the supervisor can update its local `agents`
  state (the source the mapping derives from). The existing agent-overview caller
  passes nothing and is unaffected.
- `runners?: RunnerOut[]` — when provided, `RunnerOrder` uses it for the per-kind
  online-count dots instead of firing its own `listRunners()`. The supervisor
  passes its already-loaded `renderRunners` so N inline editors don't each fetch.
  When omitted, behavior is unchanged (fetches on mount).

## Out of scope (YAGNI)

- No new backend endpoint, schema field, or migration.
- No per-specific-runner (instance-level) preferences — preference stays by kind.
- No change to claim-time honoring (`_preference_allows` in
  `apps/harness/services.py`) — it already reads `runner_preference` unchanged.
- No redesign of the Agents/Inbox/Sessions tabs beyond removing the runner block
  from Agents.

## Testing

- Unit: `runnerPriority.ts` (`agentsForKind`, `firstChoiceCount`, `ordinal`).
- Component (light): the Runners `TabsContent` renders a runner list; selecting a
  runner shows the Agent-priority section with correct ordinals and the
  accepts-all group; `data-testid="tab-runners"` is present and reachable via
  `?tab=runners`.
- Frontend build/type check: `cd frontend && npm run build`.
- Verify in the running app (not curl — canopy-web is a PWA; stale SW bundles can
  mask new routes): render `/supervisor?tab=runners`, confirm the mapping and an
  inline reorder round-trips and updates the chip.

## Files

- `frontend/src/pages/SupervisorPage.tsx` — 4th tab, move runner UI, pass
  `agents`/`runners` down, hold lifted preference updates.
- `frontend/src/components/supervisor/RunnerStatus.tsx` — "N agents" chip.
- `frontend/src/components/supervisor/RunnerDetail.tsx` — Agent-priority section +
  inline `RunnerOrder`.
- `frontend/src/components/supervisor/runnerPriority.ts` — new derivation helper.
- `frontend/src/components/supervisor/runnerPriority.test.ts` — new unit tests.
- `frontend/src/components/agents/RunnerOrder.tsx` — `onSaved` + `runners` props.
- Backend: none.
