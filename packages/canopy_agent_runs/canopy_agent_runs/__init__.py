"""canopy_agent_runs — the Django-free run-lifecycle core.

A storage-agnostic read model (`Run` / `RunSummary` / `Step` / `Artifact` /
`Verdict` / `Decision` / `Gate`) plus the `RunStore` Protocol and its portable
adapters (`InMemoryRunStore`, and the Drive-backed `DriveRunStore` under
`canopy_agent_runs.drive`). Host apps (canopy-web, ace-web) supply their own
storage-backed adapters (e.g. a Django ORM `DbRunStore`) against the same
Protocol.

Importing this package pulls in NO Django and NO Google SDK — only pydantic
(+ pyyaml for the Drive parsers, imported under `canopy_agent_runs.drive`). The Google
SDK is needed only for the live `GoogleDriveClient` and is an optional extra
(`pip install "canopy-agent-runs[drive]"`).
"""
from __future__ import annotations

from .schemas import (
    Artifact,
    Decision,
    DecisionStatus,
    Gate,
    Run,
    RunMode,
    RunStatus,
    RunSummary,
    Step,
    StepStatus,
    StrictModel,
    Verdict,
    VerdictKind,
    derive_status,
)
from .stores import (
    FORK_MODES,
    InMemoryRunStore,
    RunStore,
)

__all__ = [
    # read model
    "Artifact",
    "Decision",
    "DecisionStatus",
    "Gate",
    "Run",
    "RunMode",
    "RunStatus",
    "RunSummary",
    "Step",
    "StepStatus",
    "StrictModel",
    "Verdict",
    "VerdictKind",
    "derive_status",
    # stores
    "FORK_MODES",
    "InMemoryRunStore",
    "RunStore",
]
