"""An in-memory fake DriveClient for the agent-run Drive-adapter tests.

Ported from ace-web `apps/opps/tests/fixtures/fake_drive.py`. This is the
parity corpus engine: tests build run-folder trees as nested dicts and the
fake serves them through canopy-web's own `DriveClient` Protocol
(`apps.agent_runs.drive.client`) — no Google, no SDK.

Usage:

    tree = {
        "ACE": {
            "malaria-pilot": {
                "opp.yaml": "slug: malaria-pilot\\n...",
                "runs": {
                    "r1": {"run_state.yaml": "..."},
                },
            }
        }
    }
    client = FakeDriveClient.from_tree(tree)
    files = client.list_files(client.folder_id("ACE/malaria-pilot"))
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from apps.agent_runs.drive.client import (
    ChangesPage,
    DriveFile,
    FileContent,
)


@dataclass
class _Node:
    id: str
    name: str
    parent_id: str | None
    mime_type: str  # "application/vnd.google-apps.folder" for folders
    body: str | None = None  # text body (None for folders + binary files)
    binary_body: bytes | None = None  # binary body (set via upload_binary)
    modified_time: str | None = None
    children: dict[str, _Node] = field(default_factory=dict)  # name -> node


class FakeDriveClient:
    """In-memory DriveClient (satisfies the `DriveClient` Protocol structurally).

    Supports the full read+write+changes surface the lifecycle uses, plus the
    binary/move helpers ACE's fake exposed (harmless extras beyond the minimal
    Protocol).
    """

    FOLDER_MIME = "application/vnd.google-apps.folder"

    def __init__(self):
        self._root = _Node(
            id="fake-root", name="", parent_id=None, mime_type=self.FOLDER_MIME
        )
        self._nodes_by_id: dict[str, _Node] = {"fake-root": self._root}
        self._counter = count(1)
        # Append-only (sequence, file_id) log; each mutation calls
        # _record_mutation. list_changes consumes the log, returning ids
        # whose sequence >= the input token (a decimal sequence number).
        self._mutation_log: list[tuple[int, str]] = []
        self._seq = count(1)

    @classmethod
    def from_tree(cls, tree: dict) -> FakeDriveClient:
        client = cls()
        client._load(client._root, tree)
        return client

    def _load(self, parent: _Node, tree: dict):
        for name, value in tree.items():
            nid = f"fake-{next(self._counter)}"
            if isinstance(value, dict):
                node = _Node(
                    id=nid, name=name, parent_id=parent.id, mime_type=self.FOLDER_MIME
                )
                parent.children[name] = node
                self._nodes_by_id[nid] = node
                self._load(node, value)
            else:
                mime = self._guess_mime(name)
                node = _Node(
                    id=nid, name=name, parent_id=parent.id, mime_type=mime, body=str(value)
                )
                parent.children[name] = node
                self._nodes_by_id[nid] = node

    @staticmethod
    def _guess_mime(name: str) -> str:
        if name.endswith(".yaml") or name.endswith(".yml"):
            return "application/x-yaml"
        if name.endswith(".md"):
            return "text/markdown"
        if name.endswith(".jsonl") or name.endswith(".json"):
            return "application/json"
        return "text/plain"

    def folder_id(self, path: str) -> str:
        """Test helper: resolve a slash-separated path to a folder id."""
        node = self._root
        for part in path.strip("/").split("/"):
            node = node.children[part]
        return node.id

    def file_id(self, path: str) -> str:
        """Test helper: resolve a slash-separated path to a file id."""
        node = self._root
        for part in path.strip("/").split("/"):
            node = node.children[part]
        return node.id

    def set_modified_time(self, path: str, iso_timestamp: str) -> None:
        """Set modified_time on a file-by-path, for test ordering setups."""
        node = self._nodes_by_id[self.folder_id(path)]
        node.modified_time = iso_timestamp

    def _record_mutation(self, file_id: str) -> None:
        self._mutation_log.append((next(self._seq), file_id))

    # --- DriveClient read surface ---

    def list_files(
        self, folder_id: str, recursive: bool = False, page_size: int = 100
    ) -> list[DriveFile]:
        node = self._nodes_by_id[folder_id]
        results: list[DriveFile] = []
        self._list(node, "", recursive, results)
        return results

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        return self.list_files(folder_id, recursive=False)

    def _list(self, node: _Node, prefix: str, recursive: bool, results: list):
        for name, child in node.children.items():
            child_path = f"{prefix}/{name}" if prefix else name
            if child.mime_type == self.FOLDER_MIME:
                if recursive:
                    self._list(child, child_path, True, results)
                else:
                    results.append(DriveFile(
                        id=child.id, name=name, mime_type=child.mime_type,
                        web_view_link=f"https://fake/{child.id}", path=child_path,
                        modified_time=child.modified_time,
                    ))
            else:
                if child.binary_body is not None:
                    size = len(child.binary_body)
                elif child.body is not None:
                    size = len(child.body.encode("utf-8"))
                else:
                    size = 0
                results.append(DriveFile(
                    id=child.id, name=name, mime_type=child.mime_type,
                    web_view_link=f"https://fake/{child.id}", path=child_path,
                    modified_time=child.modified_time,
                    size_bytes=size,
                ))

    def get_file(self, file_id: str) -> DriveFile:
        node = self._nodes_by_id[file_id]
        return DriveFile(
            id=node.id, name=node.name, mime_type=node.mime_type,
            web_view_link=f"https://fake/{node.id}", path=node.name,
            modified_time=node.modified_time,
        )

    def get_content(self, file_id: str, mime_type: str) -> FileContent:
        node = self._nodes_by_id[file_id]
        if node.body is None:
            raise ValueError(f"{node.name} is a folder, not a file")
        return FileContent(content=node.body, content_type=node.mime_type)

    # --- Write surface ---

    def create_folder(self, parent_id: str, name: str) -> str:
        parent = self._nodes_by_id[parent_id]
        if parent.mime_type != self.FOLDER_MIME:
            raise ValueError(f"{parent.name} is not a folder")
        nid = f"fake-{next(self._counter)}"
        node = _Node(
            id=nid, name=name, parent_id=parent.id, mime_type=self.FOLDER_MIME
        )
        parent.children[name] = node
        self._nodes_by_id[nid] = node
        self._record_mutation(nid)
        return nid

    def upload_file(
        self, parent_id: str, name: str, content: str, mime_type: str
    ) -> str:
        parent = self._nodes_by_id[parent_id]
        if parent.mime_type != self.FOLDER_MIME:
            raise ValueError(f"{parent.name} is not a folder")
        nid = f"fake-{next(self._counter)}"
        node = _Node(
            id=nid, name=name, parent_id=parent.id, mime_type=mime_type, body=content
        )
        parent.children[name] = node
        self._nodes_by_id[nid] = node
        self._record_mutation(nid)
        return nid

    def update_file(self, file_id: str, content: str, mime_type: str) -> None:
        node = self._nodes_by_id[file_id]
        if node.mime_type == self.FOLDER_MIME:
            raise ValueError(f"{node.name} is a folder, not a file")
        node.body = content
        node.binary_body = None
        node.mime_type = mime_type
        self._record_mutation(file_id)

    def upload_binary(
        self, parent_id: str, name: str, content: bytes, mime_type: str
    ) -> str:
        parent = self._nodes_by_id[parent_id]
        if parent.mime_type != self.FOLDER_MIME:
            raise ValueError(f"{parent.name} is not a folder")
        nid = f"fake-{next(self._counter)}"
        node = _Node(
            id=nid, name=name, parent_id=parent.id, mime_type=mime_type,
            binary_body=content,
        )
        parent.children[name] = node
        self._nodes_by_id[nid] = node
        self._record_mutation(nid)
        return nid

    def update_binary(self, file_id: str, content: bytes, mime_type: str) -> None:
        node = self._nodes_by_id[file_id]
        if node.mime_type == self.FOLDER_MIME:
            raise ValueError(f"{node.name} is a folder, not a file")
        node.binary_body = content
        node.body = None
        node.mime_type = mime_type
        self._record_mutation(file_id)

    def get_binary(self, file_id: str) -> bytes:
        node = self._nodes_by_id[file_id]
        if node.mime_type == self.FOLDER_MIME:
            raise ValueError(f"{node.name} is a folder, not a file")
        if node.binary_body is not None:
            return node.binary_body
        if node.body is not None:
            return node.body.encode("utf-8")
        raise ValueError(f"{node.name} has no content")

    def copy_file(
        self, file_id: str, new_parent_id: str, new_name: str | None = None
    ) -> str:
        src = self._nodes_by_id[file_id]
        if src.mime_type == self.FOLDER_MIME:
            raise ValueError(f"{src.name} is a folder; copy_file copies files only")
        parent = self._nodes_by_id[new_parent_id]
        if parent.mime_type != self.FOLDER_MIME:
            raise ValueError(f"{parent.name} is not a folder")
        nid = f"fake-{next(self._counter)}"
        name = new_name or src.name
        node = _Node(
            id=nid, name=name, parent_id=parent.id,
            mime_type=src.mime_type, body=src.body,
        )
        parent.children[name] = node
        self._nodes_by_id[nid] = node
        self._record_mutation(nid)
        return nid

    def move_file(self, file_id: str, new_parent_id: str) -> None:
        node = self._nodes_by_id.get(file_id)
        if node is None:
            raise ValueError(f"Unknown file id: {file_id}")
        if node.mime_type == self.FOLDER_MIME:
            raise ValueError(f"{node.name} is a folder; move_file moves files only")
        new_parent = self._nodes_by_id.get(new_parent_id)
        if new_parent is None or new_parent.mime_type != self.FOLDER_MIME:
            raise ValueError(f"{new_parent_id} is not a folder")
        if node.parent_id is not None:
            old_parent = self._nodes_by_id.get(node.parent_id)
            if old_parent is not None:
                old_parent.children.pop(node.name, None)
        new_parent.children[node.name] = node
        node.parent_id = new_parent.id
        self._record_mutation(file_id)

    def trash_folder(self, folder_id: str) -> None:
        node = self._nodes_by_id.get(folder_id)
        if node is None or node.parent_id is None:
            return
        parent = self._nodes_by_id[node.parent_id]
        parent.children.pop(node.name, None)

        def _drop(n):
            self._record_mutation(n.id)
            for child in list(n.children.values()):
                _drop(child)
            self._nodes_by_id.pop(n.id, None)

        _drop(node)

    # --- Changes feed (cache invalidation; matches DriveClient Protocol) ---

    def get_changes_start_page_token(self, drive_id: str | None = None) -> str:
        # "consider only mutations after this one"; peek without advancing.
        return str(self._peek_seq())

    def list_changes(
        self, page_token: str, *, drive_id: str | None = None
    ) -> ChangesPage:
        try:
            since = int(page_token)
        except ValueError:
            return ChangesPage(set(), str(self._peek_seq()), expired=False)
        changed: set[str] = set()
        max_seen = since
        for seq, fid in self._mutation_log:
            if seq >= since:
                changed.add(fid)
                max_seen = max(max_seen, seq)
        return ChangesPage(
            changed_file_ids=changed,
            next_page_token=str(max_seen + 1),
            expired=False,
        )

    def _peek_seq(self) -> int:
        if not self._mutation_log:
            return 1
        return self._mutation_log[-1][0] + 1


# --- Realistic fixture builders (parity corpus) ---

MALARIA_PILOT_IDD = """# Malaria Pilot IDD

