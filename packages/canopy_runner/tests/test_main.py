import json
import sqlite3
import time
import uuid
from pathlib import Path

import pytest

from canopy_runner import emdash
from canopy_runner.config import Config
from canopy_runner.main import GRACE_SECONDS, run_once

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
    assert result != f"failed:t-1"
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
