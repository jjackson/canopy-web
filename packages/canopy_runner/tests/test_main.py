import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest

from canopy_runner import emdash
from canopy_runner import main as main_mod
from canopy_runner.client import ClientError
from canopy_runner.config import Config
from canopy_runner.main import GRACE_SECONDS, _fire_due_schedules, run_once

AUTOMATION_ID = "auto-1"


@pytest.fixture()
def db(tmp_path: Path) -> str:
    path = tmp_path / "emdash4.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE __drizzle_migrations (id INTEGER PRIMARY KEY, hash TEXT, created_at INTEGER);
        INSERT INTO __drizzle_migrations (id, hash, created_at) VALUES (19, 'h', 0);
        CREATE TABLE automations (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, task_config TEXT, project_id TEXT,
          enabled INTEGER DEFAULT 1 NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          trigger_config TEXT, conversation_config TEXT, deleted_at INTEGER
        );
        CREATE TABLE automation_runs (
          id TEXT PRIMARY KEY, automation_id TEXT NOT NULL, scheduled_at INTEGER, deadline_at INTEGER,
          started_at INTEGER, task_created_at INTEGER, launched_at INTEGER, finished_at INTEGER,
          status TEXT NOT NULL, error TEXT, trigger_kind TEXT NOT NULL,
          trigger_config_snapshot TEXT DEFAULT '{}' NOT NULL,
          conversation_config_snapshot TEXT DEFAULT '{}' NOT NULL,
          task_config_snapshot TEXT, generated_task_name TEXT
        );
        CREATE TABLE tasks (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
          type TEXT DEFAULT 'task' NOT NULL, automation_run_id TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO automations (id, name, task_config, project_id, enabled, created_at, updated_at, conversation_config) "
        "VALUES (?, 'canopy-turns', ?, 'proj-1', 1, 0, 0, ?)",
        (
            AUTOMATION_ID,
            json.dumps({"version": "1", "taskConfig": {"version": "1", "name": "t"}, "workspaceConfig": {}}),
            json.dumps({"prompt": "/canopy:drain-turn echo", "provider": "claude", "autoApprove": False, "type": "pty"}),
        ),
    )
    conn.commit()
    conn.close()
    return str(path)


class FakeClient:
    def __init__(self, turns=None):
        self.turns = list(turns or [])
        self.events = []
        self.heartbeats = []
        self.failed = []
        self.turn_lookup = {}

    def heartbeat(self, runner_id, active_turn_ids, degraded=False, note=""):
        self.heartbeats.append((runner_id, list(active_turn_ids), degraded, note))
        return {"status": "degraded" if degraded else "online"}

    def claim(self, runner_id):
        return self.turns.pop(0) if self.turns else None

    def post_events(self, turn_id, events):
        self.events.append((turn_id, events))

    def fail_turn(self, turn_id, note):
        self.failed.append((turn_id, note))

    def get_turn(self, turn_id):
        return self.turn_lookup.get(turn_id, {"id": turn_id, "status": "running"})


def _cfg(db, tmp_path):
    # These tests exercise the legacy DB-injection executor explicitly.
    return Config(
        base_url="http://x", token="t", runner_id="r-1", emdash_db=db,
        automation_ids={"echo": AUTOMATION_ID}, expected_migration_id=19,
        state_path=str(tmp_path / "state.json"), executor="inject",
    )


def test_idle_when_no_work(db, tmp_path):
    client = FakeClient()
    assert run_once(_cfg(db, tmp_path), client) == "idle"
    assert client.heartbeats  # heartbeat always sent


def test_claim_injects_run_and_reports_events(db, tmp_path):
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    result = run_once(_cfg(db, tmp_path), client)
    assert result == "injected:t-1"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0] == 1
    kinds = [e["kind"] for _, evs in client.events for e in evs]
    assert "status" in kinds  # injected event posted
    # state file records the active turn for crash-safe rehydration
    state = json.loads(Path(_cfg(db, tmp_path).state_path).read_text())
    assert "t-1" in state["active"]


