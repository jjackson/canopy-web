"""The reconciler — bring a box to readiness for one agent's turn.

Given a validated ``RuntimeSpec`` (the agent's declared runtime), a ``SecretStore``
(1Password), and an ``Environment`` (the box), the reconciler:

    scan → diff → apply the gaps → preflight

It is **warm-aware**: it never assumes cold start. It scans what's already present
(installed plugins, tools on PATH, resolvable secrets) and only acts on what's
missing — so a laptop with emdash, or a warm cloud box, reconciles to a near-no-op
and drops straight into the turn. It is **idempotent**.

A gap the box *can* self-heal (a missing plugin) is applied. A gap it *can't*
(a secret nobody has minted, a failing interactive-auth preflight) is returned as a
**needs-bootstrap** gap — a first-class "a human must do this once" state, never a
half-provisioned run.

The ``Environment`` seam keeps this pure and testable: the reconciler holds the
scan→diff→apply logic; the side effects (install a plugin, run a probe, write a
file) live behind an injected object that tests fake and ``LocalEnvironment``
implements against the real box.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from canopy_runtime.schema import PluginRef, RuntimeSpec
from canopy_runtime.stores import SecretStore


@dataclass(frozen=True)
class Gap:
    """Something the spec wants that the box doesn't have yet."""

    kind: str          # "secret" | "tool" | "plugin" | "preflight"
    name: str
    detail: str = ""
    # True → a human must act once (mint a secret, do interactive OAuth): the box
    # cannot self-heal. This is the "needs bootstrap" state.
    needs_human: bool = False


@dataclass
class ReconcileResult:
    env: dict[str, str] = field(default_factory=dict)   # secrets to inject as env vars
    files_written: list[str] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)    # gaps the box self-healed
    gaps: list[Gap] = field(default_factory=list)        # remaining, unresolved

    @property
    def ready(self) -> bool:
        return not self.gaps

    @property
    def needs_bootstrap(self) -> list[Gap]:
        return [g for g in self.gaps if g.needs_human]


class Environment(Protocol):
    """The box the reconciler acts on. Faked in tests, real in ``LocalEnvironment``."""

    def has_tool(self, name: str) -> bool: ...
    def installed_plugins(self) -> set[str]: ...
    def install_plugin(self, plugin: PluginRef) -> None: ...
    def run_check(self, command: str, env: dict[str, str] | None = None) -> tuple[int, str]: ...
    def write_file(self, path: str, content: str) -> None: ...


def reconcile(
    spec: RuntimeSpec,
    store: SecretStore,
    env: Environment,
    *,
    apply: bool = True,
) -> ReconcileResult:
    """Reconcile ``env`` to ``spec``. With ``apply=False`` it only reports gaps
    (a dry scan) and never installs or writes anything."""
    result = ReconcileResult()

    # Non-secret literal env first, so a secret with the same target env var always
    # wins over a literal (secrets are the authority; literals are defaults/config).
    result.env.update(spec.env)
    _reconcile_secrets(spec, store, env, result, apply)
    _reconcile_tools(spec, env, result)
    _reconcile_plugins(spec, env, result, apply)
    _run_preflight(spec, env, result)

    return result


def _reconcile_secrets(spec, store, env, result, apply):
    for ref in spec.secrets:
        value = store.resolve_optional(ref.name)
        if value is None:
            if not ref.optional:
                result.gaps.append(
                    Gap("secret", ref.name, "no value in the secret store", needs_human=True)
                )
            continue
        if ref.env:
            result.env[ref.env] = value
        if ref.path:
            if apply:
                env.write_file(os.path.expanduser(ref.path), value)
            result.files_written.append(os.path.expanduser(ref.path))
        if not ref.env and not ref.path:
            # Resolvable but no declared destination — still expose it by a stable
            # convention so a wrapper can find it, rather than dropping it silently.
            result.env["CANOPY_SECRET_" + ref.name.upper().replace("-", "_")] = value


def _reconcile_tools(spec, env, result):
    for tool in spec.tools:
        if not env.has_tool(tool.name):
            # The reconciler can't know how to install an arbitrary tool — flag it
            # for a human/base-image fix rather than guessing.
            result.gaps.append(
                Gap("tool", tool.name, "not found on PATH", needs_human=True)
            )


def _reconcile_plugins(spec, env, result, apply):
    installed = env.installed_plugins()
    for plugin in spec.plugins:
        if plugin.name in installed:
            continue
        if not apply:
            result.gaps.append(Gap("plugin", plugin.name, "not installed"))
            continue
        try:
            env.install_plugin(plugin)
            result.applied.append(f"plugin:{plugin.name}")
        except Exception as exc:  # install is a real side effect; a failure is a gap
            result.gaps.append(
                Gap("plugin", plugin.name, f"install failed: {exc}", needs_human=True)
            )


def _run_preflight(spec, env, result):
    for check in spec.preflight:
        if not check.run:
            continue
        # Run with the secrets we just resolved in scope, so a real auth probe
        # (`claude whoami`, `gog whoami`, `test -n "$CANOPY_PAT"`) can see them.
        rc, out = env.run_check(check.run, result.env)
        ok = rc == 0 and (not check.expect or check.expect in out)
        if not ok:
            result.gaps.append(
                Gap("preflight", check.name, f"check failed (rc={rc})", needs_human=True)
            )


class LocalEnvironment:
    """Real ``Environment`` against the local box (laptop or cloud). Best-effort
    plugin discovery/install via the ``claude`` CLI; tools via PATH; secrets written
    0600."""

    def __init__(self, claude_bin: str = "claude") -> None:
        self.claude_bin = claude_bin

    def has_tool(self, name: str) -> bool:
        return shutil.which(name) is not None

    def installed_plugins(self) -> set[str]:
        # Best-effort: if `claude plugin list` isn't parseable, return empty so the
        # reconciler attempts installs (install is idempotent enough to re-run).
        try:
            res = subprocess.run(
                [self.claude_bin, "plugin", "list"],
                capture_output=True, text=True, timeout=30,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return set()
        if res.returncode != 0:
            return set()
        # `claude plugin list` prints one plugin per line as "  ❯ name@marketplace",
        # followed by indented "Version:/Scope:/Status:" detail lines. Pick the
        # "name@marketplace" token and keep the name.
        names: set[str] = set()
        for line in (res.stdout or "").splitlines():
            for token in line.split():
                if "@" in token and not token.startswith("@"):
                    names.add(token.split("@")[0])
        return names

    def install_plugin(self, plugin: PluginRef) -> None:
        target = plugin.source or plugin.name
        res = subprocess.run(
            [self.claude_bin, "plugin", "install", target],
            capture_output=True, text=True, timeout=300,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or f"install {target} failed")

    def run_check(self, command: str, env: dict[str, str] | None = None) -> tuple[int, str]:
        merged = {**os.environ, **env} if env else None
        res = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120, env=merged
        )
        return res.returncode, (res.stdout or "") + (res.stderr or "")

    def write_file(self, path: str, content: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        p.chmod(0o600)  # a secret on disk — owner-only
