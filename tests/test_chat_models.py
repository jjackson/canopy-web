"""SP2a Task 1 — the chat app + Session/Message models."""
from __future__ import annotations

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import IntegrityError

from apps.agents.models import Agent
from apps.chat.models import Message, Session
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


def _ws_user():
    user = User.objects.create_user("jj", "jj@dimagi.com", "pw")
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=user)
    return ws, user


def test_chat_app_installed():
    assert apps.is_installed("apps.chat")


def test_session_and_message_roundtrip():
    ws, user = _ws_user()
    agent = Agent.objects.create(slug="echo", name="Echo", workspace=ws, owner=user)
    session = Session.objects.create(workspace=ws, agent=agent, created_by=user, title="Hello")
    msg = Message.objects.create(
        session=session, turn_index=0, role=Message.USER, plaintext="hi", content={"text": "hi"}
    )
    assert session.messages.count() == 1
    assert msg.role == "user"
    assert session.status == Session.ACTIVE


def test_session_can_be_agentless():
    ws, user = _ws_user()
    session = Session.objects.create(workspace=ws, created_by=user)
    assert session.agent_id is None


def test_message_index_unique_per_session():
    ws, user = _ws_user()
    session = Session.objects.create(workspace=ws, created_by=user)
    Message.objects.create(session=session, turn_index=0, role=Message.USER)
    with pytest.raises(IntegrityError):
        Message.objects.create(session=session, turn_index=0, role=Message.ASSISTANT)
