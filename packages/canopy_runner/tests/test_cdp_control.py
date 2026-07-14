"""Wrapper-level tests for the emdash CDP control (the sidecar itself needs a live
emdash on the debug port — validated separately)."""
import json
from types import SimpleNamespace

import pytest

from canopy_runner import cdp_control


def _fake_run(stdout, returncode=0, stderr=""):
    def run(cmd, capture_output, text, timeout):
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return run


def test_list_tasks_parses(monkeypatch):
    monkeypatch.setattr(cdp_control.subprocess, "run",
                        _fake_run(json.dumps({"ok": True, "tasks": ["a", "b"], "projects": ["echo"]})))
    r = cdp_control.list_tasks()
    assert r["tasks"] == ["a", "b"] and r["projects"] == ["echo"]


def test_open_send_ok(monkeypatch):
    monkeypatch.setattr(cdp_control.subprocess, "run",
                        _fake_run(json.dumps({"ok": True, "action": "sent", "task": "T"})))
    assert cdp_control.open_and_send("T", "hi there")["action"] == "sent"


def test_sidecar_error_raises_cdperror(monkeypatch):
    monkeypatch.setattr(cdp_control.subprocess, "run",
                        _fake_run(json.dumps({"ok": False, "error": 'no existing task "X"'})))
    with pytest.raises(cdp_control.CDPError, match="no existing task"):
        cdp_control.open_and_send("X", "hi")


def test_non_json_output_raises(monkeypatch):
    monkeypatch.setattr(cdp_control.subprocess, "run", _fake_run("kaboom not json", stderr="trace"))
    with pytest.raises(cdp_control.CDPError, match="non-JSON"):
        cdp_control.list_tasks()


def test_node_missing_raises(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(cdp_control.subprocess, "run", boom)
    with pytest.raises(cdp_control.CDPError, match="node not found"):
        cdp_control.list_tasks()


def test_host_id_has_user_and_host():
    h = cdp_control.host_id()
    assert "@" in h and len(h) > 2
