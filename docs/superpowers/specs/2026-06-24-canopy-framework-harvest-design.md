# Canopy as THE Framework — Harvesting the Generic Layer out of ACE

**Status:** Draft for review · **Date:** 2026-06-24 · **Author:** Jonathan + Claude

> Strategy / design doc, not an implementation plan. It settles the architecture
> stance, inventories what moves from ACE into Canopy, and proposes an order.
> Each wave gets its own spec → plan → implementation cycle later.

---

## 1. The settled stance

One sentence: **Canopy (the `canopy` plugin + `canopy-web`) is THE framework. ACE depends on Canopy. The generic capabilities ACE invented get relocated into Canopy so every agent inherits them. ACE keeps only what is irreducibly ACE.**

What we explicitly decided along the way:

- **No new/third framework.** We do not extract a neutral "shared package" that both
  consume. Canopy *is* the home. The dependency arrow points one way: **ACE → Canopy.**
- **Two runtimes, both first-class and permanent** — not primary + fallback:
  - **Canopy as the default runtime** — the easy place to stand up an agent and give it
    a workbench, for *internal* (Dimagi) operators.
  - **Standalone as a graduation path** — when an agent "cracks" (e.g. ACE shipped to
    Connect's *customers*), it runs as its own externally-facing product that does **not**
    require access to the central Canopy runtime — but is built on Canopy's framework code.
- **Two planes the current code blurs:**
  - **Operator / supervisor plane** (internal): the board, *needs-you* inbox, command
    queue, run viewer, eval verdicts — "what does my agent need from me?"
  - **End-user / product plane** (external): the actual agent *experience* a customer
    touches. Bespoke per agent; **not** harvested.
- **Architecture is a blend, not a decomposition.** Framework, services, and agents are
  the same objects seen from different angles (a modular monolith). We do **not** split
  repos or draw hard internal walls.

### 1.1 The one invariant that makes the blend safe

The blend stays beautiful only if **one rule** holds:

> **The dependency arrow is one-way: generic (framework) code never imports specific
> (a particular agent's domain) code. Specific imports generic.**

This costs nothing day-to-day and is *not* decomposition — it's a direction. Its payoff:
the framework stays **cuttable**. You never have to physically separate it, but the seam
is always there for the day you need it (ACE-standalone-for-customers). The failure mode
it prevents: a generic registry quietly importing a specific agent's model, so that years
later you cannot ship ACE to customers without dragging Canopy's product along.

We already have both a clean example and a small violation of this rule (§5).

---

## 2. The landscape (from the four audits)

| | **Harness = the framework** | **Example = the agent** |
|---|---|---|
| Plugin | **canopy** — 5 agents, 44 skills, thin-agent/fat-skill, DDD pipeline, `video-engine` | **ace** — 13 agents, 111 skills, 5 MCP servers, 10-phase lifecycle |
| Web | **canopy-web** — single-tenant, **Postgres = truth**, GCP Cloud Run | **ace-web** — **multi-tenant**, **Drive = truth**, AWS Fargate |

The break that makes this tractable: **both web apps are the identical stack** — Django
Ninja + Pydantic v2 + React 19 + Vite + Tailwind 4 + `openapi-fetch` + per-user PAT
loopback + FastMCP. The plugins already share the PAT flow and a **byte-identical**
`video-engine`. **This is convergence, not a rewrite.**

### 2.1 Who has what today

- **ace-web has, canopy-web lacks entirely:** multi-tenant workspaces + RBAC + invites ·
  WebSocket chat + presence (canopy only has SSE) · transcript ingest + **cost/structure
  rollup** · Drive read-through cache + Changes API · the **run/step/artifact/fork**
  lifecycle.
- **ace (plugin) has, canopy should absorb:** the `run_state.yaml` phase/step/products
  state machine + write-back contract · **artifact-manifest registry** · the **QA-gate →
  eval → verdict-schema → calibration → `opp-eval` aggregator** stack (the crown jewel) ·
  decisions log · **capability-map MCP** ("atom is the contract, backend is swappable").
- **canopy-web has, ace lacks:** the clean **Agent abstraction** (`apps/agents`: board,
  command-drain queue, typed *needs-you* inbox). The *canopy plugin* doesn't drive it
  (zero `/api/agents/*` callers) — **but Echo does** (see §2.3). The real gap is not an
  unused surface; it's that **every agent hand-rolls its own client** to reach it.

### 2.2a Echo — the live "basic agent" reference

Echo (`/Users/jjackson/emdash/repositories/echo`, a Claude Code plugin, marketing agent
for Connect) is the **first and live consumer of the agents board**. Via two hand-rolled
Python clients it drives essentially the whole `apps/agents` surface:

- `bin/echo_canopy.py` — `POST /api/agents/` (register), `…/syncs/`, `…/work-products/`,
  `PUT …/skills/` (mirrors `skills/*/SKILL.md`).
- `bin/echo_tasks.py` (+ `task-tracker` skill) — `POST …/tasks/sync`,
  `GET …/commands?status=pending` (**drains** queued board actions every turn),
  `POST …/commands/{id}/apply`, `PATCH …/tasks/{id}/` (stores rationale/source/plan).

Two findings from Echo that steer the harvest:

1. **Echo and ACE bracket the keystone.** Echo is **board-only, no run lifecycle**; ACE is
   **run-lifecycle-only, not on the board**. The clearest proof that W2 (fuse board + run
   lifecycle) is the center of gravity: Echo will *want* the lifecycle as it matures; ACE
   will *want* the board.
2. **Echo already ran the operator-plane state-store reconciliation.** Commit #22 moved its
   board from *Google Sheet = truth* to *canopy-web DB = truth* (the Sheet became a
   non-destructive legacy import). Data point for §4.1: **DB-as-truth is the natural default
   for the operator plane**; Drive-as-truth is only for heavy artifacts (ACE).

### 2.2 The keystone insight

ACE has a rich **run lifecycle** but no **board**. Canopy has a **board** but no **run
lifecycle**. These are two halves of one model. The single most important framework move
is to **unify them**: an `Agent` in canopy-web gains a run/step/artifact/verdict lifecycle,
and the board's "who has the ball" becomes *driven by* run state + pause gates. Everything
else in this doc is plumbing around that synthesis.

---

## 3. The harvest map

Legend — **Lands:** `plugin` = canopy plugin / shared agent-runtime lib; `web` = canopy-web.
**Generic-side check:** does it sit on the generic side of the one-way arrow? (must be ✅).
**Converge** = canopy already has a weaker version to reconcile, not copy.

### 3.1 Plugin-side (agent-runtime — how an agent *behaves*)

| # | Capability | Source (ace) | Lands | ✅ generic | Action | ACE keeps |
|---|---|---|---|---|---|---|
| P1 | `run_state.yaml` phase/step/**products** state machine + **write-back contract** (two-level merge, CAS, stub-fill verifier) | `agents/orchestrator-reference.md`, `lib/run-paths.ts` | plugin | ✅ | **Converge** with canopy `scripts/ddd/runstate.py` + `run_pipeline.py` into one runtime | the 10 phase *names* + ordering |
| P2 | **Artifact-manifest registry** (producer/consumer/phase/required graph) | `lib/artifact-manifest.ts`, `artifact-manifest-roles.ts` | plugin | ✅ | Promote to framework primitive; manifest *content* stays per-agent | ACE's populated manifest |
| P3 | **QA-gate → eval → verdict-schema → calibration → `opp-eval` aggregator** (the crown jewel) | `lib/verdict-schema.ts`, `lib/qa-*`, `skills/README.md`, `eval-calibration/` | plugin **+** web | ✅ | **Converge** with canopy `visual-judge` + canopy-web `/api/evals`. Verdict schema becomes the framework's eval contract | per-skill *rubric content* |
| P4 | **Decisions log** (AI-default + human-override, Doc↔YAML round-trip) | `lib/decisions-*.ts` | plugin | ✅ | Promote as-is; generic "auditable decisions with override" | — |
| P5 | **Capability-map MCP** (atom = stable contract, backend swappable: REST/Playwright/…) | `mcp/{ocs,connect,mobile}/capability-map.ts` | plugin | ✅ | Standardize the *pattern* in the framework | the connect/ocs/mobile *atoms* |
| P6 | **Orchestrator-reads-its-own-procedure-doc at L0** + fork semantics (per-run vs per-opp scope, copy-forward fork) | `agents/ace-orchestrator.md` | plugin | ✅ | Standardize the convention; each agent supplies its own `<domain>-orchestrator.md` | ACE's orchestrator doc |
| P7 | **Generic Drive/Docs/Slides/Sheets MCP** (32 tools, zero domain logic) | `mcp/google-drive-server.ts` | plugin | ✅ | Move into Canopy as the shared gdrive MCP | — |
| P8 | **`video-engine`** (Remotion narrated-demo renderer) | already byte-identical in both repos | plugin | ✅ | Collapse the two vendored copies into **one published package**; both consume | Connect-branded *templates* |

### 3.2 Web-side (substrate — what makes state/ingest/tenancy/API real)

| # | Capability | Source (ace-web) | Lands | ✅ generic | Action | Notes |
|---|---|---|---|---|---|---|
| W1 | **Multi-tenant workspaces + RBAC + invites + auto-join-domains** | `apps/workspaces` | web | ✅ | **Net-new** for canopy-web (today single-tenant). The tenancy spine. | one ACE field (`drive_root_folder_id`) to generalize |
| W2 | **Unified Agent ⊕ run lifecycle** (the keystone, §2.2) | `apps/agents` (canopy) ⊕ `apps/opps` run model (ace-web) | web | ✅ | **Synthesize.** Board gains runs/steps/artifacts/verdicts; "who has the ball" driven by run state + gates | storage-adapter pluggable (§4.1) |
| W3 | **Transcript ingest + cost/structure aggregation** (sidechain attribution via `parentUuid`) | `apps/ingest` | web | ✅ | **Net-new** for canopy-web | only Claude price table is model-specific |
| W4 | **WebSocket chat sessions + presence + drafts + `turn_driver`** | `apps/sessions` | web | ✅ | **Converge** canopy-web's SSE onto ace-web's richer WS model | opp FKs already nullable |
| W5 | **Pluggable CLI/API AI backend** (Protocol, subprocess pool, circuit breaker) | `apps/common/chat_backend.py` | web | ✅ | **Converge** with canopy-web's `AI_BACKEND` switch onto the richer one | — |
| W6 | **Drive read-through cache + Changes API + ETag** | `apps/opps/snapshot_cache.py`, `drive_changes.py` | web | ✅ | Harvest **as the Drive storage adapter** behind W2 (only needed for Drive-backed agents) | Drive-coupled but ACE-agnostic |
| W7 | **Service-account credential vault + impersonation RBAC + audit** | `apps/service_accounts` | web | ✅ | Net-new; generic secrets/impersonation plane | — |
| W8 | **3-pane Workbench shell + design tokens** | `frontend/components/workbench` | web | ✅ | **Converge** with `@canopy/workbench`; one shared shell | palette differs, token architecture identical |
| W9 | **PAT auth + `pat-to-session` + loopback authorize** | `apps/auth` | web | ✅ | **Converge** (already near-aligned); only OAuth provider differs | — |

### 3.3 What ACE keeps (the costume — never harvested)

The 10-phase pipeline *content* and ordering · all external-system backends
(`mcp/{connect,ocs,mobile}`, Connect/CommCare HQ/OCS/connect-labs) · domain vocabulary
(PDD, work order, solicitation, LLO/FLW, archetypes) · domain lib (`multimedia-*`,
`training-deck-spec`, `products-apps-schema`) · `personas/`, `templates/`, sweep
heuristics · per-skill rubric content · the mobile/AVD/Maestro emulator · the end-user
product frontend (Connect-customer surfaces).

---

## 4. The three reconciliations (the genuinely hard forks)

These are where "convergence" requires a real decision, not just a move.

### 4.1 State store: Drive-as-truth (ACE) vs DB-as-truth (canopy-web)

The single biggest impedance mismatch. **Recommendation: make the *store* pluggable behind
the run/step/artifact model.** The lifecycle **model** (W2) is the framework contract; the
**storage** is an adapter:

- **DB adapter (default)** — Postgres-backed; what Canopy-hosted agents use.
- **Drive read-through adapter** — harvested from W6; what ACE uses (its customer artifacts
  genuinely live in Drive and that's load-bearing — keep it).

This lets ACE keep Drive while new Canopy-hosted agents get Postgres, both speaking one run
model. The adapter seam is itself a clean instance of the one-way invariant.

### 4.2 MCP generation: OpenAPI-derived (ace-web) vs hand-written in-process (canopy-web)

These are actually **two different concerns** that got conflated:

- **Exposing canopy-web's *own* API as MCP** → adopt ace-web's **OpenAPI-derived**
  (`x-mcp-expose`) approach. It scales and cannot drift from the REST surface. (Canopy-web's
  `x-mcp-expose` markers already exist but are decorative — wire them up.)
- **Reaching *external* systems** → adopt ACE's **capability-map / CompositeBackend** pattern
  (P5) as the framework standard.

So: not "pick one," but "use each for the concern it fits."

### 4.3 Skill/phase registry coupling

ace-web reads phase/skill definitions from ACE plugin frontmatter (`ACE_PLUGIN_PATH`).
**Generalize to a pluggable phase/step registry** so Canopy can host *any* agent's
lifecycle, with ACE registering its phases as one consumer.

---

## 5. The invariant in the current code (proof it's real, and the one leak)

- **Clean example (keep this purity):** canopy-web `apps/agents` is *completely*
  domain-agnostic — zero canopy/skill coupling. ACE's `lib/` is already separable from
  `mcp/connect`. The seams are **latent, not absent.**
- **The one leak to fix early:** `apps/projects` is a generic registry that leaks
  `skills[]` / `skill_name` (canopy's product model) into it. That's exactly the kind of
  generic→specific import the invariant forbids. Fix it in Wave 0.
- **Enforcement:** add an import-linter / dependency test that fails CI if a framework
  module imports an agent-specific module. This is what keeps the blend cuttable without
  anyone having to remember the rule.

---

## 6. Suggested sequencing (waves)

Ordered by (value to the new agents *now*) × (reversibility) × (unblocks later waves).
**Constraint:** ACE must keep shipping throughout (it's in active development).

**Wave 0 — Establish the invariant & the shared agent-client (cheap, foundational)**
- Write the one-way-dependency rule into both CLAUDE.mds; add the import-linter CI check (§5).
- Fix the `projects.skills[]` leak.
- **Standardize the shared agent-client.** The corrected first move (per §2.2a): not "wire
  the dead board" — the board has a live consumer (Echo) — but **collapse the hand-rolled
  clients into one**. Echo wrote `echo_canopy.py` + `echo_tasks.py` (~120 lines: PAT
  resolution, register, syncs, work-products, skills, tasks, commands drain/apply); the
  canopy plugin duplicates the same PAT client across 4 scripts; ACE has its own. Ship one
  shared client (the framework's `agents` SDK + thin CLI), with **Echo as the reference
  consumer** and the canopy plugin + ACE as the next adopters. Spec:
  `2026-06-28-shared-agent-client-design.md`. ACE-independent, fully reversible.

**Wave 1 — Unify the agent model (the keystone, W2)**
- Define the framework's run/step/artifact/verdict data model in canopy-web, with the
  storage adapter seam (§4.1). Board "who has the ball" becomes run-state-driven.

**Wave 2 — Harvest the plugin-side crown jewels (P1–P4, P7, P8)**
- Converge run_state + manifest + the QA/eval/verdict/calibration stack + decisions log
  into the canopy plugin / shared runtime. Promote `video-engine` + gdrive MCP to single
  shared packages. New agents now self-grade like ACE.

**Wave 3 — Harvest the web substrate (W1, W3–W9)**
- Multi-tenant workspaces, ingest + cost, WS sessions (converge SSE), service-accounts,
  AI-backend convergence, workbench-shell convergence. Canopy-web is now a real
  multi-tenant host; the next webserver is cheap.

**Wave 4 — ACE migrates onto Canopy**
- `ace` plugin imports the shared agent-runtime; `ace-web` consumes canopy-web framework
  code (standalone-deployable, or a tenant). Reconcile MCP strategy (§4.2). Prove the
  **cuttable test** by keeping ace-web deployable for external customers on framework code.

---

## 7. Acceptance — "cuttable" tests

The framework is correctly factored when all three hold:

1. **Import test:** no framework module imports any agent-specific module (CI-enforced).
2. **Build test:** a webserver can be built from canopy-web's framework apps **without**
   the canopy product apps (collections / skills / workspace / DDD).
3. **Standalone test:** ACE can deploy for external Connect customers **without** requiring
   access to the central canopy-web instance — on framework code, not a private copy.

---

## 8. Deferred decisions (intentionally open)

- Whether Canopy's own product (skill-authoring / DDD) eventually becomes **formally "just
  another agent"** on the framework. Per the blend stance: don't force it; the invariant
  keeps it cuttable if we ever want to.
- Default storage adapter per hosted agent (Drive vs DB) — decide per agent at Wave 1+.
- Where the central multi-tenant host lives (GCP vs AWS) and whether ace-web's `/ace/`
  path-prefix coupling is lifted.
- OpenAPI-derived MCP rollout depth in canopy-web (which endpoints opt in first).

---

## 9. One-paragraph summary

Canopy is the framework; ACE depends on it. We relocate ACE's generic inventions — the run
lifecycle, artifact manifest, the QA/eval/verdict/calibration stack, decisions log,
capability-map MCP, the gdrive MCP, the video engine on the plugin side; multi-tenancy,
ingest+cost, websocket sessions, service accounts, the workbench shell on the web side —
into Canopy, converging with the weaker versions Canopy already has rather than copying.
The keystone is fusing canopy-web's *board* with ace's *run lifecycle* into one Agent model.
We don't decompose anything; we hold a single invariant — generic never imports specific —
that keeps the blend cuttable, so the day ACE ships to Connect's customers, it lifts out
cleanly onto framework code while still running just as happily inside Canopy.
