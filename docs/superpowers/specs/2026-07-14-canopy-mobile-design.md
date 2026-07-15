# canopy-mobile: one supervisor surface, three consumers

**Status:** design approved, not yet implemented
**Date:** 2026-07-14
**Related:** `2026-07-05-agent-execution-control-plane-design.md` (the harness), `2026-06-17-shared-workbench-package-design.md` (canopy-ui), `2026-06-30-workspace-multi-tenancy-design.md` (tenancy)

## The problem

There is no mobile app problem. There is a **duplication problem that a phone would make worse.**

The menubar panel (`packages/canopy_runner/canopy_runner/menubar.py`) and canopy-web already render the same concepts — "waiting on you", agent KPI cards, fleet status — from the same endpoints (`GET /api/agents/{slug}/needs-you`, `GET /api/reviews/?status=pending`). They share zero code: one is an HTML document built from Python f-strings at `menubar.py:414` and handed to a `WKWebView` via `loadHTMLString_`; the other is React. The commit that shipped the current panel (#205) describes it as a *"Mobile-style supervisor view (canopy-web parity to follow)"* — the parity debt was named at birth.

A phone would be the third copy of a screen that is already duplicated twice.

## The thesis

Build **one React supervisor surface** in canopy-web. All three consumers load it.

```
              canopy-web  /supervisor  (React, canopy-ui, generated types)
                                │
        ┌───────────────────────┼───────────────────────┐
   phone (PWA)          menubar WKWebView         desktop browser
   installed WebAPK      loadRequest_(url)         just a route
   push + badge          + native bridge
```

The menubar's `WKWebView` swaps `loadHTMLString_` → `loadRequest_` against the labs URL. This deletes `render()`, the inline CSS, `_card()`, `_waiting_item()`, `_workspace_map()`, and the `ThreadPoolExecutor` API fan-out — roughly 300 of `menubar.py`'s 723 lines. What survives is what genuinely must be native:

- the `NSStatusBar` tray icon (the vector bare-branch tree, `menubar.py:85-141`)
- `launchctl` daemon control (`_daemon`, `menubar.py:704`)
- the `PAUSED` / `PAUSED.<slug>` sentinel files (`_set_pause`, `menubar.py:681`)
- the JS↔native bridge (`userContentController_didReceiveScriptMessage_`, `menubar.py:648`)

**The bridge is why this is an upgrade, not a downgrade.** `addScriptMessageHandler` works against a remote origin, so one React page detects its host: inside the panel `window.webkit.messageHandlers.bridge` exists and local controls route natively; on the phone it is `undefined` and those controls hide.

**The service worker earns its keep twice.** WKWebView supports service workers for remote origins (not for `file://` or `loadHTMLString_`). The SW built to make the phone work on bad signal also makes the panel survive a labs outage by serving the cached shell. This is strictly better than today, where a panel that renders from local files cannot show fleet state at all when offline.

### Accepted cost

The panel gains a network dependency it does not have today. Mitigated by the SW cache, and by pause/daemon controls staying local via the bridge — the controls that matter in an emergency work even when labs is gone.

## Why Android changes the calculus

Target is Android (Chrome). This is the platform PWAs were designed for; iOS is the one that grudgingly caught up.

- Chrome generates a **WebAPK** — a real signed Android package in the app drawer, app switcher, and Settings → Apps. On iOS it is a home-screen bookmark.
- **Push** has worked for years rather than being a 2023 concession (iOS 16.4). Same for the **Badging API** — "3 waiting on you" on the icon is reliable on Android, flaky on iOS.
- **`beforeinstallprompt`** lets canopy-web offer an Install button rather than making the user find the share sheet.
- Requires HTTPS with a valid cert. Labs is already `https://labs.connect.dimagi.com/canopy/`.

The phone talks only to labs. **The laptop is never reachable from the internet** — the runner dials out on its existing 20s poll. This property is load-bearing and must not be traded away.

## Scope

**In scope:** agents. The supervisor inbox, the fleet KPIs, launching agent commands, and pausing the fleet.

**Out of scope, deliberately:** the emdash session controller. See *Deferred* below — the decision and its rationale are recorded there so they are not relitigated.

## Design

### 1. Command catalog — `AgentSkill` declares its own entry points

`AgentSkill` (`apps/agents/models.py:152`) is descriptive: `name`, `description`, `url`, `improvement_note`. The catalog is replaced wholesale on each PUT "so it always mirrors the repo."

Mirroring the repo is the problem. Echo publishes **20 skills**, but most are not human entry points: `agent-turn-review` is a pre-send discipline other skills invoke, `self-review` is superseded, `contact-memory` is a reference doc, `setup` is one-time per-machine. Rendering the catalog as buttons yields a phone full of footguns, and `/echo:setup` sits one thumb away.

Some commands also take arguments (`/canopy:agent-review <slug>`, `/ace:step <name>`), which the catalog cannot express.

**Change:** add two fields to `AgentSkill`.

```
AgentSkill
  name           "story-ideation"
  description    ...
  url            SKILL.md
+ launchable     bool   default False
+ args_hint      str    default ""    e.g. "topic (optional)"
```

`AgentSkillIn` / `AgentSkillOut` (`apps/agents/schemas.py:130`) gain the same. The agent's publish step marks which of its skills are launchable. Echo publishes 20, marks ~5.

**Why extend rather than add an `AgentCommand` model:** the wholesale-PUT contract exists precisely to keep the catalog from drifting from the repo. A second catalog would be a second thing to keep in sync — reintroducing the failure the current design prevents. Extending keeps one source of truth and lets the agent own its own surface: as agents mature, new commands appear on the phone with **zero canopy-web changes**.

**Dispatch requires no runner changes.** Tapping a command enqueues:

```
POST /api/harness/turns/
  agent_slug       "echo"
  origin           "manual"
  prompt           "/echo:story-ideation <args>"
  idempotency_key  "cmd-{user}-{agent}-{skill}-{ts}"
```

`execute.py:57` already reads `turn.get("prompt") or f"/{agent}:turn"` and honours an arbitrary prompt. The runner claims within 20s and CDP-injects it. Nothing in `canopy_runner` changes.

### 2. Remote pause — desired state on the control plane

**Finding:** you cannot pause from a phone today, and it is architectural, not an oversight. `PAUSED` is a *file on the laptop* (`main.py:532`), and the runner passes its local pause state **upward** as `?paused=` on claim (`client.py:79`). The control plane holds no pause state at all.

**Change:** add desired state to `Runner`.

```
Runner
+ desired_paused         bool           default False
+ desired_paused_agents  JSONField      default list
```

Both are returned in `RunnerOut`, which the heartbeat response already carries (`api.py:80`). **No new endpoint for the runner** — it reads what it already receives every 20s. A new `POST /api/harness/runners/{id}/desired-state` lets the phone write it (workspace-gated, per Phase 0).

**Precedence is a union:**

```
effective_paused        = local PAUSED file        OR  runner.desired_paused
effective_paused_agents = local PAUSED.<slug> glob  ∪   runner.desired_paused_agents
```

**Why union:** it preserves the local file as an emergency brake that always wins when you are sitting at the machine, and adds zero regression to existing behaviour.

**The cost, and its mitigation:** "resume" from the phone can appear to do nothing when a local `PAUSED` file exists. The UI must therefore render *why* it is paused ("paused locally — clear at your Mac") and disable rather than offer a dead button. Latency is ≤20s (one poll), so the control shows "pausing…" until the next heartbeat confirms — optimistic UI with honest confirmation.

### 3. Push — the trigger is the design work

Plumbing (well-trodden): VAPID keypair, a `PushSubscription` model (`user`, `endpoint`, `p256dh`, `auth`, `created_at`, `last_used_at`), subscribe/unsubscribe endpoints, `pywebpush` to send.

**The design work is what fires a push.** `needs_you()` (`apps/agents/services.py:389`) is an *aggregation* — suggested tasks, open run gates, human-assigned in-progress tasks, failed steps — so there is no single event to hang a push on.

**Approach:** snapshot `waiting_count` per agent; recompute on `post_save` of the feeding models inside `transaction.on_commit`; push **only on increase**.

- Pushing on increase (not on every recompute) means a task you clear does not buzz you.
- `transaction.on_commit` with a **dirty-set of agents** means one bulk operation fires at most one recompute per agent, not one per row.

**Named storm risk:** `POST /api/agents/{slug}/tasks/sync` upserts many rows in one request. Without the dirty-set it would emit a push per row. This is the specific case the debounce exists for, and it must have a test.

### 4. Prerequisite — regenerate the agent types

`frontend/src/api/agents.ts` opens by admitting the `/api/agents/*` routes "are live on the backend but are not yet present in the generated OpenAPI types". It therefore hand-rolls `getJson`/`postJson`, duplicates the workspace rewrite and CSRF/401 handling, and **hand-declares ~15 response interfaces** (`AgentOut`, `AgentDetailOut`, `NeedsYouOut`, `AgentTaskOut`, …).

That is exactly the surface the supervisor screen is built on. Writing a second consumer against hand-maintained shapes forks the drift permanently.

The file states regenerating fixes it "without touching callers", and `.github/workflows/regen-openapi.yml` already triggers on `apps/**/api.py` and `apps/**/schemas.py` — so the types should not be stale. **Part of this phase is finding out why they are.** Fix the cause, not just the artifact.

### 5. Authorization — Phase 0, before any remote actuation

`TODOS.md:96-98` already names this: any authenticated PAT can claim as any runner, enqueue a turn for any agent, append events to any turn, or finish any turn. Neither `Runner` nor `Turn` has a workspace FK; no harness endpoint consults `request.workspace_slug`. `runner.capabilities["agents"]` filters what a runner *pulls* — it is a routing convenience, self-declared at pairing, not a security boundary.

Today the blast radius is contained: the actors are your own daemon on your own laptop. **This design changes that** by adding remote actuation — a leaked token would let someone enqueue arbitrary prompts into Claude sessions on your Mac and pause your fleet.

The phone itself does not make this worse (it is session-auth on labs, same as the web app). Building a remote control surface on an unauthorized control plane does.

**Change:** membership-gate the harness the way `apps/agents` already gates itself. `_get_agent_or_404` (`apps/agents/api.py:42`) calls `auto_join_workspaces`, checks `request.workspace_slug`, and returns **404 rather than 403** so non-membership does not leak existence. The harness should be indistinguishable from it.

Two specifics, resolved here rather than left to the implementer:

**`Turn` gets no workspace FK — it derives one.** `Agent.workspace` already exists (`apps/agents/models.py:31`) and `Turn.agent` is non-null, so a Turn's tenant is `turn.agent.workspace`. Adding a parallel FK would denormalize a fact already stored one hop away, and denormalized tenancy is a thing that drifts. **`Runner` does need its own FK** — it has no agent to derive from.

**Runner operations bind to `runner.paired_by` (the user), not to a specific token.** `BearerTokenAuthMiddleware` stamps `request.user = token.user` (`apps/tokens/models.py:22-25`) and discards which token was used, so token-level binding would mean plumbing the token identity through the middleware. User-level binding closes the actual hole — *any authenticated PAT* becomes *your PATs only* — and survives rotation, which matters because `canopy:canopy-web-pat-mint` is documented as "re-run to rotate" and token-binding would break the runner on every rotation. The residual gap is accepted and stated: a second token belonging to the same user can still act as that user's runner.

## Phases

Each phase ships something usable. Nothing depends on a phase after it.

| Phase | What | Why here |
|---|---|---|
| **0** | Harness authz (`Runner.workspace` FK; `Turn` derives via `agent.workspace`; membership-gated enqueue; runner ops bound to `paired_by`) + regenerate agent OpenAPI types | Nothing user-visible; everything after is safer and typed. Never a window where a token could drive the laptop. |
| **1** | `/supervisor` React route: needs-you inbox, agent KPI cards, runner status. Desktop browser. | Panel parity minus local controls. Built on canopy-ui, which already stacks rail-over-main at `md:`. |
| **2** | PWA: manifest, service worker, WebAPK install, VAPID, `PushSubscription`, `waiting_count` snapshot trigger | Where it stops being a smaller laptop and starts tapping you on the shoulder. Highest value, highest unknown. |
| **3** | `launchable` + `args_hint`; the composer; enqueue on tap | The original ask: trigger specific commands as agents mature. |
| **4** | `desired_paused` / `desired_paused_agents`; union semantics; legible pause reason | Remote control. |
| **5** | Menubar `loadRequest_` + bridge; delete `render()` | **Last, deliberately.** The panel is a daily tool; it is not replaced until the replacement is at parity. Phases 1–4 *are* the parity. |

## Deferred (recorded so it is not relitigated)

### The emdash session controller

A "synced lightweight emdash controller" — see open sessions, continue one or start a new one — is appealing and explicitly deferred until the agent path works.

**When built, it reads `emdash4.db`, not the DOM.** The rationale:

- The `tasks` table carries `id`, `project_id`, `name`, **`status`**, `source_branch`, `task_branch`, `linked_issue`, `last_interacted_at`, `status_changed_at`, `is_pinned`, `type`, `automation_run_id`. It is complete and gives status and recency for free.
- The DOM alternative is worse than it looks. `cdp_control.list_tasks()` (`cdp_control.py:54`) already exists, is tested, and **is called by nothing in the daemon** — dead code. It is also subtly broken for this purpose: the emdash sidebar **virtualizes**, so rows scrolled out of view are not in the DOM at all. `create` knows this and scrolls the scroller in ≤40 steps hunting its target (`emdash_control.mjs:45-48`); `list` does not scroll. It returns *the visible slice*, not all 22 projects.
- Reading is far safer than the legacy `inject` executor's writes, but emdash auto-updates and its schema drifts — so a DB reader must sit behind the existing `vet` fingerprint machinery (`emdash.py:54-75`, `main.py:379-466`), which fingerprints normalized `CREATE TABLE` SQL and refuses on unvetted change.

### Non-agent / repo targets

`Turn.agent` is a required `CASCADE` FK to `agents.Agent`, so the harness can only address things that are agents. There are 22 emdash projects and roughly 5 are agents; the rest (canopy-web, commcare-connect, scout, connect-labs, …) are unreachable.

This is a data-model constraint, not a capability gap: **`cdp_control.create_task(project: str, ...)` is already project-generic** — it scrolls the sidebar for `New task for <project>` and does not know what an agent is. `execute.py:113` simply passes `agent` as the project.

If this is ever wanted, note that `one_executing_turn_per_agent` must **not** be inherited by repo targets: an agent is one identity with one continuous session, so serializing it is correct; a repo is not, and emdash gives every task its own worktree, so repo work is meant to parallelize.

### Android freebies not in scope

- **Share target** — register the PWA in Android's share sheet; share a GitHub issue into it and it becomes a turn.
- **App shortcuts** — long-press the icon for "New turn" / "Waiting on you" / "Pause fleet". Manifest-declared, no code.

## Risks

**Push storming on bulk sync.** `POST /api/agents/{slug}/tasks/sync` upserts many rows per request. The `transaction.on_commit` dirty-set is the mitigation; it needs a test that a bulk sync of N tasks emits at most one push per agent.

**The panel's new network dependency.** Mitigated by the service worker (supported in WKWebView for remote origins) and by keeping pause/daemon control local via the bridge. Phase 5's ordering is itself a mitigation — the swap does not happen until parity exists.

**Session expiry on an installed PWA.** `SESSION_COOKIE_AGE` is unset, so Django's default of two weeks applies, and `SESSION_SAVE_EVERY_REQUEST` defaults to `False` — meaning **the session expires two weeks from login, not from last use.** An installed app that silently logs out on a fixed fortnightly cycle regardless of use is a real papercut. Setting `SESSION_SAVE_EVERY_REQUEST = True` converts it to a rolling window from last use, at the cost of a session write per request. Decide this in Phase 2; do not discover it in month two.

**Stale reuse targets.** Unchanged by this design, but worth knowing: tapping a command that reuses a session whose emdash task is gone hits the existing `TASK_NOT_FOUND` path (`execute.py:66`), which is the *only* error permitted to fall through to create. Any other failure fails the turn rather than duplicating a session — the bug that once spawned two Hal sessions. Phone-driven dispatch must not weaken that rule.

## Testing

- **Phase 0:** a non-member PAT gets 404 (not 403) from every harness endpoint. A PAT belonging to a user who is not `runner.paired_by` cannot heartbeat, claim, or write desired-state for that runner.
- **Phase 2:** bulk `tasks/sync` of N tasks emits ≤1 push per agent. A `waiting_count` decrease emits none.
- **Phase 3:** a non-`launchable` skill is absent from the catalog response the composer consumes. Dispatch produces a Turn whose prompt is exactly `/{slug}:{skill} {args}`.
- **Phase 4:** local `PAUSED` file present + server `desired_paused=False` → still paused, and the UI reports "paused locally".
- **Phase 5:** existing `menubar.py` tests for tray-icon state and the launchctl/PAUSED controls must pass unchanged — the swap must not touch them.
- Playwright currently defines **no mobile viewports** (`frontend/playwright.config.ts`). Phase 1 adds one.
