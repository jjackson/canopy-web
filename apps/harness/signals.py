"""Domain signals emitted by the harness write path.

`turn_events_appended` fires AFTER an append commits (via transaction.on_commit)
so a subscriber (apps/realtime) can fan out durable events without racing the DB.

It exists because `services.append_events` uses bulk_create, which does NOT emit
post_save — a post_save receiver on TurnEvent would silently never fire. Framework
consumers connect to this instead.
"""
from __future__ import annotations

from django.dispatch import Signal

# Sent with: sender=Turn, turn=<Turn>, rows=<list[TurnEvent]> (the newly appended
# rows, in seq order). Fired post-commit.
turn_events_appended = Signal()

# Sent with: sender=Runner, runner=<Runner> after a runner's session report commits.
# apps/realtime fans the runner-owner's visible sessions to their supervisor group so
# the phone reflects live emdash activity instantly (one broadcast, N viewers) instead
# of every client polling. Post-commit, same reasoning as turn_events_appended.
sessions_reported = Signal()
