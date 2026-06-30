# Wave 2 + Wave 3 Harvest — Execution Spec

**Status:** Active build · **Date:** 2026-06-29 · **Owner:** Claude (driving)
**Parent:** `2026-06-24-canopy-framework-harvest-design.md`
**Branch:** `wave2-3/harvest` (canopy-web) + companion work in the canopy plugin.

> Lean execution spec — built in verified increments, each TDD + green + committed.
> Not for sign-off; it's the build's own tracking contract.

## Corrected starting state (what Wave 1 already delivered)

Wave 1 (`apps/agent_runs` + `packages/canopy_runs`) built more than its commits implied:
- **Tables exist:** `AgentRunVerdict` (judge/qa, score, passed, per-dim `criteria`),
  `AgentRunDecision` (P4 ✓), `AgentRunArtifact` (role-attributed, partial P2),
  `AgentRunGate`.
- **Read model** lives in the Django-free `canopy_runs` package; `RunStore` Protocol
  has `record_gate` / `record_decision` / `fork` — **but NO `record_verdict`**, and the
  `Run` read model has a `verdicts` list with **no run-level aggregate**.

So P1 (run_state) and P4 (decisions) are done. The remaining harvest:

## Scope (in priority order)

**Wave 2 — plugin crown jewels (remaining):**
- **P3a (web, THIS spec's first increments):** verdict recording + QA-gates-judge
  enforcement + run-level eval aggregation on `agent_runs`/`canopy_runs`. The plumbing a
  self-grading agent writes to.
- **P3b (plugin):** the eval *runner* — a shared `canopy eval` lib/skill that grades an
  artifact against a rubric and POSTs a verdict (the generic port of ACE's verdict-schema +
  calibration discipline). Consumes P3a.
- **P2 (plugin):** artifact-manifest registry primitive. (Partially covered by
  `AgentRunArtifact.role`; remaining = the producer/consumer dependency graph.)
- **P7 (plugin):** generic gdrive MCP — relocate ACE's `google-drive-server.ts`. *Defer
  unless needed* (it already works in ACE).
- **P8 (plugin):** video-engine single-package consolidation. *Defer* (lowest urgency;
  both copies work).

**Wave 3 — web substrate (untouched):**
- **W1 (web, high value):** multi-tenant `workspaces` app + RBAC + invites + auto-join,
  and scope `Agent`/runs to a workspace. The real blocker for onboarding more users.
- **W3 (web):** `ingest` app — transcript upload + cost/structure rollup. Net-new.
- **W7 (web):** `service_accounts` credential vault + impersonation. Net-new.
- **W4 (web):** websocket chat sessions + presence (converge SSE). Larger; sequence after W1.
- **W5/W8/W9:** AI-backend, workbench-shell, auth convergence. *Defer* — canopy-web already
  has working versions; converge opportunistically.

## Increment order (each = TDD, green, commit)

1. **P3a-1** — `record_verdict` on `RunStore` (Protocol + InMemory + DB) + read-model
   aggregate (`Run.overall_score` weakest-link over judge verdicts; `Run.qa_gate_ok`) +
   `POST /{slug}/runs/{run_id}/steps/{step_key}/verdict`. Migration-free (uses existing
   `AgentRunVerdict` columns). ← **building now**
2. **P3a-2** — QA-gates-judge enforcement: recording a `judge` verdict on a step whose `qa`
   verdict failed marks it gated; aggregate reflects it.
3. **W1-1** — `workspaces` app: `Workspace`/`Membership`/`Invite` models + RBAC + REST.
4. **W1-2** — scope `agents` + `agent_runs` to a workspace (nullable FK, default workspace,
   non-member 404).
5. **P3b** — plugin `canopy eval` runner lib/skill (consumes P3a verdict endpoint).
6. **W3** — `ingest` app (transcript + cost rollup).
7. **W7** — `service_accounts` vault.
8. Remaining (W4, P2 graph, P7, P8) as pulled.

## Invariant

All new framework apps stay framework-tier: may FK `agents.Agent` / `workspaces.Workspace`;
must not import product apps (`skills`, `collections`, `workspace`, `reviews`, `runs`).
Enforced by the Wave 0 boundary check.
