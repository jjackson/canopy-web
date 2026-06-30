"""Drive-backed `RunStore` adapter + its `DriveClient` Protocol.

`canopy_agent_runs.drive.store.DriveRunStore` reads ACE-shaped Drive run-folders into
the storage-agnostic read model. The parsers + the in-memory contract are pure
Python + PyYAML. The live Google client (`google_client.GoogleDriveClient`)
needs the `drive` extra (`pip install "canopy-agent-runs[drive]"`) — its Google SDK
imports are lazy, so importing this subpackage stays SDK-free.
"""
