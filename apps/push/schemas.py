"""Pydantic schemas for /api/push."""
from __future__ import annotations

from apps.common.schemas import StrictModel


class VapidKeyOut(StrictModel):
    public_key: str


class PushSubscribeIn(StrictModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str = ""


class PushUnsubscribeIn(StrictModel):
    endpoint: str
