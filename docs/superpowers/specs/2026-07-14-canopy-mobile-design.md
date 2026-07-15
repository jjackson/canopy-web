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

**In scope:** the supervisor inbox, the fleet KPIs, launching agent commands, pausing/resuming the fleet, and **sending follow-up input into a live session** — including sessions working on a repo rather than an agent.

That last item is not a nice-to-have. Without it the phone is read-only in practice: you dogfood canopy-mobile, spot something wrong, and have no way to say so until you are back at the Mac. The loop has to close on the phone or the phone gets abandoned.

**Out of scope, deliberately:** the emdash session *mirror* — enumerating emdash's sidebar to see and drive sessions you started by hand. See *Deferred*. The deferral survives the scope change above because **the phone owns its own thread per target** (§2): the first message creates the session, every message after reuses it. You never need to enumerate emdash to talk to a thread you yourself started from the phone.

**Multi-runner is in scope now, cloud is designed for but not built.** Exactly one runner may execute a given **agent** at a time (§4) — but different agents may live on different runners, and that split grows with each agent's maturity. Work runs under one macOS account until its tokens are exhausted, then its agents are rebound to the other; a matured workhorse (ACE) can be bound to an always-on cloud runner and simply not participate in that handoff. The local-vs-cloud policy this needs (`Turn.routing` + `_kind_allows`) already exists.

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

### 2. Session input — the reuse path, already built

**The mechanism exists.** `cdp_control.open_and_send(task, text)` (`cdp_control.py:69`) opens a task and types into its live xterm; it is already the reuse branch of `execute_turn` (`execute.py:61-88`). Firing a Turn whose `thread_key` matches an existing `SessionLink` resolves to reuse and the text lands in the running session. **Zero runner changes.**

**The phone owns a persistent thread per target.** A stable `thread_key` — `phone:{user}:{target}` — means the first message creates the session and every message after reuses it. This is what lets the emdash mirror stay deferred: you never enumerate emdash to reach a thread you started from the phone.

**The `TASK_NOT_FOUND` rule is inherited, not weakened.** `execute.py:66` permits *only* `TASK_NOT_FOUND` to fall through from reuse to create; any other send failure fails the turn rather than duplicating a session. That rule exists because it once spawned two Hal sessions. Phone-driven input must not relax it: a flaky send is a failed turn you retry, never a second session.

**Cost note:** every fall-through to create is a new Claude session and therefore tokens. The existing `REUSE FELL BACK to CREATE` warning (`execute.py:104`) already flags a persistently-failing reuse. Phone dispatch makes this path hotter, so that warning becomes worth surfacing in the UI rather than only in the log.

### 3. Repo targets — the constraint that dogfooding forces

`Turn.agent` is a required `CASCADE` FK, so the harness can only address agents. But the session you want to revise from the phone is working on **canopy-web** — a repo. Of 22 emdash projects, roughly 5 are agents.

This is a data-model constraint, not a capability gap: **`cdp_control.create_task(project: str, ...)` is already project-generic** (`cdp_control.py:59`) — it scrolls the sidebar for `New task for <project>` and has no concept of an agent. `execute.py:113` simply passes `agent` as the project.

**Change:**

```
Turn
  agent    FK → Agent   NULL          ┐ CheckConstraint:
+ project  CharField    ""            ┘ exactly one set
```

- **`one_executing_turn_per_agent` stays agent-only.** An agent is one identity with one continuous session, so serializing it is correct. A repo is not: emdash gives every task its own worktree, so repo work is *meant* to parallelize. Extending the constraint to projects would wrongly funnel all canopy-web work into a single lane.
- **`SessionLink`** takes the same nullable-agent + project treatment; its unique key becomes `(agent|project, thread_key)`.
- **`Runner.capabilities`** gains `projects` alongside `agents`, and `claim_next_turn` widens `agent__slug__in=slugs` to `Q(agent__slug__in=slugs) | Q(project__in=projects)`.
- **`execute.py`** becomes `target = turn["agent_slug"] or turn["project"]`; the CDP call underneath is unchanged.
- **Workspace derivation** (§8) has no agent to derive from for project turns, so a project Turn carries its own `workspace` FK, used only when `agent` is null. This is the one place the derive-don't-denormalize rule cannot apply.

