"""The Django ORM `RunStore` adapter — `DbRunStore`.

The Django-free pieces of this module moved to the installable ``canopy_agent_runs``
package: the `RunStore` Protocol, `InMemoryRunStore`, the `FORK_MODES` /
`_apply_decision_edit` fork contract, and the read model. What remains here is
the ONE adapter that talks to the ORM (`apps.agent_runs.models`) — DB-as-truth
for canopy-hosted agents.

For back-compat, the library's `RunStore` / `InMemoryRunStore` / `FORK_MODES`
(and `_apply_decision_edit`) are re-exported from this module so existing
importers of ``apps.agent_runs.stores`` keep working unchanged.
"""
from __future__ import annotations

import datetime as dt

# Re-exported from the library so `apps.agent_runs.stores.<X>` keeps resolving.
from canopy_agent_runs.stores import (  # noqa: F401
    FORK_MODES,
    InMemoryRunStore,
    RunStore,
    _apply_decision_edit,
)

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

# Decision write fields — kept local to the ORM adapter (the only consumer here).
_DECISION_WRITE_FIELDS = (
    "question", "ai_default", "override", "status", "reasoning", "evidence_basis",
)


# ---------------------------------------------------------------------------
# DB adapter — reads ORM rows into the read model
# ---------------------------------------------------------------------------
class DbRunStore:
    """A `RunStore` backed by `apps.agent_runs.models` Postgres rows.

    Reads (`get_run`, `list_runs`, `list_steps`, `list_artifacts`,
    `list_verdicts`) and writes (`record_gate`, `record_decision`, `fork`) are
    all implemented. `fork` CREATEs a new `AgentRun` and copies trimmed
    steps/decisions per `mode`/`edits`.
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

    def record_decision(self, agent: str, run_id: str, step_key: str, decision_fields: dict) -> Decision:
        from .models import AgentRunDecision, AgentRunStep

        step = AgentRunStep.objects.get(run__agent__slug=agent, run_id=run_id, key=step_key)
        fields = {k: v for k, v in decision_fields.items() if k in _DECISION_WRITE_FIELDS}
        decision = AgentRunDecision.objects.create(step=step, **fields)
        return _decision_to_schema(decision, step_key)

    def record_verdict(
        self, agent: str, run_id: str, step_key: str, *,
        kind: str, score: float | None = None, passed: bool | None = None,
        criteria: dict | None = None, rationale: str = "",
        evaluated_at: dt.datetime | None = None,
    ) -> Verdict:
        from .models import AgentRunStep, AgentRunVerdict

        step = AgentRunStep.objects.get(run__agent__slug=agent, run_id=run_id, key=step_key)
        verdict = AgentRunVerdict.objects.create(
            step=step, kind=kind, score=score, passed=passed,
            criteria=criteria or {}, rationale=rationale,
            evaluated_at=evaluated_at or dt.datetime.now(dt.timezone.utc),
        )
        return _verdict_to_schema(verdict, step_key)

    def fork(self, agent: str, run_id: str, at_step: str, mode: str = "keep-overrides-only", edits: dict | None = None) -> RunSummary:
        from django.db import transaction

        from .models import (
            AgentRun,
            AgentRunDecision,
            AgentRunStep,
            AgentRunVerdict,
        )

        if mode not in FORK_MODES:
            raise ValueError(f"unknown fork mode {mode!r}; expected one of {FORK_MODES}")

        source = AgentRun.objects.select_related("agent").get(agent__slug=agent, pk=run_id)
        source_steps = list(source.steps.all().order_by("ordinal", "id"))
        fork_step = next((s for s in source_steps if s.key == at_step), None)
        if fork_step is None:
            raise ValueError(f"no step {at_step!r} in run {run_id!r}")
        fork_ordinal = fork_step.ordinal
        edits = edits or {}

        with transaction.atomic():
            new_run = AgentRun.objects.create(
                agent=source.agent,
                label=source.label,
                mode=source.mode,
                current_step=at_step,
                forked_from=source,
            )
            for s in source_steps:
                kept = s.ordinal < fork_ordinal
                new_step = AgentRunStep.objects.create(
                    run=new_run,
                    key=s.key,
                    ordinal=s.ordinal,
                    title=s.title,
                    status=AgentRunStep.COMPLETE if kept else AgentRunStep.PENDING,
                    started_at=s.started_at if kept else None,
                    completed_at=s.completed_at if kept else None,
                    error="",
                )
                if not kept:
                    continue
                # "verdict seeded" — carried-over step, not freshly judged.
                AgentRunVerdict.objects.create(
                    step=new_step,
                    kind=AgentRunVerdict.JUDGE,
                    criteria={"seeded": True},
                    rationale=f"seeded from run {source.pk}",
                )
                step_edits = edits.get(s.key, {})
                for d in s.decisions.all().order_by("id"):
                    if mode == "keep-overrides-only" and d.status != AgentRunDecision.OVERRIDDEN:
                        continue
                    fields = {
                        "question": d.question,
                        "ai_default": d.ai_default,
                        "override": d.override,
                        "status": d.status,
                        "reasoning": d.reasoning,
                        "evidence_basis": d.evidence_basis,
                    }
                    _apply_decision_edit(fields, step_edits.get(d.question))
                    AgentRunDecision.objects.create(step=new_step, **fields)

        new_steps = [_step_to_schema(s) for s in new_run.steps.all()]
        return RunSummary(
            id=str(new_run.pk),
            agent_slug=new_run.agent.slug,
            label=new_run.label,
            mode=new_run.mode,
            status=derive_status(new_steps),
            current_step=new_run.current_step,
            forked_from=str(new_run.forked_from_id) if new_run.forked_from_id else None,
            session_link=new_run.session_link,
            created_at=new_run.created_at,
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
        from apps.agents.models import Agent
        from django.db import transaction

        from .models import AgentRun, AgentRunStep

        agent_obj = Agent.objects.get(slug=agent)
        with transaction.atomic():
            run = AgentRun.objects.create(
                agent=agent_obj,
                label=label,
                mode=mode,
                current_step=current_step,
                session_link=session_link,
            )
            for i, s in enumerate(steps or []):
                AgentRunStep.objects.create(
                    run=run,
                    key=s["key"],
                    ordinal=s.get("ordinal", i),
                    title=s.get("title", ""),
                    status=s.get("status", AgentRunStep.PENDING),
                )
        read_steps = [_step_to_schema(s) for s in run.steps.all()]
        return RunSummary(
            id=str(run.pk),
            agent_slug=run.agent.slug,
            label=run.label,
            mode=run.mode,
            status=derive_status(read_steps),
            current_step=run.current_step,
            forked_from=None,
            session_link=run.session_link,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

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
        # The DB adapter has no Drive file id; the row pk is the stable handle.
        # ``path`` has no DB-native source — default "". (No ORM column added.)
        ref=str(a.pk),
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
