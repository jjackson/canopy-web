"""Django-free cron slot math for scheduled agent turns.

One implementation, two consumers: the server previews fire times (`next_slots`)
so a hand-typed cron is trustworthy, and the runner decides what is due
(`due_slot`) so it can fire it. Both share the validators.
"""
from __future__ import annotations

from canopy_cron.slots import (
    due_slot,
    next_slots,
    slots_between,
    validate_cron,
    validate_timezone,
)

__all__ = [
    "due_slot",
    "next_slots",
    "slots_between",
    "validate_cron",
    "validate_timezone",
]
