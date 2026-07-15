"""Business logic for the agent workspace — kept out of the Ninja router so it's
unit-testable without HTTP."""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from .models import (
    Agent,
    AgentSkill,
    AgentSync,
    AgentTask,
    AgentTaskCommand,
    AgentTurn,
    AgentWorkProduct,
)

_VALID_TASK_STATUS = {AgentTask.SUGGESTED, AgentTask.IN_PROGRESS, AgentTask.DONE, AgentTask.DECLINED}


def _aware(value):
    if isinstance(value, dt.datetime) and timezone.is_naive(value):
        return value.replace(tzinfo=dt.timezone.utc)
    return value


# ---- agents ----
def upsert_agent(data) -> Agent:
    """Create or update an agent by slug."""
    agent, _ = Agent.objects.update_or_create(
        slug=data.slug,
        defaults={
            "name": data.name,
            "description": data.description,
            "persona": data.persona,
            "email": data.email,
            "avatar_url": data.avatar_url,
        },
    )
    return agent


def list_agents() -> list[Agent]:
    return list(Agent.objects.all())


def get_agent(slug: str) -> Agent | None:
    return Agent.objects.filter(slug=slug).first()


def agent_detail(agent: Agent) -> dict:
    latest = agent.syncs.order_by("-period_end").first()
    return {
        "id": agent.id,
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description,
        "persona": agent.persona,
        "email": agent.email,
        "avatar_url": agent.avatar_url,
        "workspace_id": agent.workspace_id,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
        "sync_count": agent.syncs.count(),
        "work_product_count": agent.work_products.count(),
        "skill_count": agent.skills.count(),
        "task_count": agent.tasks.count(),
        "turn_count": agent.turns.count(),
        "latest_sync_at": latest.period_end if latest else None,
        "latest_turn_at": latest_turn.created_at if (latest_turn := agent.turns.first()) else None,
    }


# ---- syncs ----
def upsert_sync(agent: Agent, data) -> AgentSync:
    """Idempotent per (agent, period_start, period_end, source)."""
    period_start = _aware(data.period_start)
    period_end = _aware(data.period_end)
    AgentSync.objects.filter(
        agent=agent,
        period_start=period_start,
        period_end=period_end,
        source=data.source,
    ).delete()
    return AgentSync.objects.create(
        agent=agent,
        period_start=period_start,
        period_end=period_end,
        title=data.title,
        summary=data.summary,
        doc_url=data.doc_url,
        self_grades=data.self_grades,
        source=data.source,
    )


def list_syncs(agent: Agent, limit: int = 100) -> list[AgentSync]:
    return list(agent.syncs.select_related("agent")[:limit])


# ---- turns (a packaged unit of work + optional transcript link) ----
def upsert_turn(agent: Agent, data) -> AgentTurn:
    """Idempotent per (agent, cli_session_id): one turn per Claude session, so
    re-packaging the same session (e.g. once the transcript uploads) updates it."""
    turn, _ = AgentTurn.objects.update_or_create(
        agent=agent,
        cli_session_id=data.cli_session_id,
        defaults={
            "title": data.title,
            "summary": data.summary,
            "task_ext_ids": list(data.task_ext_ids),
            "work_product_urls": list(data.work_product_urls),
            "session_slug": data.session_slug,
            "share_token": data.share_token,
            "started_at": _aware(data.started_at),
            "ended_at": _aware(data.ended_at),
            "source": data.source,
        },
    )
    return turn


def list_turns(agent: Agent, limit: int = 100) -> list[AgentTurn]:
    return list(agent.turns.select_related("agent")[:limit])


