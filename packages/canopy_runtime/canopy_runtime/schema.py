"""The declarative runtime spec an agent ships in its own repo (`runtime.yaml`).

This is the *desired* runtime for one agent: which plugins it needs (canopy + ace +
its own), which MCP servers and tools, which execution engine it prefers, which
secrets it needs (**by reference name only — never a value**), and the preflight
checks that define "ready". The reconciler (RS2) reads this from the agent's repo,
diffs it against the current box, applies only the gaps, and runs the preflight.

canopy-web does NOT parse this — it only points a runner at the repo (RS1). This
module *defines and validates* the shape so the agent's PRs can be linted and the
reconciler can load it with confidence.

Two hard rules encoded here:
  1. `extra="forbid"` everywhere — a typo'd key is a validation error in the
     agent's PR, not a silently-ignored field that never provisions.
  2. `secrets` is a list of reference *names*. There is no field anywhere that
     holds a secret value; the value is resolved from the env's store (1Password
     on a laptop, Secrets Manager on a cloud box) by the reconciler.
"""
from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# The engine axis (RS4). Mirrors agents.Agent.runtime_engine on canopy-web.
Engine = Literal["emdash", "cloud_p", "any"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PluginRef(_Strict):
    """A `.claude-plugin` the agent depends on (canopy, ace, its own …)."""

    name: str = Field(min_length=1)
    # Where to get it: a git URL, a marketplace ref, or a local path. Empty means
    # "resolved by name from the default marketplace" — non-secret either way.
    source: str = ""


class McpRef(_Strict):
    """An MCP server the agent's runtime must have wired up."""

    name: str = Field(min_length=1)
    # Optional endpoint/command hint; empty = the plugin that provides it wires it.
    url: str = ""


class ToolRef(_Strict):
    """A CLI tool / binary the runtime requires on PATH (e.g. `gh`, `claude`)."""

    name: str = Field(min_length=1)


class PreflightCheck(_Strict):
    """One check that must pass for the box to be 'ready' for this agent.

    `run` is a NON-SECRET shell probe descriptor (e.g. `claude whoami`); `expect`
    is an optional substring the reconciler looks for in its output. A failing
    check the box can't self-heal (interactive OAuth) becomes 'needs bootstrap'.
    """

    name: str = Field(min_length=1)
    run: str = ""
    expect: str = ""


class SecretRef(_Strict):
    """A secret the agent needs, declared by REFERENCE NAME plus where its value
    must land. The name resolves against the env's store (1Password); `env` and/or
    `path` say how the runtime consumes it — the repo declares this because only
    the repo knows its own tools (claude wants `CLAUDE_CODE_OAUTH_TOKEN`, gog wants
    a credentials file). Still **never a value** — only a reference + destination.
    """

    name: str = Field(min_length=1)
    # Inject the resolved value into this environment variable (the common case).
    env: str = ""
    # Or write it to this file path (e.g. a gog credentials.json). `~` is expanded.
    path: str = ""
    # If true, absence is fine (skipped) rather than a "needs bootstrap" gap.
    optional: bool = False

    @field_validator("name")
    @classmethod
    def _name_is_a_ref_not_a_value(cls, v: str) -> str:
        if not v or len(v) > 120 or any(c in v for c in "= \t\n"):
            raise ValueError(
                f"secret name is a reference NAME, not a value; got {v!r}. "
                "Put the value in the env's secret store and reference its name."
            )
        return v


class RuntimeSpec(_Strict):
    """The whole `runtime.yaml` — one agent's declarative runtime."""

    version: int = 1
    engine: Engine = "any"
    plugins: list[PluginRef] = Field(default_factory=list)
    mcp: list[McpRef] = Field(default_factory=list)
    tools: list[ToolRef] = Field(default_factory=list)
    # Secret REFERENCES (name + destination), never values — see SecretRef.
    secrets: list[SecretRef] = Field(default_factory=list)
    preflight: list[PreflightCheck] = Field(default_factory=list)


def load_runtime_yaml(text: str) -> RuntimeSpec:
    """Parse + validate a runtime.yaml document. Raises on malformed YAML or a
    spec that violates the schema (unknown key, secret value, missing name)."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("runtime.yaml must be a mapping at the top level")
    return RuntimeSpec.model_validate(data)