**Rejected: a pseudo-agent per repo.** It would serialize repo work behind `one_executing_turn_per_agent`, and pollute the fleet UI — every repo would acquire KPIs, a needs-you inbox, a skills catalog, and syncs it has no meaning for. A repo is not an agent and the model should not pretend otherwise.

### 4. Agent→runner binding — one runner *per agent*, not one runner overall

**The requirement (corrected):** the unit of exclusivity is the **agent**, not the workspace. Exactly one runner may execute a given agent at a time — but different agents may live on different runners, and that split is expected to grow with each agent's maturity. A workhorse like ACE, once it is reliable, wants to be always-on in the cloud while `echo`/`eva`/`hal` stay on whichever laptop account is in use.

> An earlier draft of this section made *the workspace* the unit — "exactly one active runner, switched on token exhaustion." That is a special case of this design (bind every agent to the same runner), and it would have blocked the always-on-ACE case entirely. It was never built; `is_active` does not exist in the code.

**Why exclusivity per agent matters, and it is not tidiness — it is tokens.** `SessionLink.reusable_by()` (`models.py:189`) requires `live_host == runner.host`. If an agent's turns alternate between two runners, **reuse never hits and every turn is a fresh Claude session** — `execute.py:104` logs exactly this (`NEW claude session = tokens`). So the binding must be *sticky*, not merely unique. Affinity is what makes session reuse work at all.

**Finding: today, claiming is a race.** `claim_next_turn` (`services.py:102`) filters by `runner.agent_slugs()`, routing, and kind — **never by host or identity.** Each macOS account runs its own runner (launchd is per-uid, `~/.canopy/runner.json` is per-account, each pairs for its own `runner_id`), and fast user switching keeps both logged in and polling. Verified empirically: with `jjackson` in the foreground, `acedimagi` had 369 live processes including Chromium renderers. A backgrounded account is fully alive, so both runners really do race.

**Change:** a binding model, in `apps/harness`.

```
AgentBinding
  agent      FK → agents.Agent   CASCADE
  runner     FK → Runner         CASCADE
  is_active  bool  default True
  bound_at, bound_by

  UniqueConstraint(fields=["agent"], condition=Q(is_active=True),
                   name="one_active_binding_per_agent")
```

It lives in `harness`, not as an `Agent.runner` FK, because **`harness` already imports `agents`** (`harness/api.py:11`) and `agents` imports nothing from `harness`. An FK on `Agent` would invert that and make the dependency circular. Both apps are framework tier, so this is about import direction, not the product boundary.

The partial unique index mirrors `one_executing_turn_per_agent` (`harness/models.py:107`) — same idiom, same reason: make the invariant unrepresentable rather than merely intended.

**`claim_next_turn` gains one exclusion:**

```python
# Affinity: an agent bound to another runner is off-limits. An UNBOUND agent
# stays claimable by any capable runner in the tenant — today's behaviour, and
# the migration path (no backfill needed).
bound_elsewhere = AgentBinding.objects.filter(is_active=True).exclude(runner=runner).values("agent_id")
candidates = candidates.exclude(agent_id__in=bound_elsewhere)
```

This composes with, and does not replace, the tenant predicate (§8) — **the workspace remains the security boundary; the binding is affinity.** Three independent filters intersect: tenant (security), `capabilities` (a self-declared routing hint), and binding (affinity). Conflating any of them was the bug that made `claim_next_turn` exploitable.

**Unbound is a valid state, deliberately.** It means "any capable runner in my tenant" — exactly today's behaviour — so this ships with **no backfill and no flag day**. You bind an agent when you want to pin it; until then nothing changes.

**Rebinding is one atomic call.** `POST /api/harness/runners/{id}/bind` with `{agent_slugs: [...]}` activates those agents' bindings on this runner and deactivates any other active binding for each, in one transaction. There is no window where an agent is bound twice or not at all.

