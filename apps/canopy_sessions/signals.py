"""Project the harness ledger into chat Messages.

Subscribes to harness's turn_events_appended (fired post-commit, after bulk_create,
which emits no post_save) and materializes a session turn's assistant/tool events
into Message rows. Same signal SP1's realtime fan-out rides — chat is just a second,
independent consumer of it.
"""
from __future__ import annotations

from django.dispatch import receiver

from apps.harness.signals import turn_events_appended


@receiver(turn_events_appended, dispatch_uid="chat_project_messages")
def _project_messages(sender, turn, rows, **kwargs):
    if not turn.chat_session_id:
        return
    from .services import project_events

    project_events(turn, rows)
