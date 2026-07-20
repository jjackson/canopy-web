"""CLI smoke tests using the env store (no 1Password) and a temp runtime.yaml."""
from __future__ import annotations

from pathlib import Path

from canopy_runtime.cli import agent_vault, main

SPEC = """
version: 1
env:
  ECHO_GMAIL_CLIENT: echo
secrets:
  - name: canopy-pat
    env: CANOPY_PAT
  - name: gog-token
    optional: true
"""


def _spec_file(tmp_path: Path) -> str:
    p = tmp_path / "runtime.yaml"
    p.write_text(SPEC)
    return str(p)


def test_agent_vault_naming():
    assert agent_vault("echo") == "Agent-Echo"
    assert agent_vault("ada") == "Agent-Ada"


def test_ready_when_required_secret_present(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CANOPY_SECRET_CANOPY_PAT", "PATVAL")
    rc = main(["--spec", _spec_file(tmp_path), "--agent", "echo",
               "--store", "env", "--dry-run", "--print-env"])
    assert rc == 0
    out = capsys.readouterr().out
    # shlex.quote leaves shell-safe values unquoted.
    assert "export CANOPY_PAT=PATVAL" in out
    assert "export ECHO_GMAIL_CLIENT=echo" in out


def test_not_ready_exits_3_when_required_secret_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("CANOPY_SECRET_CANOPY_PAT", raising=False)
    rc = main(["--spec", _spec_file(tmp_path), "--agent", "echo",
               "--store", "env", "--dry-run"])
    assert rc == 3  # canopy-pat missing → needs bootstrap


def test_env_file_is_written_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("CANOPY_SECRET_CANOPY_PAT", "PATVAL")
    envf = tmp_path / "out.env"
    rc = main(["--spec", _spec_file(tmp_path), "--agent", "echo", "--store", "env",
               "--dry-run", "--env-file", str(envf)])
    assert rc == 0
    assert "CANOPY_PAT=PATVAL" in envf.read_text()
    assert (envf.stat().st_mode & 0o777) == 0o600


def test_bad_spec_path_exits_2(tmp_path):
    assert main(["--spec", str(tmp_path / "nope.yaml"), "--agent", "echo", "--store", "env"]) == 2
