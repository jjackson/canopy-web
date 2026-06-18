"""E2E seed: a user + an authenticated session + the echo agent with a spread of
tasks and one pending command. Writes the session key to .auth/session.txt for
Playwright to use as a cookie. Run via `manage.py shell -c` from the repo root."""
import datetime as dt
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore

from apps.agents.models import (
    Agent, AgentSkill, AgentSync, AgentTask, AgentTaskCommand, AgentWorkProduct,
)

User = get_user_model()
user, _ = User.objects.get_or_create(username="e2e", defaults={"email": "e2e@dimagi.com"})

a, _ = Agent.objects.update_or_create(slug="echo", defaults=dict(
    name="Echo", email="echo@dimagi-ai.com", description="Marketing agent for Connect.",
    persona="Email-driven marketing agent."))
a.tasks.all().delete()
a.commands.all().delete()


def t(**k):
    return AgentTask.objects.create(agent=a, **k)


t(ext_id="t1", title="ZEGCAWIS polio AFP story", next_action="Get consent to interview the FLW",
  status="suggested", owner="Matt", assigned="Matt", confidence="high",
  rationale="Strong near-miss; timely AFP detection fed national surveillance.",
  source_url="https://example.com/zegcawis", position=0)
t(ext_id="t2", title="Brand-voice loop", next_action="Propose a draft to edits design",
  status="suggested", owner="Amie", assigned="Echo", confidence="low",
  rationale="Learn the house voice from edits.", position=1)
t(ext_id="t3", title="PRIDE cholera story", next_action="Run the interview",
  status="in_progress", owner="Matt", assigned="Sarvesh", position=2)
t(ext_id="t4", title="Ideas backlog upkeep", next_action="Append new ideas",
  status="in_progress", owner="Matt", assigned="Echo", position=3)
t(ext_id="t5", title="Agent workspace shipped", next_action="", status="done",
  owner="Jonathan", assigned="Echo", position=4)
AgentTaskCommand.objects.create(agent=a, task=a.tasks.get(ext_id="t4"), kind="dispatch",
                                status="pending", created_by="jonathan@dimagi.com")

a.syncs.all().delete()
a.work_products.all().delete()
a.skills.all().delete()
AgentSync.objects.create(
    agent=a, period_start=dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc),
    period_end=dt.datetime(2026, 6, 17, tzinfo=dt.timezone.utc), title="Manager sync 1",
    summary="First two weeks.", doc_url="https://docs.google.com/document/d/syncdoc/edit",
    self_grades={"work": "C+", "skills": "B-"}, source="manager-sync")
AgentWorkProduct.objects.create(
    agent=a, title="Demo story RUWOYD", kind="story",
    url="https://docs.google.com/document/d/wp1/edit", description="A 5/5 demo story.",
    tags=["story"], source="story-draft")
AgentSkill.objects.create(
    agent=a, name="email-communicator", description="Send and receive email as Echo.",
    url="https://github.com/dimagi-internal/echo/blob/main/skills/email-communicator/SKILL.md")

session = SessionStore()
session["_auth_user_id"] = str(user.pk)
session["_auth_user_backend"] = settings.AUTHENTICATION_BACKENDS[0]
session["_auth_user_hash"] = user.get_session_auth_hash()
session.set_expiry(24 * 3600)
session.save()

os.makedirs("frontend/e2e/.auth", exist_ok=True)
with open("frontend/e2e/.auth/session.txt", "w") as f:
    f.write(session.session_key)

print(f"seeded: {a.tasks.count()} tasks, {a.commands.filter(status='pending').count()} pending; "
      f"session {session.session_key[:8]}")