Two operations fall out of the same primitive:
- **Token-exhaustion handoff:** rebind `jjackson`'s agents to `acedimagi`'s runner. ACE, bound to the cloud runner, is untouched — which is the whole point of the correction.
- **Promotion to always-on:** bind ACE to a cloud runner once and leave it.

**`target_runner` is unnecessary and is not in this design.** Binding is per-agent and durable, so a turn reaches the right machine by construction; per-turn targeting would be a second, redundant mechanism.

**Binding and pause are orthogonal, and both are needed:**

| | Binding | Pause |
|---|---|---|
| Answers | *which* runner may execute this agent | *whether* a runner claims at all |
| Cardinality | ≤1 active per **agent** | independent per **runner** |
| Durability | sticky — survives restarts; changes are deliberate | transient |
| Driven by | agent maturity; token exhaustion (hours/days) | dev iteration (minutes) |

**Handoff continuity already works — no new code.** On rebinding to `acedimagi`, that runner cannot reuse `jjackson`'s sessions (`reusable_by()` requires a host match). It correctly falls through to create-and-rehydrate from the durable `summary`. That is the designed behaviour, and precisely why `SessionLink` splits durable state from the ephemeral live hint. The one-off cost of a rebind is one fresh session per thread — which is also why you would not rebind casually.

**No in-flight turn is stranded by a rebind.** In the CDP path the Turn is the *routing* job, not the work: `execute_turn` finishes it synchronously the moment the prompt lands in a session (`main.py:191-193`). Turns are short-lived, so a rebind has essentially nothing claimed to strand. The *work* continues in `jjackson`'s emdash session and stops when tokens run out; the next turn on that thread lands on `acedimagi`, rehydrated. Intended, not a loss.

**Cloud fits unchanged, and is the reason for this correction.** A cloud runner is just a runner an agent can be bound to. The local-vs-cloud *policy* already exists and needs no work: `Turn.routing` (`prefer_local` / `local_only` / `any`) and `_kind_allows` (`services.py:93`) already stop a cloud runner taking a `local_only` turn — such a turn stays `QUEUED` until a local runner can take it. So "ACE always-on in the cloud while the laptop agents come and go" is: bind ACE to the cloud runner, leave the rest unbound or bound to the active laptop.

### 5. Remote pause — and resume, which is the hard half

**Requirement:** pause is a dev-iteration tool driven *from the phone*. **Resuming from the phone must work regardless of where the pause came from.** That requirement invalidates the obvious design, so it is worked through here rather than discovered in Phase 4.

**Finding:** you cannot pause from a phone today, and it is architectural. `PAUSED` is a *file on the laptop* (`main.py:532`), and the runner passes its local pause state **upward** as `?paused=` on claim (`client.py:79`). The control plane holds no pause state at all.

**Two things make naive remote resume fail:**

1. The paused branch of the loop calls `client.heartbeat(...)` and **throws the response away** (`main.py:541-546`), so a paused runner can never learn it has been resumed.
2. The pause check is `pause_file.exists()` — a local file **the phone cannot clear**. A pause set at the Mac would be a one-way door.

This is not hypothetical: `~/.canopy/PAUSED` was present on `jjackson` at the time of writing.

**Change — desired state on the runner:**

```
Runner
+ desired_paused         bool        default False
+ desired_paused_agents  JSONField   default list
```

Both ride `RunnerOut`, which the heartbeat response already returns (`api.py:80`) — **no new endpoint for the runner**, it reads what it already receives every 20s. A new `POST /api/harness/runners/{id}/desired-state` lets the phone write it (workspace-gated, per §8).

**The runner loop must read the heartbeat response before deciding to pause**, and the paused branch must keep reading it:

```
resp             = client.heartbeat(...)          # always, and keep the response
effective_paused = pause_file.exists() or resp["desired_paused"]
```