# ---- work products ----
def upsert_work_products(agent: Agent, items: list) -> dict:
    """Create work products; re-posting the same url for the agent updates it."""
    created = replaced = 0
    for item in items:
        _, was_created = AgentWorkProduct.objects.update_or_create(
            agent=agent,
            url=item.url,
            defaults={
                "title": item.title,
                "kind": item.kind,
                "description": item.description,
                "tags": item.tags,
                "source": item.source,
            },
        )
        if was_created:
            created += 1
        else:
            replaced += 1
    return {"created": created, "replaced": replaced}


def list_work_products(agent: Agent, limit: int = 200) -> list[AgentWorkProduct]:
    return list(agent.work_products.select_related("agent")[:limit])


# ---- skills ----
@transaction.atomic
def replace_skills(agent: Agent, items: list) -> int:
    """Replace the agent's whole skill catalog so it mirrors the repo."""
    agent.skills.all().delete()
    AgentSkill.objects.bulk_create(
        [
            AgentSkill(
                agent=agent,
                name=s.name,
                description=s.description,
                url=s.url,
                improvement_note=s.improvement_note,
            )
            for s in items
        ]
    )
    return agent.skills.count()


def list_skills(agent: Agent) -> list[AgentSkill]:
    return list(agent.skills.select_related("agent"))


# ---- tasks ----
def _norm_status(s: str) -> str:
    return s if s in _VALID_TASK_STATUS else AgentTask.SUGGESTED


@transaction.atomic
def sync_tasks(agent: Agent, items: list) -> dict:
    """Upsert tasks from the (legacy) source sheet by ext_id. NON-destructive:
    the DB is now the source of truth, so DB-only fields (rationale/plan/…) and
    DB-only tasks are preserved; the sheet just sets the columns it carries."""
    created = updated = 0
    for t in items:
        _, was_created = AgentTask.objects.update_or_create(
            agent=agent,
            ext_id=t.ext_id,
            defaults=dict(
                title=t.title,
                next_action=t.next_action,
                status=_norm_status(t.status),
                owner=t.owner,
                assigned=t.assigned,
                confidence=t.confidence,
                due=t.due,
                links=[l.model_dump() for l in t.links],
                notes=t.notes,
                position=t.position,
                source=t.source,
            ),
        )
        created += int(was_created)
        updated += int(not was_created)
    return {"created": created, "count": agent.tasks.count()}


_TASK_FIELDS = ("title", "next_action", "status", "owner", "assigned", "confidence",
                "rationale", "source_url", "plan", "due", "notes", "position")


def create_task(agent: Agent, data) -> AgentTask:
    payload = {f: getattr(data, f) for f in _TASK_FIELDS if getattr(data, f, None) is not None}
    payload["status"] = _norm_status(payload.get("status", AgentTask.SUGGESTED))
    if getattr(data, "links", None):
        payload["links"] = [l.model_dump() for l in data.links]
    return AgentTask.objects.create(agent=agent, ext_id=data.ext_id, **payload)


def patch_task(task: AgentTask, data) -> AgentTask:
    """Partial update — only fields present in `data` (a dict) are written."""
    for f in _TASK_FIELDS:
        if f in data:
            setattr(task, f, _norm_status(data[f]) if f == "status" else data[f])
    if "links" in data:
        task.links = data["links"]
    task.save()
    return task


def get_task(agent: Agent, task_id: int) -> AgentTask | None:
    return agent.tasks.filter(id=task_id).select_related("agent").first()


def list_tasks(agent: Agent) -> list[AgentTask]:
    return list(agent.tasks.select_related("agent"))


