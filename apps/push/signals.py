"""post_save receivers that mark an agent dirty when its waiting set may have
changed. Wiring only — whether to push is services.refresh_agent_waiting's call.

One receiver per producer of the waiting set — which is the shape needs_you() has
today, and the reason this file has a KNOWN GAP below. `Item` (the last receiver)
is the exception and the direction of travel: it is a real row, so it needs no
hops, cannot be Drive-backed, and cannot go stale. As Phases 3-4 move tasks and
run gates onto Item, their receivers collapse into that one and the gap below
stops being expressible. See 2026-07-15-item-and-turn-design.md §5b.

KNOWN GAP, deliberate (applies to the run-derived receivers ONLY, never to Item):
run-derived items reach needs_you() through the RunStore
resolver (apps/agent_runs/resolver.py). DbRunStore is the default and its rows
ARE models, so these receivers see them. An agent listed in
settings.AGENT_RUNS_DRIVE_ROOTS is DriveRunStore-backed — it reads YAML from
Drive, so no signal will ever fire for its gates and its gate-opens will not
push. That map is {} today (its own example is {"ace": ...}), so this covers
everything now. Such an agent's TASK pushes still work — but "work" means a
live Drive API call made synchronously inside on_commit, in the request path:
_task_changed -> mark_dirty -> refresh_agent_waiting -> needs_you() ->
_run_inbox_items() -> the resolver -> DriveRunStore. Inert today since the map
is empty; the day it isn't, every task write on that agent pays a Drive
round-trip on the request thread.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.agent_runs.models import AgentRunGate, AgentRunStep
from apps.agents.models import AgentTask
from apps.harness.models import Item

from .services import mark_dirty

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=AgentTask)
def _task_changed(sender, instance: AgentTask, **kwargs) -> None:
    mark_dirty(instance.agent_id)  # the FK shadow attribute — no query


@receiver([post_save, post_delete], sender=Item)
def _item_changed(sender, instance: Item, **kwargs) -> None:
    """The only receiver here whose source is an OBJECT, not a projection — which
    is why it needs no hops and cannot hit the Drive gap above: an Item is always
    a row. As Phases 3-4 move the other producers onto Item, their receivers
    delete into this one."""
    mark_dirty(instance.agent_id)  # the FK shadow attribute — no query


@receiver([post_save, post_delete], sender=AgentRunGate)
def _gate_changed(sender, instance: AgentRunGate, **kwargs) -> None:
    # TWO hops. A gate hangs off a STEP, not a run:
    #   AgentRunGate.step -> AgentRunStep.run -> AgentRun.agent
    # There is no `gate.run`. (Verified against apps/agent_runs/models.py:165.)
    try:
        mark_dirty(instance.step.run.agent_id)
    except ObjectDoesNotExist:
        # Cascade delete: the step/run is already gone. The count can only be
        # dropping, and we never push on a drop — nothing to do.
        logger.debug("push: gate %s has no reachable run; skipping", instance.pk)


@receiver([post_save, post_delete], sender=AgentRunStep)
def _step_changed(sender, instance: AgentRunStep, **kwargs) -> None:
    try:
        mark_dirty(instance.run.agent_id)
    except ObjectDoesNotExist:
        logger.debug("push: step %s has no reachable run; skipping", instance.pk)
