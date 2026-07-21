"""Plain-pytest suite for the reconciler (scan → diff → apply → preflight).

Both side-effect surfaces are faked: an in-memory Environment (the box) and an
in-memory secret store. No subprocess, no 1Password, no filesystem."""
from __future__ import annotations

from canopy_runtime import RuntimeSpec
from canopy_runtime.reconcile import reconcile
from canopy_runtime.schema import PluginRef


class FakeStore:
    def __init__(self, values: dict[str, str]):
        self.values = values

    def resolve_optional(self, name: str) -> str | None:
        return self.values.get(name) or None

    def resolve(self, name: str) -> str:  # pragma: no cover - unused here
        return self.values[name]

    def persist(self, name, value, *, vault=None):  # pragma: no cover
        self.values[name] = value


class FakeEnv:
    def __init__(self, *, tools=(), plugins=(), checks=None, fail_install=()):
        self._tools = set(tools)
        self._plugins = set(plugins)
        self._checks = checks or {}         # command -> (rc, output)
        self._fail_install = set(fail_install)
        self.installed: list[str] = []
        self.files: dict[str, str] = {}

    def has_tool(self, name):
        return name in self._tools

    def installed_plugins(self):
        return set(self._plugins)

    def install_plugin(self, plugin: PluginRef):
        if plugin.name in self._fail_install:
            raise RuntimeError("boom")
        self._plugins.add(plugin.name)
        self.installed.append(plugin.name)

    def run_check(self, command, env=None):
        self.last_check_env = env
        return self._checks.get(command, (0, ""))

    def write_file(self, path, content):
        self.files[path] = content


def _spec(**kw):
    return RuntimeSpec.model_validate(kw)


def test_warm_box_is_ready_with_no_gaps():
    spec = _spec(
        plugins=[{"name": "canopy"}],
        tools=[{"name": "claude"}],
        secrets=[{"name": "canopy-pat", "env": "CANOPY_PAT"}],
        preflight=[{"name": "authed", "run": "claude whoami", "expect": "@"}],
    )
    env = FakeEnv(tools=["claude"], plugins=["canopy"], checks={"claude whoami": (0, "echo@x")})
    store = FakeStore({"canopy-pat": "PAT"})

    result = reconcile(spec, store, env)
    assert result.ready
    assert result.gaps == []
    assert result.env["CANOPY_PAT"] == "PAT"
    assert env.installed == []  # warm — nothing to apply


def test_missing_plugin_is_installed():
    spec = _spec(plugins=[{"name": "echo", "source": "https://github.com/dimagi/echo"}])
    env = FakeEnv(plugins=[])
    result = reconcile(spec, FakeStore({}), env)
    assert result.ready
    assert "echo" in env.installed
    assert "plugin:echo" in result.applied


def test_failed_plugin_install_is_a_needs_human_gap():
    spec = _spec(plugins=[{"name": "echo"}])
    env = FakeEnv(fail_install=["echo"])
    result = reconcile(spec, FakeStore({}), env)
    assert not result.ready
    assert result.gaps[0].kind == "plugin" and result.gaps[0].needs_human


def test_missing_required_secret_is_needs_bootstrap():
    spec = _spec(secrets=[{"name": "claude-oauth-token", "env": "CLAUDE_CODE_OAUTH_TOKEN"}])
    result = reconcile(spec, FakeStore({}), FakeEnv())
    assert not result.ready
    assert len(result.needs_bootstrap) == 1
    assert result.needs_bootstrap[0].name == "claude-oauth-token"


def test_missing_optional_secret_is_skipped():
    spec = _spec(secrets=[{"name": "gog-token", "optional": True}])
    result = reconcile(spec, FakeStore({}), FakeEnv())
    assert result.ready
    assert result.gaps == []