**The load-bearing change: the menubar's pause button stops writing the local file.** `_set_pause` (`menubar.py:681`) currently writes/unlinks `~/.canopy/PAUSED`; it must POST desired-state instead. Then pause always lives where *both* surfaces can reach it, and phone-resume works no matter where the pause originated. This lands in Phase 4 rather than waiting for Phase 5, because until it does, a pause set at the Mac is a pause the phone cannot lift — the exact frustration the phone exists to remove. Phase 5 deletes the code anyway.

**Precedence stays a union**, but the local file changes role:

```
effective_paused = local PAUSED file  OR  runner.desired_paused
```

The file is no longer the normal path — it becomes a genuine emergency brake (`touch ~/.canopy/PAUSED`) for when labs is unreachable and you need work stopped now. Both UI surfaces write server state; neither writes the file. So the union's failure mode ("resume does nothing") is now reachable only when you have *deliberately* dropped a sentinel by hand, which is exactly when you want it to win.

**Residual cost, mitigated by honesty, not cleverness:** if that hand-dropped file is present, the UI reports *why* ("paused by a local sentinel — clear it at the Mac") and disables the control rather than offering a button that lies. Latency is ≤20s, so the control reads "pausing…" until the next heartbeat confirms.

**Pause is per-runner, and §4 means that is no longer the same as "the fleet".** With agents bound to different runners, pausing one runner stops only the agents bound to it — ACE on a cloud runner keeps working while you pause the laptop. That is the correct behaviour, but it makes the UI's wording load-bearing: a control labelled "Pause" must name *which runner*, and the agent cards must show which runner each agent is bound to, or "why is ACE still running?" becomes a mystery. Per-agent pause (`desired_paused_agents`) is unchanged and remains the way to stop one agent without stopping its runner.

### 6. Push — the trigger is the design work

Plumbing (well-trodden): VAPID keypair, a `PushSubscription` model (`user`, `endpoint`, `p256dh`, `auth`, `created_at`, `last_used_at`), subscribe/unsubscribe endpoints, `pywebpush` to send.

**The design work is what fires a push.** `needs_you()` (`apps/agents/services.py:389`) is an *aggregation* — suggested tasks, open run gates, human-assigned in-progress tasks, failed steps — so there is no single event to hang a push on.

**Approach:** snapshot `waiting_count` per agent; recompute on `post_save` of the feeding models inside `transaction.on_commit`; push **only on increase**.

- Pushing on increase (not on every recompute) means a task you clear does not buzz you.
- `transaction.on_commit` with a **dirty-set of agents** means one bulk operation fires at most one recompute per agent, not one per row.

**Named storm risk:** `POST /api/agents/{slug}/tasks/sync` upserts many rows in one request. Without the dirty-set it would emit a push per row. This is the specific case the debounce exists for, and it must have a test.

### 7. Prerequisite — migrate `agents.ts` onto the generated types

`frontend/src/api/agents.ts` opens by stating the `/api/agents/*` routes "are live on the backend but are not yet present in the generated OpenAPI types", and therefore hand-rolls `getJson`/`postJson`, duplicates the workspace rewrite and CSRF/401 handling, and **hand-declares ~15 response interfaces** (`AgentOut`, `AgentDetailOut`, `NeedsYouOut`, `AgentTaskOut`, …).

**That comment is stale, and this was verified rather than assumed.** `generated.ts` contains **all 19 agent paths**, including `/api/agents/{slug}/needs-you` — and did so even before the most recent regeneration. Generating the schema directly from the live `NinjaAPI` object yields 19 agent paths out of 85 total, so nothing is dropping them. The regen workflow is working. The precondition the comment names — "when the types are regenerated (`npm run gen:api`)" — **has already been met.**

So there is no root cause to chase and nothing to regenerate. The work is the migration the comment itself prescribes: move the callers to `apiV2.GET(...)`, delete the hand-rolled fetch layer, and delete the ~15 hand-declared interfaces in favour of `components["schemas"][...]`.

This matters because it is exactly the surface the supervisor screen is built on. Building Phase 1 against hand-maintained shapes would fork the drift into a second consumer permanently — while the typed client sits there, already generated, unused.

### 8. Authorization — Phase 0, before any remote actuation