# ---- task commands (the board's action queue) ----
@transaction.atomic
def create_command(agent: Agent, task, kind: str, payload: dict, created_by: str) -> AgentTaskCommand:
    """Record a board action. Some kinds apply immediately to the task; accept
    and dispatch also leave a PENDING command for the agent to drain."""
    C = AgentTaskCommand
    payload = payload or {}
    cmd = C(agent=agent, task=task, kind=kind, payload=payload, created_by=created_by)
    applied_now = True  # most kinds need no agent follow-up
    if task is not None:
        if kind == C.ACCEPT:
            task.status, task.assigned = AgentTask.IN_PROGRESS, "Echo"
            task.save(update_fields=["status", "assigned", "updated_at"])
            applied_now = False  # the agent still has to do the work
        elif kind == C.DECLINE:
            task.status = AgentTask.DECLINED
            reason = payload.get("reason", "").strip()
            if reason:
                task.notes = f"{task.notes}\nDeclined: {reason}".strip()
            task.save(update_fields=["status", "notes", "updated_at"])
        elif kind == C.REASSIGN:
            task.assigned = payload.get("assignee", task.assigned)
            task.save(update_fields=["assigned", "updated_at"])
        elif kind == C.EDIT:
            for f in ("title", "next_action", "plan", "owner", "assigned"):
                if f in payload:
                    setattr(task, f, payload[f])
            task.save()
        elif kind == C.DONE:
            task.status = AgentTask.DONE
            task.save(update_fields=["status", "updated_at"])
        elif kind == C.COMMENT:
            note = payload.get("note", "").strip()
            if note:
                task.notes = f"{task.notes}\n{note}".strip()
                task.save(update_fields=["notes", "updated_at"])
        elif kind == C.DISPATCH:
            applied_now = False  # pure agent work
    if applied_now:
        cmd.status, cmd.applied_at = C.APPLIED, timezone.now()
    cmd.save()
    return cmd


def list_commands(agent: Agent, status: str | None = None) -> list[AgentTaskCommand]:
    qs = agent.commands.select_related("task", "agent")
    if status:
        qs = qs.filter(status=status)
    return list(qs)


# ---- "Needs you" supervisor inbox ----
def _is_human(assigned: str) -> bool:
    """The task's next action waits on a person, not the agent. Mirrors the
    board's `isEcho` rule: empty or 'echo' (any case) means the agent."""
    a = (assigned or "").strip().lower()
    return a not in ("", "echo")


def _task_item(item_type: str, task: AgentTask) -> dict:
    subtitle = (task.next_action or "").strip()
    if item_type == "question" and not subtitle:
        subtitle = f"Echo is blocked, waiting on {task.assigned.strip()}"
    return {
        "type": item_type,
        "ref_kind": "task",
        "ref_id": task.id,
        "title": (task.title or task.next_action or "").strip(),
        "subtitle": subtitle,
        "url": (task.source_url or "").strip(),
        "created_at": task.updated_at,
    }


def _run_ref_id(run_id: str) -> int:
    """The NeedsYouItem.ref_id is an int; DB run pks are ints. Cast safely so a
    non-int store id (a future Drive adapter) degrades to 0 rather than raising."""
    try:
        return int(run_id)
    except (TypeError, ValueError):
        return 0


