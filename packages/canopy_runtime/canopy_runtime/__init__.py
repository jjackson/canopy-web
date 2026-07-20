"""Django-free schema for an agent's declarative runtime spec (`runtime.yaml`).

The agent ships this file in its own repo; the reconciler reads + validates it to
provision a box for the agent's turn. canopy-web only points a runner at the repo
(it never parses the spec), so this library carries the shape both sides agree on.
"""
from __future__ import annotations

from canopy_runtime.schema import (
    Engine,
    McpRef,
    PluginRef,
    PreflightCheck,
    RuntimeSpec,
    ToolRef,
    load_runtime_yaml,
)

__all__ = [
    "Engine",
    "McpRef",
    "PluginRef",
    "PreflightCheck",
    "RuntimeSpec",
    "ToolRef",
    "load_runtime_yaml",
]
