"""The /supervisor connect snapshot — current runner status + per-agent waiting
counts for a user, built request-free (a socket has no HttpRequest and is not
tenant-pinned, so it uses the same 'unpinned' visibility branch the REST
_visible_agent_workspace_ids / _runner_visibility_q use)."""
from __future__ import annotations

from django.db.models import Q

from apps.agents import services as agent_services
from apps.harness.models import Runner
from apps.workspaces import services as wsvc


def _runner_frame(runner: Runner) -> dict:
    return {
        "id": str(runner.id),
        "name": runner.name,
        "kind": runner.kind,
        "status": runner.live_status,
        "last_heartbeat_at": (
            runner.last_heartbeat_at.isoformat() if runner.last_heartbeat_at else None
        ),
    }


def supervisor_snapshot(user) -> dict:
    wsvc.auto_join_workspaces(user)
    slugs = set(wsvc.user_workspace_slugs(user))

    agents = [
        a
        for a in agent_services.list_agents()
        if a.workspace_id in slugs or a.workspace_id is None
    ]
    waiting = {a.slug: int(agent_services.needs_you(a).get("waiting_count") or 0) for a in agents}

    runners = Runner.objects.exclude(status=Runner.RETIRED).filter(
        (Q(workspace_id__in=slugs) | Q(workspace_id__isnull=True))
        & (Q(paired_by=user) | Q(paired_by__isnull=True))
    )

    return {
        "type": "supervisor.snapshot",
        "runners": [_runner_frame(r) for r in runners],
        "waiting": waiting,
        "total_waiting": sum(waiting.values()),
    }
