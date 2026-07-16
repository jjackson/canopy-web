"""The command catalog's phone surface: which skills are human entry points.

The catalog mirrors the repo wholesale, so most of what a mature agent publishes
is not launchable (a pre-send discipline, a superseded skill, a reference doc, a
one-time setup). These tests pin the fail-closed default and the round-trip.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.agents.models import Agent, AgentSkill
from apps.workspaces.models import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="sup@dimagi.com", email="sup@dimagi.com", password="x"
    )


@pytest.fixture
def agent(db, user):
    ws = Workspace.objects.create(slug="canopy", display_name="Canopy", created_by=user)
    WorkspaceMembership.objects.create(
        workspace=ws, user=user, role=WorkspaceMembership.OWNER
    )
    return Agent.objects.create(slug="echo", name="Echo", workspace=ws)


@pytest.fixture
def client_in(client, user):
    client.force_login(user)
    return client


def test_launchable_defaults_false_so_an_unadopted_publish_offers_nothing(client_in, agent):
    """Fail closed. An agent whose publish step predates these fields must not
    have its whole 20-skill catalog show up as phone buttons."""
    resp = client_in.put(
        f"/api/agents/{agent.slug}/skills/",
        data={"skills": [{"name": "setup", "description": "one-time per machine"}]},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content

    skill = AgentSkill.objects.get(agent=agent, name="setup")
    assert skill.launchable is False
    assert skill.args_hint == ""


def test_launchable_and_args_hint_round_trip_through_put_and_get(client_in, agent):
    """The regression that matters: services.replace_skills builds AgentSkill()
    field-by-field, so a new field is silently dropped unless it is added there
    too. A test that only checked the PUT's 200 would pass while the flag was
    thrown away."""
    resp = client_in.put(
        f"/api/agents/{agent.slug}/skills/",
        data={
            "skills": [
                {
                    "name": "story-ideation",
                    "description": "pitch angles",
                    "launchable": True,
                    "args_hint": "topic (optional)",
                },
                {"name": "agent-turn-review", "description": "pre-send discipline"},
            ]
        },
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content

    got = client_in.get(f"/api/agents/{agent.slug}/skills/").json()
    by_name = {s["name"]: s for s in got}

    assert by_name["story-ideation"]["launchable"] is True
    assert by_name["story-ideation"]["args_hint"] == "topic (optional)"
    assert by_name["agent-turn-review"]["launchable"] is False
    assert by_name["agent-turn-review"]["args_hint"] == ""


def test_wholesale_replacement_still_holds(client_in, agent):
    """The PUT contract is full replacement — that is what keeps the catalog from
    drifting from the repo, and is why we extended AgentSkill rather than adding a
    second AgentCommand model. Adding fields must not weaken it."""
    client_in.put(
        f"/api/agents/{agent.slug}/skills/",
        data={"skills": [{"name": "old-skill", "launchable": True}]},
        content_type="application/json",
    )
    client_in.put(
        f"/api/agents/{agent.slug}/skills/",
        data={"skills": [{"name": "new-skill", "launchable": True}]},
        content_type="application/json",
    )

    names = set(AgentSkill.objects.filter(agent=agent).values_list("name", flat=True))
    assert names == {"new-skill"}


def test_relaunching_a_skill_can_flip_launchable_off(client_in, agent):
    """The agent owns its own phone surface: un-marking a skill must actually
    withdraw the button, not leave a stale True behind from the prior publish.

    The mid-way assert is load-bearing. Without it this test passes in a broken
    world where launchable is never written at all (everything is False, so the
    final assert holds vacuously) — which is how it behaved when first written.
    """
    client_in.put(
        f"/api/agents/{agent.slug}/skills/",
        data={"skills": [{"name": "risky", "launchable": True}]},
        content_type="application/json",
    )
    assert AgentSkill.objects.get(agent=agent, name="risky").launchable is True

    client_in.put(
        f"/api/agents/{agent.slug}/skills/",
        data={"skills": [{"name": "risky", "launchable": False}]},
        content_type="application/json",
    )
    assert AgentSkill.objects.get(agent=agent, name="risky").launchable is False
