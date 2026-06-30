"""The `RunStore` Protocol and its Django-free adapters.

`RunStore` is the minimal interface the run lifecycle needs (distilled from ACE's
`DriveClient` contract in the design spec §4). The lifecycle depends only on this
Protocol — never on Drive or Postgres specifics. That one-way invariant is what
lets ACE keep Drive-as-truth while canopy-hosted agents get DB-as-truth.

This module is Django-free and ships in the installable `canopy_runs` package:

- `RunStore` — the Protocol every store satisfies.
- `InMemoryRunStore` — dict-backed, for tests and as the reference behaviour.
- `FORK_MODES` / `_apply_decision_edit` — the shared fork contract every adapter
  (in-memory, Drive, and the Django `DbRunStore`) implements identically.

The DB adapter (`DbRunStore`) lives in the Django app (`apps.agent_runs.stores`)
because it talks to the ORM; it imports this Protocol + read model and implements
the same contract. The Drive adapter (`canopy_runs.drive.store.DriveRunStore`)
also lives here in the package.
"""
from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable

from .schemas import (
    Artifact,
    Decision,
    Gate,
    Run,
    RunSummary,
    Step,
    Verdict,
)

# Fork modes — both copy kept (pre-fork) steps + their decisions; they differ
# only in how upstream decision rows carry forward (mirrors ACE's
# opp_forker.FORK_MODES):
#   * keep-overrides-only — only rows whose status == "overridden" survive; AI
#     defaults are dropped so the new run re-derives them.
#   * keep-all — every kept-step decision carries forward regardless of status.
FORK_MODES = ("keep-overrides-only", "keep-all")

# The mutable read-model Decision fields a write path may set (everything but
# the step_key, which is positional).
_DECISION_WRITE_FIELDS = (
    "question", "ai_default", "override", "status", "reasoning", "evidence_basis",
)


def _apply_decision_edit(fields: dict, edit) -> None:
    """Mutate a decision `fields` dict in place per a single fork `edit`.

    `edit` may be a bare string (the override answer) or a dict with any of
    `override` / `status` / `reasoning` / `evidence_basis`. Supplying an
    `override` flips status to "overridden" unless an explicit status is given.
    A falsy/None edit is a no-op.
    """
    if not edit:
        return
    if isinstance(edit, str):
        edit = {"override": edit}
    if "override" in edit and edit["override"] is not None:
        fields["override"] = edit["override"]
        fields["status"] = edit.get("status", "overridden")
    elif "status" in edit:
        fields["status"] = edit["status"]
    if "reasoning" in edit:
        fields["reasoning"] = edit["reasoning"]
    if "evidence_basis" in edit:
        fields["evidence_basis"] = edit["evidence_basis"]


@runtime_checkable
class RunStore(Protocol):
    """The minimal storage interface the run lifecycle depends on.

    All `agent` arguments are the agent slug (str); `run_id` is the store-local
    run identifier (str). Returning the storage-agnostic read model means callers
    never see Drive/Postgres specifics.
    """

    def get_run(self, agent: str, run_id: str) -> Run:
        """The full run read model (steps + artifacts + verdicts + decisions + gates)."""
        ...

    def list_runs(self, agent: str) -> list[RunSummary]:
        """Run headers for the agent, newest first."""
        ...

    def list_steps(self, agent: str, run_id: str) -> list[Step]:
        ...

    def list_artifacts(self, agent: str, run_id: str, step_key: str | None = None) -> list[Artifact]:
        ...

    def list_verdicts(self, agent: str, run_id: str) -> list[Verdict]:
        ...

    def record_gate(self, agent: str, run_id: str, step_key: str, decision: str, decided_by: str = "", note: str = "") -> Gate:
        """Record (close) a gate decision on a step. A write."""
        ...

    def record_decision(self, agent: str, run_id: str, step_key: str, decision_fields: dict) -> Decision:
        """Append an entry to the auditable decisions log on a step. A write.

        `decision_fields` carries the read-model Decision fields (`question`
        required; `ai_default` / `override` / `status` / `reasoning` /
        `evidence_basis` optional). Used by gates/steps to record what the AI
        proposed and any human override.
        """
        ...

    def fork(self, agent: str, run_id: str, at_step: str, mode: str = "keep-overrides-only", edits: dict | None = None) -> RunSummary:
        """Mint a new run under the same agent, copying steps < at_step. A write."""
        ...

    def create_run(
        self,
        agent: str,
        *,
        label: str = "",
        mode: str = "review",
        current_step: str = "",
        session_link: str = "",
        steps: list[dict] | None = None,
    ) -> RunSummary:
        """Create a fresh run (with optional seed steps) under the agent. A write.

        `steps` is a list of dicts carrying read-model Step fields
        (`key` required; `ordinal` / `title` / `status` optional). Returns the
        new run's header. Only DB-as-truth stores create runs through this API —
        Drive runs are minted by ACE itself, so `DriveRunStore.create_run` is the
        seam that stays unimplemented until/unless ACE writes through canopy.
        """
        ...

    def changed_ids(self, agent: str, cursor: str | None = None) -> tuple[list[str], str]:
        """Invalidation hook: run ids changed since `cursor`, plus a new cursor.

        For cache-busting. The DB adapter can answer from row timestamps; the
        Drive adapter from the Changes API. Returns (changed_run_ids, new_cursor).
        """
        ...