`TODOS.md:96-98` already names this: any authenticated PAT can claim as any runner, enqueue a turn for any agent, append events to any turn, or finish any turn. Neither `Runner` nor `Turn` has a workspace FK; no harness endpoint consults `request.workspace_slug`. `runner.capabilities["agents"]` filters what a runner *pulls* — it is a routing convenience, self-declared at pairing, not a security boundary.

Today the blast radius is contained: the actors are your own daemon on your own laptop. **This design changes that** by adding remote actuation — a leaked token would let someone enqueue arbitrary prompts into Claude sessions on your Mac and pause your fleet.

The phone itself does not make this worse (it is session-auth on labs, same as the web app). Building a remote control surface on an unauthorized control plane does.

**Change:** membership-gate the harness the way `apps/agents` already gates itself. `_get_agent_or_404` (`apps/agents/api.py:42`) calls `auto_join_workspaces`, checks `request.workspace_slug`, and returns **404 rather than 403** so non-membership does not leak existence. The harness should be indistinguishable from it.

Two specifics, resolved here rather than left to the implementer:

**`Turn` derives its workspace when it can, and stores it only when it cannot.** `Agent.workspace` already exists (`apps/agents/models.py:31`), so an agent Turn's tenant is `turn.agent.workspace` — deriving beats a parallel FK, because denormalized tenancy drifts. A **project** Turn (§3) has no agent, so it carries a `workspace` FK used only in that case. `Runner` needs its own FK for the same reason — and `claim_next_turn` uses it as the security boundary, intersected with (never replaced by) §4's binding.

**Runner operations bind to `runner.paired_by` (the user), not to a specific token.** `BearerTokenAuthMiddleware` stamps `request.user = token.user` (`apps/tokens/models.py:22-25`) and discards which token was used, so token-level binding would mean plumbing the token identity through the middleware. User-level binding closes the actual hole — *any authenticated PAT* becomes *your PATs only* — and survives rotation, which matters because `canopy:canopy-web-pat-mint` is documented as "re-run to rotate" and token-binding would break the runner on every rotation. The residual gap is accepted and stated: a second token belonging to the same user can still act as that user's runner.

## Phases

Each phase ships something usable. Nothing depends on a phase after it.

| Phase | What | Why here |
|---|---|---|
| **0** | Harness authz (§8): `Runner.workspace` FK, `Turn` derives via `agent.workspace`, membership-gated enqueue, runner ops bound to `paired_by`. Plus regenerate agent OpenAPI types (§7). | Nothing user-visible; everything after is safer and typed. Never a window where a token could drive the laptop. |
| **1** | `/supervisor` React route: needs-you inbox, agent KPI cards, runner status. Desktop browser. | Panel parity minus local controls. Built on canopy-ui, which already stacks rail-over-main at `md:`. |
| **2** | PWA: manifest, service worker, WebAPK install, VAPID, `PushSubscription`, `waiting_count` snapshot trigger (§6). Decide `SESSION_SAVE_EVERY_REQUEST`. | Where it stops being a smaller laptop and starts tapping you on the shoulder. Highest value, highest unknown. |
| **3** | Dispatch: `launchable` + `args_hint` (§1); repo targets (§3 — nullable `agent`, `project`, `SessionLink`/capabilities/claim widening); the composer; **session input via the existing reuse path** (§2). | The dogfooding loop. Repo targets and session input ship together because either alone leaves the loop open. |
| **4** | Control: `AgentBinding` + atomic `/bind` (§4); `desired_paused` (§5); runner loop reads the heartbeat response; **menubar `_set_pause` POSTs desired-state instead of writing the file**. | Rebind on token exhaustion; pin a matured agent to an always-on cloud runner; pause/resume that works from the phone regardless of origin. |
| **5** | Menubar `loadRequest_` + bridge; delete `render()`. | **Last, deliberately.** The panel is a daily tool; it is not replaced until the replacement is at parity. Phases 1–4 *are* the parity. |

