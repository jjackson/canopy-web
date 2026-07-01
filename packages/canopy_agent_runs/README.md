# canopy-agent-runs

The Django-free **run-lifecycle core** extracted from canopy-web's
`apps/agent_runs`. A separate project (e.g. ace-web) can `pip install` this and
get the storage-agnostic read model + the `RunStore` Protocol + the Drive
adapter, with no Django dependency.

## What's in here

- `canopy_agent_runs.schemas` — the read model: `Run` / `RunSummary` / `Step` /
  `Artifact` / `Verdict` / `Decision` / `Gate` (plain pydantic, `StrictModel`).
- `canopy_agent_runs.stores` — the `RunStore` Protocol, `InMemoryRunStore` (reference
  + tests), and the shared fork contract (`FORK_MODES`, `_apply_decision_edit`).
- `canopy_agent_runs.drive` — the `DriveClient` Protocol + parsers + `DriveRunStore`
  (reads ACE-shaped Drive run-folders into the read model). The live
  `GoogleDriveClient` needs the `drive` extra.

A host app supplies its own storage-backed adapter against the same Protocol —
canopy-web keeps a Django ORM `DbRunStore` in `apps/agent_runs/stores.py`.

## Install

```bash
pip install canopy-agent-runs            # core (pydantic + pyyaml)
pip install "canopy-agent-runs[drive]"   # + Google Drive SDK for GoogleDriveClient
```

## Django-free guarantee

`import canopy_agent_runs` (and `canopy_agent_runs.drive.store`) imports no Django. The
Google SDK in `google_client.py` is imported lazily and is opt-in via the
`drive` extra. Credential SOURCES are passed in as parameters — the package
never reads `django.conf.settings`.

## Tests

```bash
cd packages/canopy_agent_runs && pytest -q   # plain pytest, no DB
```
