"""The `RunStore` Protocol and its adapters.

`RunStore` is the minimal interface the run lifecycle needs (distilled from ACE's
`DriveClient` contract in the design spec §4). The lifecycle depends only on this
Protocol — never on Drive or Postgres specifics. That one-way invariant is what
lets ACE keep Drive-as-truth while canopy-hosted agents get DB-as-truth.

Adapters here:
- `InMemoryRunStore` — dict-backed, for tests and as the reference behaviour.
- `DbRunStore` — reads `apps.agent_runs.models` rows into the read model. Reads +
  `record_gate` are implemented; `fork` is the next layer (raises NotImplemented).

The Drive adapter (ACE parity) lands in a later phase behind this same Protocol.
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
    derive_status,
)


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

    def fork(self, agent: str, run_id: str, at_step: str, mode: str = "keep-overrides-only", edits: dict | None = None) -> RunSummary:
        """Mint a new run under the same agent, copying steps < at_step. A write."""
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

    def fork(self, agent: str, run_id: str, at_step: str, mode: str = "keep-overrides-only", edits: dict | None = None) -> RunSummary:
        raise NotImplementedError("fork is the next layer — see Wave 1 Phase 2")

    def changed_ids(self, agent: str, cursor: str | None = None) -> tuple[list[str], str]:
        start = int(cursor) if cursor else 0
        ids = [run_id for seq, ag, run_id in self._changed if seq > start and ag == agent]
        # de-dup preserving order
        seen: set[str] = set()
        out = [i for i in ids if not (i in seen or seen.add(i))]
        return out, str(self._cursor)


# ---------------------------------------------------------------------------
# DB adapter — reads ORM rows into the read model
# ---------------------------------------------------------------------------
class DbRunStore:
    """A `RunStore` backed by `apps.agent_runs.models` Postgres rows.

    Reads (`get_run`, `list_runs`, `list_steps`, `list_artifacts`,
    `list_verdicts`) + `record_gate` are implemented. `fork` (CREATE + copy
    steps/decisions) is the next layer.
    """

    def get_run(self, agent: str, run_id: str) -> Run:
        from .models import AgentRun

        run = (
            AgentRun.objects.select_related("agent", "forked_from")
            .get(agent__slug=agent, pk=run_id)
        )
        steps = list(run.steps.all())
        step_key_by_id = {s.pk: s.key for s in steps}

        read_steps = [_step_to_schema(s) for s in steps]
        artifacts: list[Artifact] = []
        verdicts: list[Verdict] = []
        decisions: list[Decision] = []
        gates: list[Gate] = []
        for s in steps:
            key = step_key_by_id[s.pk]
            artifacts += [_artifact_to_schema(a, key) for a in s.artifacts.all()]
            verdicts += [_verdict_to_schema(v, key) for v in s.verdicts.all()]
            decisions += [_decision_to_schema(d, key) for d in s.decisions.all()]
            gates += [_gate_to_schema(g, key) for g in s.gates.all()]

        run_model = Run(
            id=str(run.pk),
            agent_slug=run.agent.slug,
            label=run.label,
            mode=run.mode,
            current_step=run.current_step,
            forked_from=str(run.forked_from_id) if run.forked_from_id else None,
            session_link=run.session_link,
            created_at=run.created_at,
            completed_at=run.completed_at,
            steps=read_steps,
            artifacts=artifacts,
            verdicts=verdicts,
            decisions=decisions,
            gates=gates,
        )
        return run_model.with_derived_status()

    def list_runs(self, agent: str) -> list[RunSummary]:
        from .models import AgentRun

        runs = (
            AgentRun.objects.filter(agent__slug=agent)
            .select_related("agent")
            .prefetch_related("steps")
        )
        out: list[RunSummary] = []
        for run in runs:
            steps = [_step_to_schema(s) for s in run.steps.all()]
            out.append(
                RunSummary(
                    id=str(run.pk),
                    agent_slug=run.agent.slug,
                    label=run.label,
                    mode=run.mode,
                    status=derive_status(steps),
                    current_step=run.current_step,
                    forked_from=str(run.forked_from_id) if run.forked_from_id else None,
                    session_link=run.session_link,
                    created_at=run.created_at,
                    completed_at=run.completed_at,
                )
            )
        return out

    def list_steps(self, agent: str, run_id: str) -> list[Step]:
        from .models import AgentRunStep

        steps = AgentRunStep.objects.filter(run__agent__slug=agent, run_id=run_id)
        return [_step_to_schema(s) for s in steps]

    def list_artifacts(self, agent: str, run_id: str, step_key: str | None = None) -> list[Artifact]:
        from .models import AgentRunArtifact

        qs = AgentRunArtifact.objects.filter(
            step__run__agent__slug=agent, step__run_id=run_id
        ).select_related("step")
        if step_key is not None:
            qs = qs.filter(step__key=step_key)
        return [_artifact_to_schema(a, a.step.key) for a in qs]

    def list_verdicts(self, agent: str, run_id: str) -> list[Verdict]:
        from .models import AgentRunVerdict

        qs = AgentRunVerdict.objects.filter(
            step__run__agent__slug=agent, step__run_id=run_id
        ).select_related("step")
        return [_verdict_to_schema(v, v.step.key) for v in qs]

    def record_gate(self, agent: str, run_id: str, step_key: str, decision: str, decided_by: str = "", note: str = "") -> Gate:
        from .models import AgentRunGate, AgentRunStep

        step = AgentRunStep.objects.get(run__agent__slug=agent, run_id=run_id, key=step_key)
        now = dt.datetime.now(dt.timezone.utc)
        gate = (
            AgentRunGate.objects.filter(step=step, decided_at__isnull=True)
            .order_by("id")
            .first()
        )
        if gate is None:
            gate = AgentRunGate(step=step)
        gate.decision = decision
        gate.decided_by = decided_by
        gate.note = note
        gate.decided_at = now
        gate.save()
        return _gate_to_schema(gate, step_key)

    def fork(self, agent: str, run_id: str, at_step: str, mode: str = "keep-overrides-only", edits: dict | None = None) -> RunSummary:
        # TODO(Wave 1 Phase 2): CREATE a new AgentRun under the same agent, copy
        # steps (and decisions per `mode`) with ordinal < the at_step ordinal,
        # set forked_from, and return the new run's summary.
        raise NotImplementedError("DbRunStore.fork is the next layer — see Wave 1 Phase 2")

    def changed_ids(self, agent: str, cursor: str | None = None) -> tuple[list[str], str]:
        from django.utils.dateparse import parse_datetime

        from .models import AgentRun

        qs = AgentRun.objects.filter(agent__slug=agent)
        since = parse_datetime(cursor) if cursor else None
        if since is not None:
            qs = qs.filter(created_at__gt=since)
        qs = qs.order_by("created_at")
        ids = [str(r.pk) for r in qs]
        newest = qs.last() or AgentRun.objects.filter(agent__slug=agent).order_by("created_at").last()
        new_cursor = newest.created_at.isoformat() if newest else (cursor or "")
        return ids, new_cursor


# ---- ORM-row → read-model adapters ----
def _step_to_schema(s) -> Step:
    return Step(
        key=s.key,
        ordinal=s.ordinal,
        title=s.title,
        status=s.status,
        started_at=s.started_at,
        completed_at=s.completed_at,
        error=s.error,
    )


def _artifact_to_schema(a, step_key: str) -> Artifact:
    return Artifact(
        step_key=step_key,
        name=a.name,
        url=a.url,
        mime_type=a.mime_type,
        size=a.size,
        role=a.role,
    )


def _verdict_to_schema(v, step_key: str) -> Verdict:
    return Verdict(
        step_key=step_key,
        kind=v.kind,
        score=v.score,
        passed=v.passed,
        criteria=v.criteria,
        rationale=v.rationale,
        evaluated_at=v.evaluated_at,
    )


def _decision_to_schema(d, step_key: str) -> Decision:
    return Decision(
        step_key=step_key,
        question=d.question,
        ai_default=d.ai_default,
        override=d.override,
        status=d.status,
        reasoning=d.reasoning,
        evidence_basis=d.evidence_basis,
    )


def _gate_to_schema(g, step_key: str) -> Gate:
    return Gate(
        step_key=step_key,
        decision=g.decision,
        decided_by=g.decided_by,
        decided_at=g.decided_at,
        note=g.note,
    )