def test_unknown_agent_fails_turn(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-2", "agent_slug": "eva", "status": "claimed"}])
    result = run_once(cfg, client)
    assert result == "failed:t-2"
    assert client.failed and client.failed[0][0] == "t-2"
    # no lease-renewing state entry may be left behind for the failed turn
    if Path(cfg.state_path).exists():
        state = json.loads(Path(cfg.state_path).read_text())
        assert "t-2" not in state["active"]


def test_schema_drift_goes_degraded_and_never_writes(db, tmp_path):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO __drizzle_migrations (id, hash, created_at) VALUES (20, 'x', 0)")
    conn.commit(); conn.close()
    client = FakeClient(turns=[{"id": "t-3", "agent_slug": "echo", "status": "claimed"}])
    result = run_once(_cfg(db, tmp_path), client)
    assert result == "degraded"
    assert client.heartbeats[-1][2] is True  # degraded flag
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0] == 0


def test_promotes_task_on_followup_pass(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    run_once(cfg, client)  # inject
    # emdash_run_id is deterministic (== turn_id) now, so no need to look it
    # up from the saved state to find the automation_runs row it created.
    run_id = "t-1"
    state = json.loads(Path(cfg.state_path).read_text())
    assert state["active"]["t-1"]["emdash_run_id"] == run_id
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tasks (id, project_id, name, status, type, automation_run_id) "
        "VALUES ('task-1', 'proj-1', 'fruity', 'in_progress', 'automation-run', ?)", (run_id,)
    )
    conn.commit(); conn.close()
    result = run_once(cfg, client)  # follow-up pass sees the task
    assert result == "promoted:task-1"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT type FROM tasks WHERE id='task-1'").fetchone()[0] == "task"