def _run_inbox_items(agent: Agent) -> tuple[list[dict], list[dict], list[dict]]:
    """Project an agent's RUN STATE onto the inbox bands (spec §5), reusing the
    existing review/question/notify types — no new types invented:

      - an OPEN gate awaiting a human decision -> a 'review'  (subtitle: gate step)
      - a FAILED step / blocked gate           -> a 'question'
      - a COMPLETED run                        -> a 'notify'

    Runs are resolved through the store resolver (DbRunStore for canopy-hosted).
    Lazy-imported here so apps.agents doesn't import apps.agent_runs at module
    load (both are framework; agent_runs imports apps.agents.models — eager
    import would cycle).

    Returns (review, question, notify) bands so the caller can interleave them
    with the task bands and keep the Review → Question → Notify ranking.
    """
    from apps.agent_runs.resolver import get_run_store

    store = get_run_store(agent)
    review: list[dict] = []
    question: list[dict] = []
    notify: list[dict] = []

    for summary in store.list_runs(agent.slug):
        run = store.get_run(agent.slug, summary.id)
        ref_id = _run_ref_id(run.id)
        label = (run.label or "").strip() or f"Run {run.id}"
        url = (run.session_link or "").strip()

        # Open gate → review (the human owes a decision before the run proceeds).
        for gate in run.gates:
            if gate.is_open:
                review.append({
                    "type": "review", "ref_kind": "run", "ref_id": ref_id,
                    "title": label, "subtitle": f"Gate awaiting decision: {gate.step_key}",
                    "url": url, "created_at": run.created_at,
                })

        # Failed step → question (the run is blocked; the agent needs help).
        for step in run.steps:
            if step.status == "failed":
                detail = (step.error or "").strip()
                subtitle = f"Step '{step.key}' failed"
                if detail:
                    subtitle = f"{subtitle}: {detail}"
                question.append({
                    "type": "question", "ref_kind": "run", "ref_id": ref_id,
                    "title": label, "subtitle": subtitle,
                    "url": url, "created_at": run.created_at,
                })

        # Completed run → notify (FYI, no gate).
        if run.status == "complete":
            notify.append({
                "type": "notify", "ref_kind": "run", "ref_id": ref_id,
                "title": label, "subtitle": "Run complete",
                "url": url, "created_at": run.completed_at or run.created_at,
            })

    return review, question, notify


def needs_you(agent: Agent, notify_limit: int = 5) -> dict:
    """The supervisor's "what does the agent need from me right now?" view.

    Aggregates human-actionable items across the board AND the run lifecycle,
    typed and ranked:
      - review:   Suggested tasks awaiting validate/decline; runs with an OPEN
                  gate awaiting a human decision.
      - question: In-progress tasks blocked on a human; runs with a FAILED step.
      - notify:   Recent FYI with no gate (a sync posted, a work product shipped,
                  a run completed).
    Ranked Review → Question → Notify. `waiting_count` counts only the gated
    (review + question) items — the "N waiting on you" badge."""
    review: list[dict] = []
    question: list[dict] = []

    # Review — every suggestion needs a human to validate or decline it.
    for t in agent.tasks.filter(status=AgentTask.SUGGESTED).order_by("position", "id"):
        review.append(_task_item("review", t))

    # Question — Echo is mid-task but the next step waits on a named person.
    for t in agent.tasks.filter(status=AgentTask.IN_PROGRESS).order_by("position", "id"):
        if _is_human(t.assigned):
            question.append(_task_item("question", t))

    # Run-state projection (spec §5): open gates → review, failed steps →
    # question, completed runs → notify.
    run_review, run_question, run_notify = _run_inbox_items(agent)
    review.extend(run_review)
    question.extend(run_question)

    items: list[dict] = review + question
    waiting_count = len(items)  # review + question are the gated items

    # Notify — recent FYI, newest first, capped. Merge syncs + work products +
    # completed runs.
    notify: list[dict] = list(run_notify)
    for s in agent.syncs.all()[:notify_limit]:
        notify.append({
            "type": "notify", "ref_kind": "sync", "ref_id": s.id,
            "title": s.title, "subtitle": "Sync posted", "url": s.doc_url,
            "created_at": s.created_at,
        })
    for w in agent.work_products.all()[:notify_limit]:
        notify.append({
            "type": "notify", "ref_kind": "work_product", "ref_id": w.id,
            "title": w.title, "subtitle": w.kind or "Work product", "url": w.url,
            "created_at": w.created_at,
        })
    notify.sort(key=lambda i: i["created_at"], reverse=True)
    items.extend(notify[:notify_limit])

    return {"agent_slug": agent.slug, "waiting_count": waiting_count, "items": items}


def apply_command(cmd: AgentTaskCommand, result_note: str = "") -> AgentTaskCommand:
    cmd.status = AgentTaskCommand.APPLIED
    cmd.applied_at = timezone.now()
    if result_note:
        cmd.result_note = result_note
    cmd.save(update_fields=["status", "applied_at", "result_note"])
    return cmd
