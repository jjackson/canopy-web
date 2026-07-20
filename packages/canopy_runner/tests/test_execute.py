"""CDP executor — resolve → reuse-or-create, runner owns the routing lifecycle."""
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from canopy_runner import cdp_control, emdash, execute


def _cfg():
    # A real (but throwaway) state_path — execute_turn's fail/finish paths now write a
    # readiness marker next to it (see readiness.py); without one, readiness would fall
    # back to the real ~/.canopy and pollute the developer's machine during a test run.
    # Fresh tmp dir per call keeps every test's marker isolated from the others.
    tmp = Path(tempfile.mkdtemp(prefix="canopy-runner-test-"))
    return SimpleNamespace(cdp_port=9222, runner_id="r-1", emdash_db="/fake/emdash4.db",
                           state_path=str(tmp / "runner-state.json"))


@pytest.fixture(autouse=True)
def _db_says_live(monkeypatch):
    """Default: sqlite reports the linked task present. Tests that care override it."""
    monkeypatch.setattr(emdash, "task_state", lambda db, name: "live")


class FakeClient:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []          # method log
        self.events = []
        self.started = []
        self.finished = []
        self.failed = []
        self.recorded = []

    def resolve_session(self, runner_id, agent, thread_key, *, project="", workspace=""):
        self.calls.append(("resolve", agent, thread_key, project, workspace))
        return dict(self.plan)

    def start(self, turn_id, session_id=""):
        self.started.append(turn_id)

    def finish(self, turn_id, note=""):
        self.finished.append((turn_id, note))

    def fail_turn(self, turn_id, note):
        self.failed.append((turn_id, note))

    def post_events(self, turn_id, events):
        self.events.append((turn_id, events))

    def record_session(self, runner_id, agent, thread_key, **kw):
        self.recorded.append((agent, thread_key, kw))



def _turn(**kw):
    d = {"id": "t-1", "agent_slug": "hal", "origin_ref": {}, "prompt": "do the thing"}
    d.update(kw)
    return d


def test_reuse_sends_into_existing_session(monkeypatch):
    sent = {}
    monkeypatch.setattr(cdp_control, "open_and_send",
                        lambda task, text, port=9222: sent.update(task=task, text=text) or {"ok": True})
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda *a, **k: pytest.fail("must NOT create when reusing"))
    client = FakeClient({"reuse": True, "emdash_task_id": "shaky-baths-listen", "summary": ""})
    turn = _turn(origin_ref={"thread_id": "thr-1"})
    result = execute.execute_turn(_cfg(), client, "r-1", turn)
    assert result == "reused:t-1"
    assert sent == {"task": "shaky-baths-listen", "text": "do the thing"}
    assert client.started == ["t-1"] and client.finished and "existing session" in client.finished[0][1]


@pytest.mark.parametrize("state", ["archived", "absent"])
def test_db_says_gone_creates_fresh_without_asking_the_dom(monkeypatch, state):
    """sqlite is the truth for existence. A genuinely-gone task creates + rehydrates —
    and never pays for a CDP round trip to learn what one query already answered."""
    monkeypatch.setattr(emdash, "task_state", lambda db, name: state)
    monkeypatch.setattr(cdp_control, "open_and_send",
                        lambda *a, **k: pytest.fail("must not touch the DOM once sqlite says gone"))
    created = {}
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda project, prompt, task_name="", port=9222: created.update(project=project, prompt=prompt) or {"task": "new-task-x"})
    client = FakeClient({"reuse": True, "emdash_task_id": "gone-one", "summary": "prior ctx"})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={"thread_id": "thr-1"}))
    assert result.startswith("created:t-1:new-task-x")
    assert created["project"] == "hal"
    assert "prior ctx" in created["prompt"]      # rehydrated on fallback


def test_dom_not_found_never_duplicates_a_task_sqlite_says_is_live(monkeypatch):
    """THE eva org-research bug (2026-07-15). The sidebar virtualizes, so a live task
    scrolled out of view reports TASK_NOT_FOUND. Trusting that spawned a cold duplicate
    and orphaned the real session's context. sqlite outranks the DOM: fail, don't fork."""
    def not_found(task, text, port=9222):
        raise cdp_control.CDPError('TASK_NOT_FOUND: no task "eva-org-research-790c-0715-1352"')
    monkeypatch.setattr(cdp_control, "open_and_send", not_found)
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda *a, **k: pytest.fail("must NOT duplicate a live session"))
    client = FakeClient({"reuse": True, "emdash_task_id": "eva-org-research-790c-0715-1352",
                         "summary": "ctx"})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={"thread_id": "thr-1"}))
    assert result == "failed:t-1"
    assert client.recorded == []      # link still points at the original session


def test_unreadable_db_degrades_to_the_dom_verdict(monkeypatch):
    """No truth available (db missing/misconfigured) — don't wedge every turn; fall back
    to the legacy CDP verdict, which is no worse than the pre-sqlite behaviour."""
    monkeypatch.setattr(emdash, "task_state", lambda db, name: "unknown")
    def not_found(task, text, port=9222):
        raise cdp_control.CDPError('TASK_NOT_FOUND: no task "x"')
    monkeypatch.setattr(cdp_control, "open_and_send", not_found)
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda project, prompt, task_name="", port=9222: {"task": "new-x"})
    client = FakeClient({"reuse": True, "emdash_task_id": "x", "summary": ""})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={"thread_id": "thr-1"}))
    assert result.startswith("created:t-1:new-x")