def test_corrupt_state_file_self_heals(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    Path(cfg.state_path).write_text("{not valid json at all")
    # give it a turn to claim so the recovered state actually gets persisted
    # back to disk (an idle iteration with no work never calls _save_state).
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    result = run_once(cfg, client)
    assert result == "injected:t-1"  # loop continues sanely instead of crash-looping
    corrupt_path = Path(cfg.state_path + ".corrupt")
    assert corrupt_path.exists()
    assert corrupt_path.read_text() == "{not valid json at all"
    # a fresh, valid state file was written in its place, recovered from the
    # empty {"active": {}} default plus this iteration's claim
    state = json.loads(Path(cfg.state_path).read_text())
    assert "t-1" in state["active"]


def test_corrupt_state_file_missing_active_key_self_heals(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    Path(cfg.state_path).write_text(json.dumps({"foo": "bar"}))
    client = FakeClient()
    result = run_once(cfg, client)
    assert result == "idle"
    assert Path(cfg.state_path + ".corrupt").exists()


def test_crash_between_save_and_inject_recovers(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    turn_id = "t-crash-1"
    # hand-write a state file as if run_once crashed right after the first
    # _save_state call (injected=False) but before inject_run committed —
    # no automation_runs row exists yet for this turn.
    Path(cfg.state_path).write_text(json.dumps({
        "active": {
            turn_id: {
                "emdash_run_id": turn_id,
                "agent": "echo",
                "task_promoted": False,
                "injected": False,
            }
        }
    }))
    client = FakeClient()
    result = run_once(cfg, client)
    assert result == f"reinjected:{turn_id}"
    # the emdash row now exists (inject_run was called, idempotently)
    assert emdash.run_status(db, turn_id) == "queued"
    state = json.loads(Path(cfg.state_path).read_text())
    assert state["active"][turn_id]["injected"] is True


def test_crash_after_inject_before_flag_flip_recovers(db, tmp_path):
    """Row exists (inject_run committed) but injected flag never got saved
    True — the reinjection check treats a present row + injected=False the
    same as a missing row: reinject (idempotent no-op) and flip the flag."""
    cfg = _cfg(db, tmp_path)
    turn_id = "t-crash-2"
    emdash.inject_run(db, AUTOMATION_ID, turn_id, task_name="canopy-turn-echo")
    Path(cfg.state_path).write_text(json.dumps({
        "active": {
            turn_id: {
                "emdash_run_id": turn_id,
                "agent": "echo",
                "task_promoted": False,
                "injected": False,
            }
        }
    }))
    client = FakeClient()
    result = run_once(cfg, client)
    assert result == f"reinjected:{turn_id}"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0] == 1  # still just one row
    state = json.loads(Path(cfg.state_path).read_text())
    assert state["active"][turn_id]["injected"] is True


def test_disabled_automation_fails_turn_and_evicts(db, tmp_path):
    """A permanently-broken entry (automation disabled) must be failed and
    evicted — NOT retried forever while the heartbeat renews its lease."""
    cfg = _cfg(db, tmp_path)
    turn_id = "t-wedge-1"
    # claim-time state exists (as if we crashed pre-inject), then the
    # automation gets disabled out from under us
    Path(cfg.state_path).write_text(json.dumps({
        "active": {
            turn_id: {
                "emdash_run_id": turn_id,
                "agent": "echo",
                "task_promoted": False,
                "injected": False,
            }
        }
    }))
    conn = sqlite3.connect(db)
    conn.execute("UPDATE automations SET enabled=0 WHERE id=?", (AUTOMATION_ID,))
    conn.commit(); conn.close()
    client = FakeClient()
    result = run_once(cfg, client)
    assert result == f"failed:{turn_id}"
    assert client.failed and client.failed[0][0] == turn_id
    assert "disabled" in client.failed[0][1]
    state = json.loads(Path(cfg.state_path).read_text())
    assert turn_id not in state["active"]  # evicted — lease can now expire
    # next iteration is clean, not wedged
    assert run_once(cfg, client) == "idle"


def test_disabled_automation_at_claim_time_fails_and_evicts(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE automations SET enabled=0 WHERE id=?", (AUTOMATION_ID,))
    conn.commit(); conn.close()
    client = FakeClient(turns=[{"id": "t-wedge-2", "agent_slug": "echo", "status": "claimed"}])
    result = run_once(cfg, client)
    assert result == "failed:t-wedge-2"
    assert client.failed and client.failed[0][0] == "t-wedge-2"
    state = json.loads(Path(cfg.state_path).read_text())
    assert "t-wedge-2" not in state["active"]


def test_reinjection_skipped_when_task_promoted(db, tmp_path):
    """emdash pruning a finished run's row must not re-execute the turn."""
    cfg = _cfg(db, tmp_path)
    turn_id = "t-done-1"
    # injected + promoted, but the automation_runs row is gone (pruned)
    Path(cfg.state_path).write_text(json.dumps({
        "active": {
            turn_id: {
                "emdash_run_id": turn_id,
                "agent": "echo",
                "task_promoted": True,
                "injected": True,
            }
        }
    }))
    client = FakeClient()
    result = run_once(cfg, client)
    assert result == "idle"  # nothing-to-do, NOT reinjected
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM automation_runs").fetchone()[0] == 0


def test_non_dict_active_quarantines(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    Path(cfg.state_path).write_text(json.dumps({"active": None}))
    client = FakeClient()
    result = run_once(cfg, client)
    assert result == "idle"
    assert Path(cfg.state_path + ".corrupt").exists()


def test_state_write_is_atomic(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    run_once(cfg, client)
    assert not Path(cfg.state_path + ".tmp").exists()
    state = json.loads(Path(cfg.state_path).read_text())  # parses cleanly
    assert "t-1" in state["active"]


def test_evicts_turn_finished_serverside(db, tmp_path):
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    client.turn_lookup = {"t-1": {"id": "t-1", "status": "done"}}
    run_once(cfg, client)  # inject
    result = run_once(cfg, client)  # follow-up sees server-side done
    assert result == "evicted:t-1"
    state = json.loads(Path(cfg.state_path).read_text())
    assert state["active"] == {}


def test_completed_run_within_grace_is_left_alone(db, tmp_path):
    """emdash run reached 'done' but the server turn is still claimed/running
    (skill never POSTed /finish yet) — within the grace window this must be
    left alone, not failed+evicted."""
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    client.turn_lookup = {"t-1": {"id": "t-1", "status": "running"}}
    run_once(cfg, client)  # inject
    conn = sqlite3.connect(db)
    conn.execute("UPDATE automation_runs SET status='done' WHERE id='t-1'")
    conn.commit(); conn.close()

    run_once(cfg, client)  # first observation of 'done' — records completed_seen_at
    state = json.loads(Path(cfg.state_path).read_text())
    assert "completed_seen_at" in state["active"]["t-1"]

    result = run_once(cfg, client)  # still well within GRACE_SECONDS
    assert result != "failed:t-1"
    assert not client.failed
    state = json.loads(Path(cfg.state_path).read_text())
    assert "t-1" in state["active"]


def test_completed_run_with_unfinished_turn_fails_after_grace(db, tmp_path, monkeypatch):
    """If the grace window expires with the turn still unclosed server-side,
    the entry must be failed+evicted so it stops wedging the agent's lane."""
    cfg = _cfg(db, tmp_path)
    client = FakeClient(turns=[{"id": "t-1", "agent_slug": "echo", "status": "claimed"}])
    client.turn_lookup = {"t-1": {"id": "t-1", "status": "running"}}
    run_once(cfg, client)  # inject
    conn = sqlite3.connect(db)
    conn.execute("UPDATE automation_runs SET status='done' WHERE id='t-1'")
    conn.commit(); conn.close()

    run_once(cfg, client)  # first observation — records completed_seen_at
    state = json.loads(Path(cfg.state_path).read_text())
    completed_seen_at = state["active"]["t-1"]["completed_seen_at"]

    # Jump time forward past the grace window between the two run_once calls.
    monkeypatch.setattr(time, "time", lambda: completed_seen_at + GRACE_SECONDS + 1)
    result = run_once(cfg, client)
    assert result == "failed:t-1"
    assert client.failed and client.failed[-1][0] == "t-1"
    assert "grace expired" in client.failed[-1][1]
    state = json.loads(Path(cfg.state_path).read_text())
    assert "t-1" not in state["active"]  # evicted — lease can now expire


# --- scheduled turns: the loop wiring (the decision logic is tests/test_schedules.py) ---


def test_schedule_sync_failure_never_kills_the_loop(tmp_path):
    """The daemon runs unattended under launchd: an unhandled exception in the
    scheduling path would take down claiming and the inbox with it."""
    class Boom:
        def sync_schedules(self, runner_id):
            raise ClientError("500 from server")

    cfg = Config(base_url="http://x", token="t", runner_id="r-1", emdash_db="x",
                 automation_ids={}, expected_migration_id=19,
                 state_path=str(tmp_path / "state.json"))
    _fire_due_schedules(cfg, Boom())  # must not raise


def test_global_pause_sentinel_blocks_schedule_firing(tmp_path, monkeypatch):
    """Paused = no work, no tokens. Firing while paused would queue scheduled turns
    that all execute the instant the runner resumes."""
    cfg_path = tmp_path / "runner.json"
    cfg_path.write_text(json.dumps({
        "base_url": "http://x", "token": "t", "runner_id": "r-1",
        "emdash_db": str(tmp_path / "e.db"), "automation_ids": {},
        "expected_migration_id": 19, "poll_seconds": 1,
    }))
    (tmp_path / "PAUSED").touch()  # the sentinel main() watches, next to the config

    calls = []

    class RecordingClient:
        def __init__(self, base_url, token):
            pass

        def heartbeat(self, *a, **k):
            calls.append("heartbeat")
            return {}

        def sync_schedules(self, runner_id):
            calls.append("sync_schedules")
            return []

        def claim(self, *a, **k):
            calls.append("claim")
            return None

    class StopLoopError(Exception):
        pass

    def stop(_seconds):
        raise StopLoopError

    monkeypatch.setattr(main_mod, "Client", RecordingClient)
    monkeypatch.setattr(time, "sleep", stop)
    monkeypatch.setattr(sys, "argv", ["canopy-runner", "run", "--config", str(cfg_path)])

    with pytest.raises(StopLoopError):
        main_mod.main()

    assert "heartbeat" in calls  # still alive-but-idle to the control plane
    assert "sync_schedules" not in calls  # ...but fired nothing
    assert "claim" not in calls


def test_unpaused_loop_fires_schedules_every_poll(tmp_path, monkeypatch):
    """The counterpart to the pause test: prove the firing is actually wired into
    the poll (the pause assertion alone would pass if it were wired nowhere)."""
    cfg_path = tmp_path / "runner.json"
    cfg_path.write_text(json.dumps({
        "base_url": "http://x", "token": "t", "runner_id": "r-1",
        "emdash_db": str(tmp_path / "e.db"), "automation_ids": {},
        "expected_migration_id": 19, "poll_seconds": 1,
    }))
    calls = []

    class RecordingClient:
        def __init__(self, base_url, token):
            pass

        def heartbeat(self, *a, **k):
            return {}

        def sync_schedules(self, runner_id):
            calls.append(runner_id)
            return []

        def claim(self, *a, **k):
            return None

    class StopLoopError(Exception):
        pass

    monkeypatch.setattr(main_mod, "Client", RecordingClient)
    monkeypatch.setattr(time, "sleep", lambda _s: (_ for _ in ()).throw(StopLoopError()))
    monkeypatch.setattr(sys, "argv", ["canopy-runner", "run", "--config", str(cfg_path)])

    with pytest.raises(StopLoopError):
        main_mod.main()

    assert calls == ["r-1"]  # synced on the poll — the poll IS the tick


# --------------------------------------------------------------------------------------
# drain_one — the "take a single turn" primitive (CDP executor)
# --------------------------------------------------------------------------------------

def _cdp_cfg(tmp_path):
    return Config(
        base_url="http://x", token="t", runner_id="r-1",
        emdash_db=str(tmp_path / "e.db"), automation_ids={},
        expected_migration_id=19,  # executor defaults to "cdp"
    )


class _CdpClient:
    def __init__(self, turn):
        self._turn = turn
        self.beats = 0
        self.claims = 0

    def heartbeat(self, runner_id, active, host="", **kw):
        self.beats += 1

    def claim(self, runner_id, paused_agents=None):
        self.claims += 1
        return self._turn


def test_drain_one_runs_exactly_one_turn_without_polling(monkeypatch, tmp_path):
    """The single-turn primitive: heartbeat → claim ONE → execute, and NEVER poll the
    inbox or fire schedules — those side effects are exactly what --once has and
    --drain-one deliberately avoids, so a single turn can't spawn work you didn't ask for."""
    monkeypatch.setattr("canopy_runner.cdp_control.cdp_healthy", lambda **k: True)
    monkeypatch.setattr("canopy_runner.cdp_control.host_id", lambda: "u@h")
    monkeypatch.setattr(main_mod, "_paused_agents", lambda c: set())
    monkeypatch.setattr(main_mod, "_maybe_check_inboxes",
                        lambda *a, **k: pytest.fail("drain_one must NOT poll the inbox"))
    monkeypatch.setattr(main_mod, "_fire_due_schedules",
                        lambda *a, **k: pytest.fail("drain_one must NOT fire schedules"))
    seen = {}
    monkeypatch.setattr("canopy_runner.execute.execute_turn",
                        lambda cfg, client, rid, turn: seen.update(turn=turn) or f"reused:{turn['id']}")

    client = _CdpClient({"id": "t-9", "agent_slug": "eva"})
    assert main_mod.drain_one(_cdp_cfg(tmp_path), client) == "reused:t-9"
    assert seen["turn"]["id"] == "t-9"
    assert client.beats == 1 and client.claims == 1


def test_drain_one_idle_when_nothing_queued(monkeypatch, tmp_path):
    monkeypatch.setattr("canopy_runner.cdp_control.cdp_healthy", lambda **k: True)
    monkeypatch.setattr("canopy_runner.cdp_control.host_id", lambda: "u@h")
    monkeypatch.setattr(main_mod, "_paused_agents", lambda c: set())
    monkeypatch.setattr("canopy_runner.execute.execute_turn",
                        lambda *a, **k: pytest.fail("nothing queued — must not execute"))
    assert main_mod.drain_one(_cdp_cfg(tmp_path), _CdpClient(None)) == "idle"


def test_drain_one_honours_per_agent_pause_via_claim(monkeypatch, tmp_path):
    """Per-agent pauses ARE respected — the paused set is passed to claim, which the
    server uses to exclude that agent's turns."""
    monkeypatch.setattr("canopy_runner.cdp_control.cdp_healthy", lambda **k: True)
    monkeypatch.setattr("canopy_runner.cdp_control.host_id", lambda: "u@h")
    monkeypatch.setattr(main_mod, "_paused_agents", lambda c: {"eva"})
    passed = {}

    class C(_CdpClient):
        def claim(self, runner_id, paused_agents=None):
            passed["paused"] = paused_agents
            return None

    main_mod.drain_one(_cdp_cfg(tmp_path), C(None))
    assert passed["paused"] == ["eva"]


def test_drain_one_refuses_to_claim_when_cdp_down(monkeypatch, tmp_path):
    """The self-heal reaches the single-turn primitive too: claiming with emdash down
    would immediately fail (burn) the turn, so drain_one refuses instead. It must ALSO
    report ready=False on this heartbeat — otherwise the server keeps showing the runner
    as "ready" while it can't actually execute anything (the primary proactive case this
    feature exists to surface)."""
    monkeypatch.setattr("canopy_runner.cdp_control.cdp_healthy", lambda **k: False)
    monkeypatch.setattr("canopy_runner.cdp_control.host_id", lambda: "u@h")
    monkeypatch.setattr(main_mod, "_paused_agents", lambda c: set())

    class C(_CdpClient):
        def __init__(self):
            super().__init__(None)
            self.degraded = None
            self.ready = None
            self.ready_note = None

        def heartbeat(self, runner_id, active, degraded=False, note="", host="",
                      ready=True, ready_note=""):
            self.beats += 1
            self.degraded = degraded
            self.ready = ready
            self.ready_note = ready_note

        def claim(self, runner_id, paused_agents=None):
            pytest.fail("must NOT claim a turn while CDP is down")

    c = C()
    assert main_mod.drain_one(_cdp_cfg(tmp_path), c) == "cdp_down"
    assert c.degraded is True  # surfaced as degraded to the control plane
    assert c.ready is False  # must NOT default to True while CDP is unreachable
    assert c.ready_note  # a human-readable reason accompanies it


def test_broken_scheduling_does_not_crash_the_tick(db, tmp_path, monkeypatch, caplog):
    """A scheduling dependency failure — e.g. canopy_cron not installed in the
    laptop daemon's env — must disable ONLY scheduling. Claiming and the inbox
    keep running. The `from . import schedules` lives INSIDE _fire_due_schedules'
    guard for exactly this reason: the import is the likeliest failure, and it
    must not escape and take down the whole run_once cycle.

    Regression for the outage where a missing canopy_cron crash-looped the runner
    (no claim, no inbox) instead of gracefully skipping scheduling.
    """
    import sys

    # Make `from . import schedules` raise ImportError, exactly as a missing
    # canopy_cron did (schedules.py imports canopy_cron at module top, so its
    # own import fails). setitem(..., None) is Python's "this import is halted".
    monkeypatch.setitem(sys.modules, "canopy_runner.schedules", None)
    caplog.set_level("WARNING")

    # Must NOT raise — before the fix this propagated out of run_once.
    _fire_due_schedules(_cfg(db, tmp_path), FakeClient(), paused=set())

    assert "scheduling unavailable" in caplog.text.lower()


# --------------------------------------------------------------------------------------
# CDP preflight — don't claim (and burn) a turn when emdash's CDP is unreachable
# --------------------------------------------------------------------------------------


class _CdpLoopClient:
    """A CDP-path fake: records heartbeats (degraded flag) and how many times claim ran."""

    def __init__(self, turns=None):
        self.turns = list(turns or [])
        self.claims = 0
        self.heartbeats = []

    def heartbeat(self, runner_id, active, degraded=False, note="", host="",
                  ready=True, ready_note=""):
        self.heartbeats.append({"degraded": degraded, "note": note,
                                "ready": ready, "ready_note": ready_note})

    def report_sessions(self, runner_id, sessions):
        pass

    def sync_schedules(self, runner_id):
        return []

    def claim(self, runner_id, paused_agents=None):
        self.claims += 1
        return self.turns.pop(0) if self.turns else None


def _cdp_loop_cfg(tmp_path):
    # executor defaults to "cdp"; no mailboxes so the inbox poll is a no-op.
    return Config(
        base_url="http://x", token="t", runner_id="r-1",
        emdash_db=str(tmp_path / "e.db"), automation_ids={}, expected_migration_id=19,
    )


@pytest.fixture(autouse=True)
def _reset_cdp_throttle():
    """The CDP-down throttle is module-level (one WARNING per outage over the loop's
    lifetime) — reset it around every test so ordering can't leak signalled state."""
    main_mod._reset_cdp_health_state()
    yield
    main_mod._reset_cdp_health_state()


def _stub_cdp(monkeypatch, healthy):
    monkeypatch.setattr("canopy_runner.cdp_control.cdp_healthy", lambda **k: healthy)
    monkeypatch.setattr("canopy_runner.cdp_control.host_id", lambda: "u@h")
    monkeypatch.setattr(main_mod.emdash, "list_open_sessions", lambda db: [])


def test_cdp_healthy_claims_and_executes(monkeypatch, tmp_path):
    _stub_cdp(monkeypatch, healthy=True)
    monkeypatch.setattr("canopy_runner.execute.execute_turn",
                        lambda cfg, client, rid, turn: f"created:{turn['id']}:task")
    client = _CdpLoopClient(turns=[{"id": "t-1", "agent_slug": "eva"}])
    assert run_once(_cdp_loop_cfg(tmp_path), client) == "created:t-1:task"
    assert client.claims == 1
    assert client.heartbeats[-1]["degraded"] is False  # healthy heartbeat


def test_cdp_unhealthy_skips_claim_and_burns_nothing(monkeypatch, tmp_path):
    """The core acceptance criterion: with emdash down a tick claims ZERO turns and
    produces ZERO failed turns — queued turns stay queued."""
    _stub_cdp(monkeypatch, healthy=False)
    monkeypatch.setattr("canopy_runner.execute.execute_turn",
                        lambda *a, **k: pytest.fail("must NOT execute while CDP is down"))
    client = _CdpLoopClient(turns=[{"id": "t-1", "agent_slug": "eva"}])
    assert run_once(_cdp_loop_cfg(tmp_path), client) == "cdp_down"
    assert client.claims == 0  # nothing claimed -> nothing burned
    assert client.heartbeats[-1]["degraded"] is True  # surfaced as degraded, every tick


def test_cdp_unhealthy_heartbeat_reports_not_ready(monkeypatch, tmp_path):
    """The proactive case this whole feature exists for: a CDP-down runner must read as
    NOT ready on the server, not just "degraded". Before the fix, the unhealthy-branch
    heartbeat omitted ready/ready_note entirely, so it defaulted to ready=True — a
    CDP-down runner would still show up as ready in the control plane."""
    _stub_cdp(monkeypatch, healthy=False)
    client = _CdpLoopClient()
    run_once(_cdp_loop_cfg(tmp_path), client)
    hb = client.heartbeats[-1]
    assert hb["ready"] is False
    assert hb["ready_note"]  # a human-readable reason accompanies it


def test_cdp_down_still_polls_inbox_and_schedules(monkeypatch, tmp_path):
    """Inbound work must keep ENQUEUING while CDP is down — only the claim is gated."""
    _stub_cdp(monkeypatch, healthy=False)
    ran = {}
    monkeypatch.setattr(main_mod, "_maybe_check_inboxes",
                        lambda *a, **k: ran.__setitem__("inbox", True))
    monkeypatch.setattr(main_mod, "_fire_due_schedules",
                        lambda *a, **k: ran.__setitem__("sched", True))
    run_once(_cdp_loop_cfg(tmp_path), _CdpLoopClient())
    assert ran == {"inbox": True, "sched": True}


def test_cdp_recovery_drains_the_backlog(monkeypatch, tmp_path):
    """When emdash comes back, the next tick claims + drains the queued turn normally."""
    _stub_cdp(monkeypatch, healthy=False)
    monkeypatch.setattr("canopy_runner.execute.execute_turn",
                        lambda cfg, client, rid, turn: f"reused:{turn['id']}")
    cfg = _cdp_loop_cfg(tmp_path)
    client = _CdpLoopClient(turns=[{"id": "t-1", "agent_slug": "eva"}])

    assert run_once(cfg, client) == "cdp_down"  # down: the queued turn waits
    assert client.claims == 0

    monkeypatch.setattr("canopy_runner.cdp_control.cdp_healthy", lambda **k: True)  # emdash returns
    assert run_once(cfg, client) == "reused:t-1"  # back: drains the backlog
    assert client.claims == 1


def test_cdp_down_warning_is_throttled_to_one(monkeypatch, tmp_path, caplog):
    """A single throttled surface signal after sustained downtime — NOT per-tick spam.
    The degraded heartbeat still fires every tick (machine signal); the WARNING fires once."""
    _stub_cdp(monkeypatch, healthy=False)
    cfg = _cdp_loop_cfg(tmp_path)
    client = _CdpLoopClient()
    caplog.set_level("WARNING", logger="canopy_runner")
    ticks = main_mod.CDP_DOWN_SIGNAL_TICKS + 5
    for _ in range(ticks):
        run_once(cfg, client)
    warns = [r for r in caplog.records if "CDP unreachable" in r.getMessage()]
    assert len(warns) == 1  # ONE loud log despite many down ticks
    assert len(client.heartbeats) == ticks  # ...but a degraded heartbeat every tick
    assert all(h["degraded"] for h in client.heartbeats)


def test_cdp_recovery_logs_once_and_rearms(monkeypatch, tmp_path, caplog):
    """After recovery the throttle re-arms, so a SECOND outage warns again (not muted forever)."""
    cfg = _cdp_loop_cfg(tmp_path)
    client = _CdpLoopClient()
    caplog.set_level("INFO", logger="canopy_runner")

    _stub_cdp(monkeypatch, healthy=False)
    for _ in range(main_mod.CDP_DOWN_SIGNAL_TICKS):
        run_once(cfg, client)
    monkeypatch.setattr("canopy_runner.cdp_control.cdp_healthy", lambda **k: True)
    run_once(cfg, client)  # recovery — logs "healthy again" and re-arms the throttle
    assert any("healthy again" in r.getMessage() for r in caplog.records)

    caplog.clear()
    monkeypatch.setattr("canopy_runner.cdp_control.cdp_healthy", lambda **k: False)
    for _ in range(main_mod.CDP_DOWN_SIGNAL_TICKS):
        run_once(cfg, client)
    assert sum("CDP unreachable" in r.getMessage() for r in caplog.records) == 1  # warns again


def test_maybe_report_sessions_throttled(db, tmp_path, monkeypatch):
    """The session report (up to session_tail_count transcript reads) runs at most
    every session_report_seconds, even though the claim tick polls far faster."""
    from canopy_runner import main as m
    from canopy_runner import transcript
    cfg = _cfg(db, tmp_path)  # session_report_seconds defaults to 20
    calls = []
    monkeypatch.setattr(emdash, "list_open_sessions", lambda p: calls.append(1) or [])
    monkeypatch.setattr(transcript, "attach_recent_tail", lambda *a, **k: None)
    m._last_session_report = 0.0
    clock = [1000.0]
    now = lambda: clock[0]
    client = FakeClient()
    m._maybe_report_sessions(cfg, client, now_fn=now)   # first tick -> reports
    m._maybe_report_sessions(cfg, client, now_fn=now)   # within window -> skipped
    clock[0] += cfg.session_report_seconds + 1
    m._maybe_report_sessions(cfg, client, now_fn=now)   # window elapsed -> reports
    assert len(calls) == 2