**On sequencing Phase 3 and 4:** Phase 3 is the loop that stops you abandoning the phone; Phase 4 is what you need the day you exhaust tokens mid-session. Either order works — 3 first if you want the phone useful, 4 first if a handoff is imminent.

## Deferred (recorded so it is not relitigated)

### The emdash session controller

A "synced lightweight emdash controller" — see open sessions, continue one or start a new one — is appealing and explicitly deferred until the agent path works.

**When built, it reads `emdash4.db`, not the DOM.** The rationale:

- The `tasks` table carries `id`, `project_id`, `name`, **`status`**, `source_branch`, `task_branch`, `linked_issue`, `last_interacted_at`, `status_changed_at`, `is_pinned`, `type`, `automation_run_id`. It is complete and gives status and recency for free.
- The DOM alternative is worse than it looks. `cdp_control.list_tasks()` (`cdp_control.py:54`) already exists, is tested, and **is called by nothing in the daemon** — dead code. It is also subtly broken for this purpose: the emdash sidebar **virtualizes**, so rows scrolled out of view are not in the DOM at all. `create` knows this and scrolls the scroller in ≤40 steps hunting its target (`emdash_control.mjs:45-48`); `list` does not scroll. It returns *the visible slice*, not all 22 projects.
- Reading is far safer than the legacy `inject` executor's writes, but emdash auto-updates and its schema drifts — so a DB reader must sit behind the existing `vet` fingerprint machinery (`emdash.py:54-75`, `main.py:379-466`), which fingerprints normalized `CREATE TABLE` SQL and refuses on unvetted change.

**Note:** repo targets were *also* deferred in an earlier draft and have since moved into scope (§3) — dogfooding requires them. Only the *mirror* remains deferred, and it stays deferred because the phone owns its own thread per target and never needs to enumerate emdash to reach it.

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
- **Phase 3:** a non-`launchable` skill is absent from the catalog response the composer consumes. Dispatch produces a Turn whose prompt is exactly `/{slug}:{skill} {args}`. A Turn with both `agent` and `project` set is rejected by the CheckConstraint; so is one with neither. Two concurrent project turns for the same project both execute — `one_executing_turn_per_agent` must not have leaked onto projects. A second phone message on an existing thread reuses (`open_and_send`) rather than creating. A non-`TASK_NOT_FOUND` send failure fails the turn and creates **no** second session.
- **Phase 4:** binding an agent to runner B deactivates its binding on runner A **in one transaction**; the DB constraint rejects two active bindings for one agent. An agent bound to another runner is not claimable — and the negative test must use a **tenanted** attacker, since after the §8 backfill every real runner has a workspace and the untenanted path no longer exists in production. An **unbound** agent stays claimable by any capable runner in its tenant (the no-flag-day path). Two agents bound to two different runners both execute concurrently — that is the always-on-ACE case and the reason the workspace-level model was rejected. Pausing runner A does not stop an agent bound to runner B. A paused runner **reads the heartbeat response** and resumes when `desired_paused` flips — the regression test for the bug that a paused runner discards its heartbeat response. Pause set from the menubar is clearable from the phone (the whole point). A hand-dropped local `PAUSED` file still wins, and the UI reports why. A `local_only` turn is not claimed by a cloud runner and stays `QUEUED`.
- **Phase 5:** existing `menubar.py` tests for tray-icon state and the launchctl controls must pass unchanged — the swap must not touch them.
- Playwright currently defines **no mobile viewports** (`frontend/playwright.config.ts`). Phase 1 adds one.

**Untested and worth an experiment before relying on it:** whether the CDP sidecar drives emdash reliably from a *switched-away* macOS session. The sidecar is occlusion-proof (JS-dispatched clicks), but occluded-within-a-session is not the same as a session that is not on screen at all, and Chromium throttles invisible renderers. `page.evaluate()` needs no paint and layout still runs, so `create`'s scroll-and-wait for virtualized rows *should* work — but it has never been tried, and `acedimagi` has no runner configured today. This only matters if the always-on-background-account model is ever adopted; it is not needed for the switch-on-token-exhaustion model, where the active account is the foreground one.
