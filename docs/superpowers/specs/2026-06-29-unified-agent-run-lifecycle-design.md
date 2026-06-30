# Unified Agent ⊕ Run Lifecycle — the keystone (Wave 1)

**Status:** Draft for review · **Date:** 2026-06-29 · **Author:** Jonathan + Claude
**Parent:** `2026-06-24-canopy-framework-harvest-design.md` (W2, §2.2 the keystone; §4.1 the storage reconciliation)

> Design spec for one wave, not the whole program. Turns into an implementation
> plan next. Grounded in two code audits: canopy-web `apps/agents`/`apps/runs`
> and ace-web `apps/opps`.

---

## 1. Problem

Two halves of one model live in two different systems:

- **canopy-web has a board, no run lifecycle.** `apps/agents` fully persists an
  Agent + its board (`AgentTask`, the `AgentTaskCommand` drain queue, syncs,
  work-products, skills). "Who has the ball" is already real: `AgentTask.assigned`
  (agent vs human), the pending-command queue, and the typed `/needs-you` inbox
  (review / question / notify). What it lacks: any notion of a **run** the agent
  executes — steps, artifacts, verdicts, gates.
- **ace-web has a rich run lifecycle, no board.** `apps/opps` drives a
  run → step → artifact → verdict/QA → decision → gate → **fork** lifecycle. But
  it is **not in Postgres**: it lives as YAML on Drive (`run_state.yaml`,
  `verdicts/*.yaml`, `decisions.yaml`, `<N>-<phase>/` artifact folders). Postgres
  holds only a thin `OppWorkspace` wrapper; the lifecycle objects (`RunDetail`,
  `StepManifest`, `JudgeVerdict`, `QAResult`, `Decision`, `ArtifactRef`) are
  dataclasses **synthesized at read-time** from Drive, with run status **derived**
  from a phases map, never stored.

These are two views of the same object. The single most important framework move
(§2.2) is to **fuse them**: an Agent gains a run lifecycle, and the board's "who
has the ball" becomes *driven by* run state + pause gates. Everything else in the
harvest is plumbing around this synthesis.

The catch that makes it hard (§4.1): **two storage truths.** ACE's run state is
**Drive-as-truth** (load-bearing — its customer artifacts genuinely live in
Drive); canopy-web is **DB-as-truth**. We must not force ACE into Postgres tables
(that breaks Drive-truth and ACE keeps shipping), nor leave canopy-hosted agents
without real rows.

## 2. Goal & non-goals

**Goal:** one **run-lifecycle model** that an Agent owns, defined as an
adapter-backed **read model** so the *same* lifecycle can be stored two ways — and
wire the existing board so a run's state determines who has the ball.