def test_transient_reuse_send_failure_never_duplicates(monkeypatch):
    """The bug that spawned two Hal sessions: a send glitch on an EXISTING task must
    fail the turn, NOT create a duplicate + re-point the link."""
    def glitch(task, text, port=9222):
        raise cdp_control.CDPError("locator.click: Timeout 30000ms exceeded")  # not TASK_NOT_FOUND
    monkeypatch.setattr(cdp_control, "open_and_send", glitch)
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda *a, **k: pytest.fail("must NOT create a duplicate on a transient send failure"))
    client = FakeClient({"reuse": True, "emdash_task_id": "live-session", "summary": "ctx"})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={"thread_id": "thr-1"}))
    assert result == "failed:t-1"
    assert client.failed and "not spawning a duplicate" in client.failed[0][1]
    assert client.recorded == []   # link NOT re-pointed — the original session stays canonical


def test_create_new_thread_rehydrates_from_summary(monkeypatch):
    created = {}
    monkeypatch.setattr(cdp_control, "create_task",
                        lambda project, prompt, task_name="", port=9222: created.update(prompt=prompt) or {"task": "fresh"})
    # other-account plan: reuse False but summary present
    client = FakeClient({"reuse": False, "new_thread": False, "emdash_task_id": "etask-A",
                         "summary": "what account A did"})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={"thread_id": "thr-1"}))
    assert result.startswith("created:t-1:fresh")
    assert "what account A did" in created["prompt"]
    assert client.recorded and client.recorded[0][0] == "hal"


def test_create_failure_fails_the_turn(monkeypatch):
    def boom(project, prompt, task_name="", port=9222):
        raise cdp_control.CDPError("emdash not on debug port")
    monkeypatch.setattr(cdp_control, "create_task", boom)
    client = FakeClient({"reuse": False, "new_thread": True, "summary": ""})
    result = execute.execute_turn(_cfg(), client, "r-1", _turn())
    assert result == "failed:t-1"
    assert client.failed and "emdash create failed" in client.failed[0][1]


def test_thread_key_defaults_to_agent_main_when_no_ref(monkeypatch):
    monkeypatch.setattr(cdp_control, "create_task", lambda *a, **k: {"task": "x"})
    client = FakeClient({"reuse": False, "new_thread": True, "summary": ""})
    execute.execute_turn(_cfg(), client, "r-1", _turn(origin_ref={}))
    assert client.calls[0] == ("resolve", "hal", "hal:main", "", "")


def test_a_project_turn_drives_the_repo_and_carries_its_tenant(monkeypatch):
    """A repo turn (agent_slug None, project set) resolves + drives against the
    project name, and threads project + workspace to the session-link calls so
    the durable link is tenant-scoped. cdp_control is unchanged — it always took
    a project name."""
    created = {}
    monkeypatch.setattr(
        cdp_control, "create_task",
        lambda project, prompt, **k: created.update(project=project, prompt=prompt) or {"task": "ct"},
    )
    client = FakeClient({"reuse": False, "new_thread": True, "summary": ""})
    turn = {
        "id": "t-9", "agent_slug": None, "project": "canopy-web",
        "workspace_slug": "canopy", "origin_ref": {}, "prompt": "fix the header",
    }

    result = execute.execute_turn(_cfg(), client, "r-1", turn)

    assert result == "created:t-9:ct"
    # resolve keyed on the repo, tagged with project + workspace
    assert client.calls[0] == ("resolve", "", "canopy-web:main", "canopy-web", "canopy")
    # the CDP create drove the repo as its emdash project, with the composer's prompt
    assert created == {"project": "canopy-web", "prompt": "fix the header"}
    # the durable link was recorded with the repo's tenant
    agent_arg, thread_key, kw = client.recorded[0]
    assert agent_arg == ""
    assert kw["project"] == "canopy-web" and kw["workspace"] == "canopy"


def test_task_name_is_readable_subject_plus_stamp():
    import datetime as dt
    now = dt.datetime(2026, 7, 14, 15, 32)
    t = _turn(origin="email", origin_ref={"subject": "Re: Bednet demo!!"})
    assert execute._task_name("hal", t, now=now) == "hal-re-bednet-demo-main-0714-1532"
    # no subject -> agent + stamp
    assert execute._task_name("hal", _turn(origin="manual", origin_ref={}), now=now) == "hal-manual-main-0714-1532"


def test_task_name_distinguishes_threads_with_same_subject():
    """The observed bug: two DIFFERENT threads with the same subject in the same minute
    got the same name. The thread discriminator must keep them distinct."""
    import datetime as dt
    now = dt.datetime(2026, 7, 14, 15, 14)
    t1 = _turn(origin="email", origin_ref={"subject": "Security alert", "thread_id": "19f4c06eeb986355"})
    t2 = _turn(origin="email", origin_ref={"subject": "Security alert", "thread_id": "19f425675a9855a4"})
    n1 = execute._task_name("hal", t1, now=now)
    n2 = execute._task_name("hal", t2, now=now)
    assert n1 == "hal-security-alert-6355-0714-1514"
    assert n2 == "hal-security-alert-55a4-0714-1514"
    assert n1 != n2
