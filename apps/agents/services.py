"""Business logic for the agent workspace — kept out of the Ninja router so it's
unit-testable without HTTP."""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from .models import Agent, AgentSkill, AgentSync, AgentTask, AgentWorkProduct

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
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
        "sync_count": agent.syncs.count(),
        "work_product_count": agent.work_products.count(),
        "skill_count": agent.skills.count(),
        "task_count": agent.tasks.count(),
        "latest_sync_at": latest.period_end if latest else None,
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
@transaction.atomic
def sync_tasks(agent: Agent, items: list) -> dict:
    """Replace the agent's task board from the source sheet."""
    agent.tasks.all().delete()
    AgentTask.objects.bulk_create(
        [
            AgentTask(
                agent=agent,
                ext_id=t.ext_id,
                title=t.title,
                next_action=t.next_action,
                status=t.status if t.status in _VALID_TASK_STATUS else AgentTask.SUGGESTED,
                owner=t.owner,
                assigned=t.assigned,
                confidence=t.confidence,
                due=t.due,
                links=[l.model_dump() for l in t.links],
                notes=t.notes,
                position=t.position,
                source=t.source,
            )
            for t in items
        ]
    )
    return {"count": agent.tasks.count()}


def list_tasks(agent: Agent) -> list[AgentTask]:
    return list(agent.tasks.select_related("agent"))