def test_secret_with_path_is_written_as_a_file():
    spec = _spec(secrets=[{"name": "gog-oauth-client", "path": "/tmp/creds.json"}])
    env = FakeEnv()
    result = reconcile(spec, FakeStore({"gog-oauth-client": "CLIENTJSON"}), env)
    assert env.files["/tmp/creds.json"] == "CLIENTJSON"
    assert "/tmp/creds.json" in result.files_written


def test_secret_without_destination_falls_back_to_convention_env():
    spec = _spec(secrets=[{"name": "some-key"}])
    result = reconcile(spec, FakeStore({"some-key": "V"}), FakeEnv())
    assert result.env["CANOPY_SECRET_SOME_KEY"] == "V"


def test_missing_tool_is_a_gap():
    spec = _spec(tools=[{"name": "gh"}])
    result = reconcile(spec, FakeStore({}), FakeEnv(tools=[]))
    assert not result.ready
    assert result.gaps[0].kind == "tool"


def test_failing_preflight_is_a_gap():
    spec = _spec(preflight=[{"name": "authed", "run": "claude whoami", "expect": "@"}])
    env = FakeEnv(checks={"claude whoami": (0, "Not logged in")})  # rc 0 but wrong output
    result = reconcile(spec, FakeStore({}), env)
    assert not result.ready
    assert result.gaps[0].kind == "preflight" and result.gaps[0].needs_human


def test_dry_run_reports_but_does_not_apply():
    spec = _spec(
        plugins=[{"name": "echo"}],
        secrets=[{"name": "gog-oauth-client", "path": "/tmp/x.json"}],
    )
    env = FakeEnv()
    result = reconcile(spec, FakeStore({"gog-oauth-client": "J"}), env, apply=False)
    assert env.installed == []          # no install
    assert env.files == {}              # no file written
    assert any(g.kind == "plugin" for g in result.gaps)
    assert "/tmp/x.json" in result.files_written  # still reported as intended


def test_non_secret_env_literals_are_injected():
    spec = _spec(env={"ECHO_GMAIL_CLIENT": "echo", "ECHO_DRIVE_FOLDER_ID": "abc123"})
    result = reconcile(spec, FakeStore({}), FakeEnv())
    assert result.ready
    assert result.env["ECHO_GMAIL_CLIENT"] == "echo"
    assert result.env["ECHO_DRIVE_FOLDER_ID"] == "abc123"


def test_secret_overrides_a_literal_on_the_same_env_var():
    spec = _spec(
        env={"CANOPY_PAT": "placeholder"},
        secrets=[{"name": "canopy-pat", "env": "CANOPY_PAT"}],
    )
    result = reconcile(spec, FakeStore({"canopy-pat": "REALPAT"}), FakeEnv())
    assert result.env["CANOPY_PAT"] == "REALPAT"  # secret wins over the literal


def test_local_env_parses_claude_plugin_list(monkeypatch):
    import subprocess as _sp

    from canopy_runtime.reconcile import LocalEnvironment

    sample = (
        "Installed plugins:\n\n  ❯ ace@ace\n    Version: 0.13\n\n"
        "  ❯ canopy@canopy\n    Status: enabled\n  ❯ echo@echo\n"
    )
    monkeypatch.setattr(
        _sp, "run",
        lambda *a, **k: _sp.CompletedProcess(a, 0, sample, ""),
    )
    assert LocalEnvironment().installed_plugins() == {"ace", "canopy", "echo"}


def test_preflight_sees_resolved_secrets_in_env():
    spec = _spec(
        secrets=[{"name": "canopy-pat", "env": "CANOPY_PAT"}],
        preflight=[{"name": "pat-present", "run": "check", "expect": ""}],
    )
    env = FakeEnv(checks={"check": (0, "")})
    reconcile(spec, FakeStore({"canopy-pat": "REALPAT"}), env)
    # The preflight was handed the resolved env, so a `$CANOPY_PAT` probe can see it.
    assert env.last_check_env["CANOPY_PAT"] == "REALPAT"