# ---------------------------------------------------------------------------
# In-memory adapter (tests + reference behaviour)
# ---------------------------------------------------------------------------
class InMemoryRunStore:
    """A dict-backed `RunStore` for tests. Holds fully-formed `Run` read models
    keyed by (agent_slug, run_id)."""

    def __init__(self) -> None:
        # {agent_slug: {run_id: Run}}
        self._runs: dict[str, dict[str, Run]] = {}
        self._cursor = 0
        self._changed: list[tuple[int, str, str]] = []  # (seq, agent, run_id)
        self._fork_seq = 0  # monotonic suffix for minted fork run-ids
        self._run_seq = 0  # monotonic suffix for minted (created) run-ids

    # -- helpers (test-facing) --
    def put_run(self, run: Run) -> Run:
        """Insert or replace a run. Recomputes derived status."""
        run = run.with_derived_status()
        self._runs.setdefault(run.agent_slug, {})[run.id] = run
        self._cursor += 1
        self._changed.append((self._cursor, run.agent_slug, run.id))
        return run

    def _require(self, agent: str, run_id: str) -> Run:
        try:
            return self._runs[agent][run_id]
        except KeyError as exc:
            raise KeyError(f"no run {run_id!r} for agent {agent!r}") from exc

    # -- RunStore --
    def get_run(self, agent: str, run_id: str) -> Run:
        return self._require(agent, run_id).with_derived_status()

    def list_runs(self, agent: str) -> list[RunSummary]:
        runs = self._runs.get(agent, {}).values()
        summaries = [
            RunSummary(
                id=r.id, agent_slug=r.agent_slug, label=r.label, mode=r.mode,
                status=r.status_from_steps(), current_step=r.current_step,
                forked_from=r.forked_from, session_link=r.session_link,
                created_at=r.created_at, completed_at=r.completed_at,
            )
            for r in runs
        ]
        summaries.sort(key=lambda s: (s.created_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)
        return summaries

    def list_steps(self, agent: str, run_id: str) -> list[Step]:
        return list(self._require(agent, run_id).steps)

    def list_artifacts(self, agent: str, run_id: str, step_key: str | None = None) -> list[Artifact]:
        arts = self._require(agent, run_id).artifacts
        if step_key is not None:
            return [a for a in arts if a.step_key == step_key]
        return list(arts)

    def list_verdicts(self, agent: str, run_id: str) -> list[Verdict]:
        return list(self._require(agent, run_id).verdicts)

    def record_gate(self, agent: str, run_id: str, step_key: str, decision: str, decided_by: str = "", note: str = "") -> Gate:
        run = self._require(agent, run_id)
        now = dt.datetime.now(dt.timezone.utc)
        gate = next((g for g in run.gates if g.step_key == step_key and g.is_open), None)
        if gate is None:
            gate = Gate(step_key=step_key)
            run.gates.append(gate)
        updated = gate.model_copy(update={
            "decision": decision, "decided_by": decided_by, "note": note, "decided_at": now,
        })
        run.gates = [updated if g is gate else g for g in run.gates]
        self._cursor += 1
        self._changed.append((self._cursor, agent, run_id))
        return updated

    def record_decision(self, agent: str, run_id: str, step_key: str, decision_fields: dict) -> Decision:
        run = self._require(agent, run_id)
        fields = {k: v for k, v in decision_fields.items() if k in _DECISION_WRITE_FIELDS}
        decision = Decision(step_key=step_key, **fields)
        run.decisions.append(decision)
        self._cursor += 1
        self._changed.append((self._cursor, agent, run_id))
        return decision

    def fork(self, agent: str, run_id: str, at_step: str, mode: str = "keep-overrides-only", edits: dict | None = None) -> RunSummary:
        if mode not in FORK_MODES:
            raise ValueError(f"unknown fork mode {mode!r}; expected one of {FORK_MODES}")
        src = self._require(agent, run_id)
        fork_step = next((s for s in src.steps if s.key == at_step), None)
        if fork_step is None:
            raise ValueError(f"no step {at_step!r} in run {run_id!r}")
        fork_ordinal = fork_step.ordinal
        edits = edits or {}

        new_steps: list[Step] = []
        new_verdicts: list[Verdict] = []
        kept_keys: set[str] = set()
        for s in src.steps:
            kept = s.ordinal < fork_ordinal
            if kept:
                kept_keys.add(s.key)
            new_steps.append(s.model_copy(update={
                "status": "complete" if kept else "pending",
                "started_at": s.started_at if kept else None,
                "completed_at": s.completed_at if kept else None,
                "error": "",
            }))
            if kept:
                # "verdict seeded" — mark the carried-over step as not freshly
                # judged (mirrors ACE's `verdict: seeded` phase sentinel).
                new_verdicts.append(Verdict(
                    step_key=s.key, kind="judge", criteria={"seeded": True},
                    rationale=f"seeded from run {run_id}",
                ))

        new_decisions: list[Decision] = []
        for d in src.decisions:
            if d.step_key not in kept_keys:
                continue
            if mode == "keep-overrides-only" and d.status != "overridden":
                continue
            fields = d.model_dump()
            _apply_decision_edit(fields, edits.get(d.step_key, {}).get(d.question))
            new_decisions.append(Decision(**fields))

        self._fork_seq += 1
        new_id = f"{run_id}-fork-{self._fork_seq}"
        new_run = Run(
            id=new_id, agent_slug=src.agent_slug, label=src.label, mode=src.mode,
            current_step=at_step, forked_from=run_id, session_link="",
            created_at=dt.datetime.now(dt.timezone.utc),
            steps=new_steps, artifacts=[], verdicts=new_verdicts,
            decisions=new_decisions, gates=[],
        )
        self.put_run(new_run)
        return RunSummary(
            id=new_run.id, agent_slug=new_run.agent_slug, label=new_run.label,
            mode=new_run.mode, status=new_run.status_from_steps(),
            current_step=new_run.current_step, forked_from=new_run.forked_from,
            session_link=new_run.session_link, created_at=new_run.created_at,
            completed_at=new_run.completed_at,
        )

    def create_run(
        self,
        agent: str,
        *,
        label: str = "",
        mode: str = "review",
        current_step: str = "",
        session_link: str = "",
        steps: list[dict] | None = None,
    ) -> RunSummary:
        self._run_seq += 1
        new_id = f"{agent}-run-{self._run_seq}"
        read_steps = [
            Step(
                key=s["key"],
                ordinal=s.get("ordinal", i),
                title=s.get("title", ""),
                status=s.get("status", "pending"),
            )
            for i, s in enumerate(steps or [])
        ]
        new_run = Run(
            id=new_id, agent_slug=agent, label=label, mode=mode,
            current_step=current_step, session_link=session_link,
            created_at=dt.datetime.now(dt.timezone.utc), steps=read_steps,
        )
        self.put_run(new_run)
        return RunSummary(
            id=new_run.id, agent_slug=new_run.agent_slug, label=new_run.label,
            mode=new_run.mode, status=new_run.status_from_steps(),
            current_step=new_run.current_step, forked_from=new_run.forked_from,
            session_link=new_run.session_link, created_at=new_run.created_at,
            completed_at=new_run.completed_at,
        )

    def changed_ids(self, agent: str, cursor: str | None = None) -> tuple[list[str], str]:
        start = int(cursor) if cursor else 0
        ids = [run_id for seq, ag, run_id in self._changed if seq > start and ag == agent]
        # de-dup preserving order
        seen: set[str] = set()
        out = [i for i in ids if not (i in seen or seen.add(i))]
        return out, str(self._cursor)