**The bar (set by the maintainer):** Drive storage is **just as first-class as DB
storage** — both adapters are implemented in this wave, not deferred. The wave is
not "meaningful" until it is **100% working for ACE**: the Drive adapter, running
in canopy-web, reads ACE's real Drive run state and reproduces the full run
lifecycle at **parity with ace-web `apps/opps`** (run/steps/artifacts/verdicts/QA/
decisions/gates/**fork**). No thin slice; full completeness before review.

**Non-goals (this wave):**
- **Not** the QA-gate → eval → verdict-schema → **calibration** → aggregator crown
  jewel (that's plugin-side **Wave 2**, P3). We model *where a verdict attaches* and
  reproduce ACE's existing verdict/QA *reads*, not the scoring/calibration engine.
- **Not** multi-tenant workspaces (W1, separate). Runs hang off the existing
  single-tenant Agent.
- **Not** a frontend build. API + model only; the board UI already exists.
- **No** breaking change to `/api/agents/*` or the DDD `apps/runs` aggregation
  (which stays exactly as-is — see §6).

## 3. The model (storage-agnostic read model)

The lifecycle is a **read model** (Pydantic), independent of how it's stored.
Names generalized from ACE's dataclasses:

```
Run         id, agent, label, mode(review|auto), status(derived), created_at,
            completed_at, current_step, forked_from(run_id?|null), session_link?
Step        key, ordinal, title, status(pending|running|complete|failed|skipped),
            started_at, completed_at, error?
Artifact    step_key, name, url|ref, mime_type, size?, role?(producer skill/tag)
Verdict     step_key, kind(judge|qa), score?, passed?, criteria{}, rationale,
            evaluated_at         # QA is binary + gates the judge verdict
Decision    step_key, question, ai_default, override?, status(ai-default|overridden),
            reasoning, evidence_basis     # the auditable decisions log (ACE P4)
Gate        step_key, decision?, decided_by?, decided_at?, note   # a pause point
```

Key properties carried over from the ACE source (they're load-bearing, not
incidental):
- **Run status is derived, not stored** — computed from the steps/phases map
  (all terminal → complete; else in_progress). Forks mark steps `< fork` done.
- **Verdicts are asynchronous to steps** and QA gates the judge (QA fail →
  judge `incomplete`).
- **Artifacts attribute to a producing step/skill** via a manifest, many-per-step.
- **Fork mints a new run under the same agent** (copy steps `< fork`, fresh state
  onward); modes `keep-overrides-only | keep-all` for the decisions log.

## 4. The storage adapter (the §4.1 reconciliation)

The model is fronted by a **`RunStore` Protocol** — the minimal interface the
lifecycle needs, distilled from ACE's `DriveClient` contract:

```python
class RunStore(Protocol):
    def get_run(agent, run_id) -> Run: ...
    def list_runs(agent) -> list[RunSummary]: ...
    def list_steps(agent, run_id) -> list[Step]: ...
    def list_artifacts(agent, run_id, step_key=None) -> list[Artifact]: ...
    def list_verdicts(agent, run_id) -> list[Verdict]: ...
    def record_gate(agent, run_id, step_key, decision) -> Gate: ...   # write
    def fork(agent, run_id, at_step, mode, edits) -> RunSummary: ...   # write
    # + an invalidation signal: changed_ids since a cursor (for cache busting)
```

Two implementations, **both first-class and built in this wave**:

- **DB adapter (default)** — canopy-hosted agents. Backs the read model with real
  Postgres rows (`AgentRun`, `AgentRunStep`, `AgentRunArtifact`, `AgentRunVerdict`,
  `AgentRunDecision`, `AgentRunGate`). Fork = a CREATE (+ copy step/decision rows);
  gate = an UPDATE; phase advance = step-row updates. No external cache needed —
  the DB *is* the index.
- **Drive adapter (first-class, ACE parity)** — wraps a read-through-Drive client +
  snapshot cache + Changes-API invalidation, parsing `run_state.yaml` / `verdicts/`
  / `decisions.yaml` / phase folders into the **same** read model. This is the
  harvest of ace-web's `apps/opps` read path (`sync.py`, `parsers.py`,
  `drive_cache.py`, `snapshot_cache.py`, `drive_changes.py`, `opp_forker.py`) into
  a framework adapter. Acceptance is parity with `apps/opps` on real ACE runs.
  **Dependency:** canopy-web needs Drive read access (a service account) to reach
  ACE's run folders — see §9.

This is the clean instance of the one-way invariant: the lifecycle (framework)
depends on the `RunStore` Protocol, never on Drive or Postgres specifics.

## 5. Fusing the board with run state ("who has the ball" becomes run-driven)

The board already encodes who-has-the-ball; this wave makes a **run** able to
drive it, without rebuilding the board:

- An `AgentTask` gains an optional `run_id` ("this task is: execute this run").
- A run's state projects onto the board / `/needs-you`:
  - a **running step** → the agent has the ball (task `in_progress`, assigned=agent);
  - an **open gate** awaiting a human → a **review** item in `/needs-you`;
  - a **failed step / blocked gate** → a **question** item (agent waiting on a person);
  - a **completed run** → a **notify** item.
- The existing `AgentTaskCommand` drain stays the human→agent control channel;
  recording a **gate decision** is the run-lifecycle analogue of applying a command.

So the board is the *operator surface* and the run is the *execution substrate*;
the projection rules are the fusion. No new inbox concept — we reuse
review/question/notify.

## 6. Reconciliation with the existing `apps/runs`

`apps/runs` is **DDD-specific read-time aggregation** over `Walkthrough` +
`ReviewRequest`, with **zero DB models** and a string `run_id`. It is **not** the
generic lifecycle and must not be conflated. The generic model lands as a **new
home** (naming TBD — see §8) and `apps/runs` is left untouched. Later (Wave 2+),
DDD *could* be re-expressed as one consumer of the generic run model, but that is
explicitly out of scope here.

## 7. Build order (to full completeness — my call per "do it in the order you think best")

The whole model, both adapters, ACE parity — sequenced so each layer is testable
before the next, ending at the ACE-parity gate:

1. **Read model + `RunStore` Protocol** (Pydantic; the shared contract both
   adapters return). The neutral substrate.
2. **DB adapter + migrations** for the full model (`AgentRun`, `AgentRunStep`,
   `AgentRunArtifact`, `AgentRunVerdict`, `AgentRunDecision`, `AgentRunGate`),
   incl. fork (CREATE + copy) and the decisions log. Unit-tested against the read
   model with a fake/in-memory store first.
3. **Drive adapter** — port ace-web `apps/opps`'s read path (state/verdict/QA/
   decision parsing, artifact attribution, step synthesis, fork, cache +
   Changes-API invalidation) behind the same Protocol. The big lift.
4. **Parity harness** — a test that runs the Drive adapter against real ACE run
   folders and asserts the read model matches what ace-web `apps/opps` produces.
   This is the "100% working for ACE" gate.
5. **REST** for the unified runs (`/api/agents/{slug}/runs/…`, steps, gate, fork)
   + **the board fusion** (run state → `/needs-you`; `AgentTask.run_id`).
6. **Drive access wiring** in canopy-web (service-account creds / settings) so the
   Drive adapter actually reaches ACE's folders in a deployed/CI context.

## 8. Decisions (with recommendations)

- **Read-model-first, not tables-first** *(recommended)*. Model the lifecycle as a
  Pydantic read model behind a `RunStore` Protocol; the DB adapter persists rows,
  the Drive adapter reads YAML. This is the only shape that lets ACE keep
  Drive-truth while canopy gets DB-truth (§4.1). The alternative — canonical
  Django tables only — would force ACE off Drive and is rejected.
- **Lifecycle owned by the Agent, in a new home.** A run belongs to an agent.
  Recommend a new app `apps/agent_runs` (framework tier) FK'd to `agents.Agent`,
  rather than overloading `apps/agents` (keeps the board app focused) or colliding
  with product `apps/runs`. *Open: app name.*
- **Verdict is a first-class read-model object** persisted by the DB adapter
  (canopy-web has none today — it's ad-hoc JSON). The *scoring engine* stays Wave 2.
- **Reuse review/question/notify** for the board projection — do not invent a new
  inbox type.

## 9. The critical dependency (must resolve to reach "100% working for ACE")

"Working for ACE" means the **Drive adapter reaches ACE's actual Drive run
folders** from canopy-web. ace-web does this with a Google **service account**
(its `DriveClient` / `GoogleDriveClient`). canopy-web today has **no** Drive
integration. So full completeness requires one of:
- **Share ACE's Drive + service-account creds with canopy-web** (canopy-web gets
  read access to the `ACE/<slug>/runs/…` tree). Then parity is testable against
  live data.
- **Or** a captured **fixture corpus** of real ACE run folders (the `run_state.yaml`
  / `verdicts/` / `decisions.yaml` trees) checked in, so the Drive adapter is built
  + parity-tested against recorded truth without live creds. *(Recommended to start
  — it makes the parity harness deterministic and unblocks the build immediately;
  live creds can follow for the deployed path.)*

Either way this is infra, not just code — flagged because it gates the acceptance
bar. Minor still-open: app name (`apps/agent_runs`?), and whether a Run carries a
`session_link` (cheap; lean yes).

## 10. Acceptance (the "100% working for ACE" gate)

1. **ACE parity (the bar):** the Drive adapter, given real ACE run folders, returns
   a run lifecycle (run/steps/artifacts/verdicts/QA/decisions/gates, + fork)
   **matching ace-web `apps/opps`** for the same opp — verified by the parity harness.
2. **DB adapter:** a canopy-hosted agent can create a run, advance steps, attach
   artifacts + verdicts, record a gate, and fork — persisted as rows, same read model.
3. **Board fusion:** an open gate surfaces in `/needs-you` as **review**; a running
   step shows the agent holding the ball; completion shows as **notify**.
4. **Invariant:** the lifecycle imports only the `RunStore` Protocol — no Drive or
   Postgres specifics leak into it (caught by the Wave 0 boundary test).
5. `apps/agents/*` and DDD `apps/runs` unchanged; ace-web untouched.

## 10. Acceptance

1. A canopy-hosted agent can create a run, advance steps, attach artifacts +
   verdicts, and record a gate decision — all through the `RunStore` DB adapter,
   persisted as rows.
2. An open gate surfaces in that agent's `/needs-you` as a **review**; a running
   step shows the agent holding the ball; completion shows as **notify**.
3. The lifecycle code imports only the `RunStore` Protocol — no Drive/Postgres
   specifics (one-way invariant; caught by the Wave 0 boundary test).
4. `apps/agents/*` and DDD `apps/runs` are unchanged. ACE is untouched.