Reduce malaria infant mortality in northern Mozambique via monthly
FLW-administered RDT screening and referral.
"""


def malaria_pilot_tree() -> dict:
    """Flat-layout fixture for malaria-pilot — the canonical shape the ACE
    plugin writes and ace-web reads."""
    return {
        "ACE": {
            "malaria-pilot": {
                "run_state.yaml": """current_phase: app-building
current_step: app-test
mode: review
started_at: 2026-04-01T10:00:00Z
created_by: neal@dimagi.com
display_name: Malaria Pilot — Northern Mozambique
""",
                "idea.md": "Seed idea for the malaria pilot.",
                "pdd.md": MALARIA_PILOT_IDD,
                "app-summaries": {
                    "learn-app-brief.md": "# Learn App Brief\n\n12 forms",
                    "deliver-app-brief.md": "# Deliver App\n\n4 workflows",
                },
                "test-results": {
                    "test-plan.md": "40 test cases",
                    "bug-list.md": "2 bugs found",
                },
                "training-materials": {
                    "facilitator-guide.md": "# Facilitator Guide\n\nOnboarding LLOs.",
                },
                "comms-log": {
                    "onboarding-email.md": "Welcome to the malaria pilot.",
                },
                "closeout": {
                    "cycle-grade.md": "# Cycle Grade\n\nOverall: B+",
                },
            }
        }
    }


def turmeric_multi_run_tree() -> dict:
    """Multi-run-layout fixture for turmeric — the ACE-plugin shape where
    run_state.yaml, idea.md, verdicts/ all live under ``runs/<run-id>/``.
    Opp root carries ``opp.yaml`` + an ``inputs/`` folder for the PDD."""
    return {
        "ACE": {
            "turmeric": {
                "opp.yaml": (
                    "display_name: Turmeric Market Survey\n"
                    "slug: turmeric\n"
                    "created_at: 2026-05-02T14:30:00Z\n"
                    "created_by: ace@dimagi-ai.com\n"
                ),
                "inputs": {
                    "pdd.md": "# Turmeric PDD\n\nFLWs photograph turmeric vendors.",
                },
                "runs": {
                    "20260502-1830": {
                        "run_state.yaml": (
                            "current_phase: ocs\n"
                            "current_step: ocs-agent-setup\n"
                            "mode: review\n"
                            "started_at: 2026-05-02T18:30:00Z\n"
                            "initiated_by: ace@dimagi-ai.com\n"
                            "last_actor: ace@dimagi-ai.com\n"
                            "last_actor_at: 2026-05-02T18:42:00Z\n"
                            "gates:\n"
                            "  idea-to-pdd:\n"
                            "    decision: approved\n"
                            "    decided_by: ace@dimagi-ai.com\n"
                            "    decided_at: 2026-05-02T18:35:30Z\n"
                            "    note: ''\n"
                        ),
                        "idea.md": "Turmeric idea body.",
                        "verdicts": {
                            "idea-to-pdd-deep.yaml": (
                                "skill: idea-to-pdd\n"
                                "verdict: pass\n"
                                "overall_score: 87\n"
                                "evaluated_at: 2026-05-02T18:35:00Z\n"
                            ),
                            "opp-eval-deep.yaml": (
                                "skill: opp-eval\n"
                                "mode: deep\n"
                                "overall_score: 84\n"
                                "verdict: pass\n"
                                "evaluated_at: 2026-05-02T18:40:00Z\n"
                            ),
                        },
                    },
                    "20260502-1430": {
                        "run_state.yaml": (
                            "current_phase: closeout\n"
                            "current_step: cycle-grade\n"
                            "mode: review\n"
                            "started_at: 2026-05-02T14:30:00Z\n"
                            "last_actor: ace@dimagi-ai.com\n"
                            "last_actor_at: 2026-05-02T16:01:00Z\n"
                        ),
                        "idea.md": "Earlier turmeric idea.",
                    },
                },
            }
        }
    }
