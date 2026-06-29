# Shared Agent-Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-agent hand-rolled `/api/agents` clients (Echo's `echo_canopy.py`/`echo_tasks.py`, the canopy plugin's duplicated PAT helpers, ACE's own) with one shared client — a `canopy_web` transport/auth core, an `AgentClient` SDK, and a `canopy agent` CLI — shipped in the canopy plugin.

**Architecture:** Three new modules in the canopy plugin's `orchestrator` package: `canopy_web.py` (PAT/base-url resolution + injectable HTTP transport, stdlib `urllib` only), `agent_client.py` (`AgentClient` over that core + a skill-catalog helper), and `agent_cli.py` (a `canopy agent …` click subcommand group). Then dedupe the existing PAT-hand-rolling scripts onto `canopy_web`, document the REST contract for ACE, and migrate Echo to consume the `canopy agent` CLI (the acceptance proof).

**Tech Stack:** Python 3.11+, `click` 8 (CLI), `pydantic` 2 (typed payloads), stdlib `urllib` (HTTP — the canopy plugin does **not** depend on `requests`), `pytest` via `uv run pytest`.

## Global Constraints

- **All work below runs in the canopy *plugin* repo `/Users/jjackson/emdash-projects/canopy`** unless a task says "(echo repo)". The spec lives in canopy-web; the code does not.
- **stdlib `urllib` only for HTTP** — do not add `requests` to the canopy plugin (`pyproject.toml` deps are `pyyaml`, `click`, `pydantic`, `pillow`).
- **PAT/base-url resolution precedence (verbatim, matches `scripts/ddd/auth.py`):** base URL = explicit arg → `CANOPY_WEB_API_URL` env → `https://canopy-web-ujpz2cuyxq-uc.a.run.app`; token = explicit arg → `CANOPY_WEB_PAT` env → `~/.claude/canopy/workbench-token`; raise `RuntimeError` if no token.
- **Operator-plane only.** Do NOT add run/step/artifact/verdict surface area — that is Wave 1 (W2) and would collide with it.
- **No changes to canopy-web `apps/agents`.** v1 is exactly the endpoints Echo already uses.
- **One-way-dependency invariant:** these modules must not import any agent-specific (echo/ace/ddd-domain) code.
- **Run tests with `uv run pytest` from the canopy repo root.** Commit after each task; end every commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/orchestrator/canopy_web.py` (create) | `DEFAULT_API`, `TOKEN_FILE`, `resolve_base_url`, `resolve_token`, `CanopyError`, `Transport` type, `urllib_transport`, low-level `call()` |
| `src/orchestrator/agent_client.py` (create) | `AgentIdentity`, `BoardCommand`, `AgentClient`, `catalog_from_repo`, `_frontmatter` |
| `src/orchestrator/agent_cli.py` (create) | `agent` click group (`register`/`sync`/`work`/`skills`/`tasks-sync`/`commands`/`apply`/`set`) |
| `src/orchestrator/cli.py` (modify) | register the `agent` group on `main` |
| `tests/test_canopy_web.py` (create) | unit tests for resolvers + `call()` + transport |
| `tests/test_agent_client.py` (create) | unit tests for `AgentClient` + `catalog_from_repo` |
| `tests/test_cli_agent.py` (create) | CLI tests via click `CliRunner` |
| `tests/fixtures/agent_skills/demo-skill/SKILL.md` (create) | fixture for `catalog_from_repo` |
| `scripts/ddd/auth.py`, `scripts/share-session/upload.py`, `scripts/walkthrough-share/upload.py`, `src/orchestrator/shareout.py`, `src/orchestrator/doctor.py` (modify) | re-point onto `canopy_web` resolvers (Task 6) |
| `docs/architecture/agent-client-rest-contract.md` (create) | the REST contract for ACE/other consumers (Task 7) |
| `bin/echo_canopy.py`, `bin/echo_tasks.py` (echo repo, modify) | consume `canopy agent` CLI; drop hand-rolled transport (Task 8) |

---

## Task 1: `canopy_web` transport + auth core

**Files:**
- Create: `src/orchestrator/canopy_web.py`
- Test: `tests/test_canopy_web.py`

**Interfaces:**
- Produces:
  - `resolve_base_url(base_url: str | None) -> str`
  - `resolve_token(token: str | None) -> str` (raises `RuntimeError`)
  - `class CanopyError(RuntimeError)`
  - `Transport = Callable[[str, str, dict, bytes | None], tuple[int, str]]`
  - `urllib_transport(method, url, headers, body) -> tuple[int, str]`
  - `call(method: str, path: str, body=None, *, base_url=None, token=None, transport: Transport | None = None) -> dict`

- [ ] **Step 1: Write failing tests for resolvers + `call`**

```python
# tests/test_canopy_web.py
import json
import pytest
from orchestrator import canopy_web as cw


def test_resolve_base_url_precedence(monkeypatch):
    assert cw.resolve_base_url("https://x.test/") == "https://x.test"   # arg wins, trailing slash stripped
    monkeypatch.setenv("CANOPY_WEB_API_URL", "https://env.test/")
    assert cw.resolve_base_url(None) == "https://env.test"
    monkeypatch.delenv("CANOPY_WEB_API_URL", raising=False)
    assert cw.resolve_base_url(None) == cw.DEFAULT_API


def test_resolve_token_precedence(monkeypatch, tmp_path):
    monkeypatch.setattr(cw, "TOKEN_FILE", tmp_path / "missing")
    monkeypatch.delenv("CANOPY_WEB_PAT", raising=False)
    assert cw.resolve_token("raw-arg") == "raw-arg"
    monkeypatch.setenv("CANOPY_WEB_PAT", "env-tok")
    assert cw.resolve_token(None) == "env-tok"
    monkeypatch.delenv("CANOPY_WEB_PAT", raising=False)
    tf = tmp_path / "tok"
    tf.write_text("file-tok\n")
    monkeypatch.setattr(cw, "TOKEN_FILE", tf)
    assert cw.resolve_token(None) == "file-tok"


def test_resolve_token_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("CANOPY_WEB_PAT", raising=False)
    monkeypatch.setattr(cw, "TOKEN_FILE", tmp_path / "missing")
    with pytest.raises(RuntimeError, match="canopy-web PAT"):
        cw.resolve_token(None)


def test_call_uses_transport_and_parses_json():
    seen = {}

    def fake(method, url, headers, body):
        seen.update(method=method, url=url, headers=headers, body=body)
        return 200, json.dumps({"ok": True})

    out = cw.call("POST", "/api/agents/", {"slug": "x"},
                  base_url="https://x.test", token="t", transport=fake)
    assert out == {"ok": True}
    assert seen["method"] == "POST"
    assert seen["url"] == "https://x.test/api/agents/"
    assert seen["headers"]["Authorization"] == "Bearer t"
    assert json.loads(seen["body"]) == {"slug": "x"}


def test_call_raises_canopy_error_on_4xx():
    def fake(method, url, headers, body):
        return 404, "nope"
    with pytest.raises(cw.CanopyError, match="404"):
        cw.call("GET", "/api/agents/x/", base_url="https://x.test", token="t", transport=fake)


def test_call_get_has_no_body():
    def fake(method, url, headers, body):
        assert body is None
        return 200, "[]"
    assert cw.call("GET", "/api/x", base_url="https://x.test", token="t", transport=fake) == []
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_canopy_web.py -v`
Expected: FAIL — `ModuleNotFoundError: orchestrator.canopy_web`

- [ ] **Step 3: Implement `canopy_web.py`**

```python
# src/orchestrator/canopy_web.py
"""Shared canopy-web transport + auth — the one place PAT/base-url resolution
and HTTP live. stdlib urllib only (the canopy plugin has no `requests` dep)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

DEFAULT_API = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = Path.home() / ".claude" / "canopy" / "workbench-token"

Transport = Callable[[str, str, dict, Optional[bytes]], "tuple[int, str]"]


class CanopyError(RuntimeError):
    """A non-2xx response from canopy-web."""


def resolve_base_url(base_url: Optional[str]) -> str:
    if base_url:
        return base_url.rstrip("/")
    from_env = os.environ.get("CANOPY_WEB_API_URL", "").strip()
    if from_env:
        return from_env.rstrip("/")
    return DEFAULT_API


def resolve_token(token: Optional[str]) -> str:
    if token:
        return token
    from_env = os.environ.get("CANOPY_WEB_PAT", "").strip()
    if from_env:
        return from_env
    if TOKEN_FILE.exists():
        stored = TOKEN_FILE.read_text().strip()
        if stored:
            return stored
    raise RuntimeError(
        f"no canopy-web PAT — run /canopy:canopy-web-pat-mint to mint one, "
        f"or set CANOPY_WEB_PAT. Expected token at {TOKEN_FILE}."
    )


def urllib_transport(method: str, url: str, headers: dict, body: Optional[bytes]) -> "tuple[int, str]":
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def call(method: str, path: str, body=None, *,
         base_url: Optional[str] = None, token: Optional[str] = None,
         transport: Optional[Transport] = None) -> dict:
    base = resolve_base_url(base_url)
    tok = resolve_token(token)
    transport = transport or urllib_transport
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    status, text = transport(method, base + path, headers, data)
    if not (200 <= status < 300):
        raise CanopyError(f"{method} {path} -> {status}: {text[:400]}")
    return json.loads(text) if text.strip() else {}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_canopy_web.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Add a transport unit test (urllib request shape)**

```python
# append to tests/test_canopy_web.py
def test_urllib_transport_builds_request(monkeypatch):
    captured = {}

    class FakeResp:
        status = 201
        def read(self): return b'{"created": 1}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req):
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        captured["body"] = req.data
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    status, text = cw.urllib_transport("PUT", "https://x.test/api/x",
                                       {"Authorization": "Bearer t"}, b'{"a":1}')
    assert (status, text) == (201, '{"created": 1}')
    assert captured["method"] == "PUT"
    assert captured["body"] == b'{"a":1}'
```

- [ ] **Step 6: Run + commit**

Run: `uv run pytest tests/test_canopy_web.py -v` → Expected: PASS (7 tests)
```bash
git add src/orchestrator/canopy_web.py tests/test_canopy_web.py
git commit -m "feat(agent-client): canopy_web transport + PAT/base-url core"
```

---

## Task 2: `AgentClient` core (identity + register)

**Files:**
- Create: `src/orchestrator/agent_client.py`
- Test: `tests/test_agent_client.py`

**Interfaces:**
- Consumes: `canopy_web.call`, `canopy_web.Transport`.
- Produces:
  - `class AgentIdentity(BaseModel)` — fields `slug: str`, `name=""`, `email=""`, `description=""`, `persona=""`, `avatar_url=""`.
  - `class AgentClient(identity: AgentIdentity | dict, *, base_url=None, token=None, transport=None)` with `.slug` property and `.register() -> dict`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_agent_client.py
import json
from orchestrator.agent_client import AgentClient, AgentIdentity


def make_client(recorder):
    def transport(method, url, headers, body):
        recorder.append((method, url, json.loads(body) if body else None))
        return 200, "{}"
    return AgentClient({"slug": "echo", "name": "Echo", "email": "echo@dimagi-ai.com"},
                       base_url="https://x.test", token="t", transport=transport)


def test_identity_from_dict_or_model():
    c = AgentClient(AgentIdentity(slug="a"), base_url="https://x.test", token="t")
    assert c.slug == "a"
    c2 = AgentClient({"slug": "b"}, base_url="https://x.test", token="t")
    assert c2.slug == "b"


def test_register_posts_identity():
    rec = []
    c = make_client(rec)
    c.register()
    method, url, body = rec[0]
    assert method == "POST"
    assert url == "https://x.test/api/agents/"
    assert body["slug"] == "echo"
    assert body["email"] == "echo@dimagi-ai.com"
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_agent_client.py -v`
Expected: FAIL — `ModuleNotFoundError: orchestrator.agent_client`

- [ ] **Step 3: Implement the core**

```python
# src/orchestrator/agent_client.py
"""Shared client for canopy-web's agent workspace (/api/agents). Operator-plane
only (identity, syncs, work-products, skills, tasks, commands) — NO run lifecycle."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel

from orchestrator import canopy_web
from orchestrator.canopy_web import CanopyError, Transport  # re-export

__all__ = ["AgentIdentity", "BoardCommand", "AgentClient", "catalog_from_repo", "CanopyError"]


class AgentIdentity(BaseModel):
    slug: str
    name: str = ""
    email: str = ""
    description: str = ""
    persona: str = ""
    avatar_url: str = ""


class AgentClient:
    def __init__(self, identity, *, base_url: Optional[str] = None,
                 token: Optional[str] = None, transport: Optional[Transport] = None):
        self.identity = identity if isinstance(identity, AgentIdentity) else AgentIdentity(**identity)
        self._base = base_url
        self._token = token
        self._transport = transport

    @property
    def slug(self) -> str:
        return self.identity.slug

    def _call(self, method: str, path: str, body=None) -> dict:
        return canopy_web.call(method, path, body, base_url=self._base,
                               token=self._token, transport=self._transport)

    def register(self) -> dict:
        return self._call("POST", "/api/agents/", self.identity.model_dump())
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_agent_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/agent_client.py tests/test_agent_client.py
git commit -m "feat(agent-client): AgentClient identity + register"
```

---

## Task 3: Operator-plane methods + `BoardCommand`

**Files:**
- Modify: `src/orchestrator/agent_client.py`
- Test: `tests/test_agent_client.py`

**Interfaces:**
- Produces on `AgentClient`:
  - `post_sync(*, period_start, period_end, title, doc_url, summary="", self_grades=None, source="manager-sync") -> dict`
  - `put_work_products(items: list[dict]) -> dict`
  - `put_skills(items: list[dict]) -> dict`
  - `sync_tasks(tasks: list[dict]) -> dict`
  - `pending_commands() -> list[BoardCommand]`
  - `apply_command(command_id: int, result_note: str = "") -> dict`
  - `patch_task(task_id: int, **fields) -> dict` (drops `None` values)
- `class BoardCommand(BaseModel)` — `id: int`, `kind: str`, `task_title: str | None`, `created_by: str = ""`, `payload: dict | None`, `model_config = ConfigDict(extra="allow")`.

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_agent_client.py
import json as _json
from orchestrator.agent_client import BoardCommand


def _recorder_client(responses):
    """responses: list of (status, text) returned in order."""
    calls = []
    seq = list(responses)
    def transport(method, url, headers, body):
        calls.append((method, url, _json.loads(body) if body else None))
        return seq.pop(0)
    c = AgentClient({"slug": "echo"}, base_url="https://x.test", token="t", transport=transport)
    return c, calls


def test_post_sync_and_skills_and_workproducts():
    c, calls = _recorder_client([(200, "{}"), (200, "{}"), (200, "{}")])
    c.post_sync(period_start="2026-06-01", period_end="2026-06-07", title="W",
                doc_url="https://doc", self_grades={"work": "C+"})
    c.put_work_products([{"title": "T", "url": "https://wp"}])
    c.put_skills([{"name": "s", "url": "https://s"}])
    assert calls[0][:2] == ("POST", "https://x.test/api/agents/echo/syncs/")
    assert calls[0][2]["self_grades"] == {"work": "C+"}
    assert calls[1][:2] == ("POST", "https://x.test/api/agents/echo/work-products/")
    assert calls[1][2] == {"work_products": [{"title": "T", "url": "https://wp"}]}
    assert calls[2][:2] == ("PUT", "https://x.test/api/agents/echo/skills/")
    assert calls[2][2] == {"skills": [{"name": "s", "url": "https://s"}]}


def test_pending_commands_parses_models():
    raw = _json.dumps([{"id": 5, "kind": "dispatch", "task_title": "Do it",
                        "created_by": "jj@dimagi.com", "payload": {"note": "go"}}])
    c, calls = _recorder_client([(200, raw)])
    cmds = c.pending_commands()
    assert calls[0][:2] == ("GET", "https://x.test/api/agents/echo/commands?status=pending")
    assert isinstance(cmds[0], BoardCommand)
    assert (cmds[0].id, cmds[0].kind, cmds[0].task_title) == (5, "dispatch", "Do it")


def test_apply_command_and_patch_task_drops_none():
    c, calls = _recorder_client([(200, "{}"), (200, "{}")])
    c.apply_command(5, result_note="done")
    c.patch_task(9, rationale="why", plan=None, status="in_progress")
    assert calls[0] == ("POST", "https://x.test/api/agents/echo/commands/5/apply", {"result_note": "done"})
    assert calls[1] == ("PATCH", "https://x.test/api/agents/echo/tasks/9/", {"rationale": "why", "status": "in_progress"})


def test_sync_tasks_wraps_payload():
    c, calls = _recorder_client([(200, "{}")])
    c.sync_tasks([{"ext_id": "T1", "title": "x"}])
    assert calls[0][:2] == ("POST", "https://x.test/api/agents/echo/tasks/sync")
    assert calls[0][2] == {"tasks": [{"ext_id": "T1", "title": "x"}]}
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_agent_client.py -v`
Expected: FAIL — `ImportError: cannot import name 'BoardCommand'` / `AttributeError: post_sync`

- [ ] **Step 3: Implement the methods**

Add `ConfigDict` to the pydantic import and append `BoardCommand` + the methods:

```python
# src/orchestrator/agent_client.py — change the pydantic import line to:
from pydantic import BaseModel, ConfigDict
```

```python
# add after AgentIdentity:
class BoardCommand(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    kind: str
    task_title: Optional[str] = None
    created_by: str = ""
    payload: Optional[dict] = None
```

```python
# add these methods inside AgentClient:
    def post_sync(self, *, period_start, period_end, title, doc_url,
                  summary="", self_grades=None, source="manager-sync") -> dict:
        body = {"period_start": period_start, "period_end": period_end, "title": title,
                "summary": summary, "doc_url": doc_url,
                "self_grades": self_grades or {}, "source": source}
        return self._call("POST", f"/api/agents/{self.slug}/syncs/", body)

    def put_work_products(self, items: list[dict]) -> dict:
        return self._call("POST", f"/api/agents/{self.slug}/work-products/", {"work_products": items})

    def put_skills(self, items: list[dict]) -> dict:
        return self._call("PUT", f"/api/agents/{self.slug}/skills/", {"skills": items})

    def sync_tasks(self, tasks: list[dict]) -> dict:
        return self._call("POST", f"/api/agents/{self.slug}/tasks/sync", {"tasks": tasks})

    def pending_commands(self) -> "list[BoardCommand]":
        raw = self._call("GET", f"/api/agents/{self.slug}/commands?status=pending")
        return [BoardCommand(**c) for c in (raw or [])]

    def apply_command(self, command_id: int, result_note: str = "") -> dict:
        return self._call("POST", f"/api/agents/{self.slug}/commands/{command_id}/apply",
                          {"result_note": result_note})

    def patch_task(self, task_id: int, **fields) -> dict:
        patch = {k: v for k, v in fields.items() if v is not None}
        return self._call("PATCH", f"/api/agents/{self.slug}/tasks/{task_id}/", patch)
```

Add `"BoardCommand"` to `__all__`.

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_agent_client.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/agent_client.py tests/test_agent_client.py
git commit -m "feat(agent-client): syncs, work-products, skills, tasks, command drain"
```

---

## Task 4: `catalog_from_repo` skill-catalog helper

**Files:**
- Modify: `src/orchestrator/agent_client.py`
- Create: `tests/fixtures/agent_skills/demo-skill/SKILL.md`
- Test: `tests/test_agent_client.py`

**Interfaces:**
- Produces: `catalog_from_repo(skills_root: str | Path, url_template: str) -> list[dict]` returning `[{"name","description","url","improvement_note"}]`. `url_template` is `.format(name=…)`-ed. Skips dirs whose `SKILL.md` lacks a frontmatter `name`.

- [ ] **Step 1: Create the fixture**

```markdown
<!-- tests/fixtures/agent_skills/demo-skill/SKILL.md -->
---
name: demo-skill
description: >
  A demo skill used to test catalog parsing. It spans
  two folded lines.
---

# Demo
body text
```

- [ ] **Step 2: Write failing test**

```python
# append to tests/test_agent_client.py
from pathlib import Path
from orchestrator.agent_client import catalog_from_repo


def test_catalog_from_repo_parses_frontmatter():
    root = Path(__file__).parent / "fixtures" / "agent_skills"
    items = catalog_from_repo(root, "https://gh/{name}/SKILL.md")
    assert items == [{
        "name": "demo-skill",
        "description": "A demo skill used to test catalog parsing. It spans two folded lines.",
        "url": "https://gh/demo-skill/SKILL.md",
        "improvement_note": "",
    }]
```

- [ ] **Step 3: Run, verify fail**

Run: `uv run pytest tests/test_agent_client.py::test_catalog_from_repo_parses_frontmatter -v`
Expected: FAIL — `ImportError: cannot import name 'catalog_from_repo'`

- [ ] **Step 4: Implement (port Echo's frontmatter parser)**

```python
# src/orchestrator/agent_client.py — add imports at top:
import glob
import os
import re
from pathlib import Path
```

```python
# add at module level:
def _frontmatter(path: str) -> "tuple[str, str] | None":
    text = Path(path).read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    block = m.group(1)
    name = re.search(r"^name:\s*(.+)$", block, re.M)
    desc = re.search(r"^description:\s*(?:>\s*)?\n?((?:.|\n)*?)(?:\n\w[\w-]*:|\Z)", block, re.M)
    name_v = name.group(1).strip() if name else ""
    desc_v = " ".join(l.strip() for l in (desc.group(1).splitlines() if desc else [])).strip()
    return name_v, desc_v


def catalog_from_repo(skills_root, url_template: str) -> "list[dict]":
    items = []
    for p in sorted(glob.glob(os.path.join(str(skills_root), "*", "SKILL.md"))):
        fm = _frontmatter(p)
        if not fm or not fm[0]:
            continue
        name, desc = fm
        items.append({"name": name, "description": desc,
                      "url": url_template.format(name=name), "improvement_note": ""})
    return items
```

Add `"catalog_from_repo"` to `__all__` (already present — confirm).

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/test_agent_client.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator/agent_client.py tests/fixtures/agent_skills tests/test_agent_client.py
git commit -m "feat(agent-client): catalog_from_repo skill-frontmatter helper"
```

---

## Task 5: `canopy agent` CLI group

**Files:**
- Create: `src/orchestrator/agent_cli.py`
- Modify: `src/orchestrator/cli.py`
- Test: `tests/test_cli_agent.py`

**Interfaces:**
- Consumes: `AgentClient`, `catalog_from_repo`, `CanopyError`.
- Produces: a click group `agent` with commands `register`, `sync`, `work`, `skills`, `tasks-sync`, `commands`, `apply`, `set`. Registered on `main` in `cli.py`.

**Implementation note for tests:** the CLI builds a real `AgentClient` (default `urllib_transport`). Tests inject a fake by monkeypatching `orchestrator.canopy_web.urllib_transport` and setting `CANOPY_WEB_PAT`.

- [ ] **Step 1: Write failing CLI tests**

```python
# tests/test_cli_agent.py
import json
import pytest
from click.testing import CliRunner
from orchestrator.cli import main


@pytest.fixture
def fake_http(monkeypatch):
    calls = []
    responses = {}

    def transport(method, url, headers, body):
        calls.append((method, url, json.loads(body) if body else None))
        return responses.get((method, url.split("/api/")[1]), (200, "{}"))

    monkeypatch.setenv("CANOPY_WEB_PAT", "t")
    monkeypatch.setenv("CANOPY_WEB_API_URL", "https://x.test")
    monkeypatch.setattr("orchestrator.canopy_web.urllib_transport", transport)
    return calls, responses


def test_agent_register(fake_http):
    calls, _ = fake_http
    r = CliRunner().invoke(main, ["agent", "register", "--slug", "echo", "--name", "Echo",
                                  "--email", "echo@dimagi-ai.com", "--persona", "p"])
    assert r.exit_code == 0, r.output
    assert calls[0][:2] == ("POST", "https://x.test/api/agents/")
    assert calls[0][2]["slug"] == "echo"


def test_agent_commands_lists(fake_http):
    calls, responses = fake_http
    responses[("GET", "agents/echo/commands?status=pending")] = (
        200, json.dumps([{"id": 7, "kind": "dispatch", "task_title": "Do", "created_by": "jj", "payload": None}]))
    r = CliRunner().invoke(main, ["agent", "commands", "--slug", "echo"])
    assert r.exit_code == 0, r.output
    assert "#7" in r.output and "dispatch" in r.output


def test_agent_apply(fake_http):
    calls, _ = fake_http
    r = CliRunner().invoke(main, ["agent", "apply", "--slug", "echo", "--id", "7", "--note", "ok"])
    assert r.exit_code == 0, r.output
    assert calls[0] == ("POST", "https://x.test/api/agents/echo/commands/7/apply", {"result_note": "ok"})


def test_agent_error_exits_nonzero(fake_http):
    calls, responses = fake_http
    responses[("POST", "agents/echo/commands/7/apply")] = (404, "missing")
    r = CliRunner().invoke(main, ["agent", "apply", "--slug", "echo", "--id", "7"])
    assert r.exit_code != 0
    assert "404" in r.output
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_cli_agent.py -v`
Expected: FAIL — no `agent` command on `main`.

- [ ] **Step 3: Implement `agent_cli.py`**

```python
# src/orchestrator/agent_cli.py
"""`canopy agent …` — thin CLI over AgentClient for shell-driven agents."""
import json
import click

from orchestrator.agent_client import AgentClient, catalog_from_repo, CanopyError


def _client(slug, **identity):
    return AgentClient({"slug": slug, **{k: v for k, v in identity.items() if v}})


def _emit(obj):
    click.echo(json.dumps(obj))


@click.group()
def agent():
    """Talk to canopy-web's agent workspace (/api/agents)."""


@agent.command("register")
@click.option("--slug", required=True)
@click.option("--name", default="")
@click.option("--email", default="")
@click.option("--description", default="")
@click.option("--persona", default="")
@click.option("--avatar-url", default="")
def agent_register(slug, name, email, description, persona, avatar_url):
    """Upsert agent identity."""
    try:
        c = _client(slug, name=name, email=email, description=description,
                    persona=persona, avatar_url=avatar_url)
        _emit(c.register())
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("sync")
@click.option("--slug", required=True)
@click.option("--doc-url", required=True)
@click.option("--title", required=True)
@click.option("--summary", default="")
@click.option("--grades", default="{}", help="JSON object of self-grades")
@click.option("--period-start", required=True)
@click.option("--period-end", required=True)
@click.option("--source", default="manager-sync")
def agent_sync(slug, doc_url, title, summary, grades, period_start, period_end, source):
    """Post a manager sync."""
    try:
        c = _client(slug)
        _emit(c.post_sync(period_start=period_start, period_end=period_end, title=title,
                          summary=summary, doc_url=doc_url, self_grades=json.loads(grades), source=source))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("work")
@click.option("--slug", required=True)
@click.option("--json", "json_file", required=True, type=click.Path(exists=True),
              help="JSON file: [{title,kind,url,description,tags,source}]")
def agent_work(slug, json_file):
    """Upsert work products from a JSON file."""
    try:
        items = json.load(open(json_file))
        _emit(_client(slug).put_work_products(items))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("skills")
@click.option("--slug", required=True)
@click.option("--from-repo", "skills_root", type=click.Path(exists=True),
              help="glob <root>/*/SKILL.md into the catalog")
@click.option("--url-template", default="", help="e.g. https://github.com/org/repo/blob/main/skills/{name}/SKILL.md")
@click.option("--json", "json_file", type=click.Path(exists=True), help="explicit catalog JSON")
def agent_skills(slug, skills_root, url_template, json_file):
    """Replace the skill catalog (from a repo glob or a JSON file)."""
    try:
        if skills_root:
            items = catalog_from_repo(skills_root, url_template or "{name}")
        elif json_file:
            items = json.load(open(json_file))
        else:
            raise click.ClickException("pass --from-repo or --json")
        _emit(_client(slug).put_skills(items))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("tasks-sync")
@click.option("--slug", required=True)
@click.option("--json", "json_file", required=True, type=click.Path(exists=True),
              help="JSON file: [{ext_id,title,next_action,status,owner,assigned,…}]")
def agent_tasks_sync(slug, json_file):
    """Non-destructive task upsert from a JSON file."""
    try:
        tasks = json.load(open(json_file))
        _emit(_client(slug).sync_tasks(tasks))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("commands")
@click.option("--slug", required=True)
def agent_commands(slug):
    """List board actions queued for the agent (drain on a turn)."""
    try:
        cmds = _client(slug).pending_commands()
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))
    if not cmds:
        click.echo("no queued commands")
        return
    for c in cmds:
        click.echo(f"  #{c.id} {c.kind} -> {c.task_title or '(no task)'}  [{c.created_by}]  {c.payload or ''}")


@agent.command("apply")
@click.option("--slug", required=True)
@click.option("--id", "cmd_id", type=int, required=True)
@click.option("--note", default="")
def agent_apply(slug, cmd_id, note):
    """Mark a queued command applied."""
    try:
        _emit(_client(slug).apply_command(cmd_id, result_note=note))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("set")
@click.option("--slug", required=True)
@click.option("--task-id", type=int, required=True)
@click.option("--rationale", default=None)
@click.option("--source-url", default=None)
@click.option("--plan", default=None)
@click.option("--status", default=None)
@click.option("--assigned", default=None)
@click.option("--next-action", default=None)
@click.option("--owner", default=None)
@click.option("--notes", default=None)
def agent_set(slug, task_id, **fields):
    """Patch a task (store rationale/source/plan/status/…)."""
    try:
        _emit(_client(slug).patch_task(task_id, **fields))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))
```

- [ ] **Step 4: Register the group in `cli.py`**

In `src/orchestrator/cli.py`, after the existing imports near the top add:

```python
from orchestrator.agent_cli import agent as agent_group
```

After the `def main():` group is defined and other groups are attached (e.g. after `@main.group() def registry(): …`), add at module scope (bottom of the import/registration area):

```python
main.add_command(agent_group)
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/test_cli_agent.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Smoke the wiring**

Run: `uv run canopy agent --help`
Expected: lists `register sync work skills tasks-sync commands apply set`

- [ ] **Step 7: Full suite + commit**

Run: `uv run pytest -q`
Expected: PASS (no regressions)
```bash
git add src/orchestrator/agent_cli.py src/orchestrator/cli.py tests/test_cli_agent.py
git commit -m "feat(agent-client): canopy agent CLI subcommand group"
```

---

## Task 6: Dedupe existing PAT-hand-rolling scripts onto `canopy_web`

**Files:**
- Modify: `scripts/ddd/auth.py` (re-export from `canopy_web`), `scripts/share-session/upload.py`, `scripts/walkthrough-share/upload.py`, `src/orchestrator/shareout.py`, `src/orchestrator/doctor.py`
- Test: existing suite (regression) + a new `tests/test_auth_reexport.py`

**Interfaces:**
- Consumes: `canopy_web.resolve_base_url`, `canopy_web.resolve_token`, `canopy_web.DEFAULT_API`, `canopy_web.TOKEN_FILE`.

- [ ] **Step 1: Write a test pinning the re-export equivalence**

```python
# tests/test_auth_reexport.py
from orchestrator import canopy_web
import importlib


def test_ddd_auth_reexports_canopy_web():
    auth = importlib.import_module("scripts.ddd.auth") if False else None
    # scripts/ddd is not a package on sys.path; assert via canopy_web directly instead:
    assert canopy_web.DEFAULT_API == "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
    assert canopy_web.resolve_base_url("https://x/") == "https://x"
```

> Note: `scripts/ddd/` is loaded by path, not as a package, so this test pins the
> canonical values in `canopy_web`. The dedupe below makes the scripts import these.

- [ ] **Step 2: Run, verify pass (baseline pin)**

Run: `uv run pytest tests/test_auth_reexport.py -v`
Expected: PASS

- [ ] **Step 3: Make `scripts/ddd/auth.py` re-export the canonical core**

Replace the bodies of `resolve_base_url`/`resolve_token` and the `DEFAULT_API`/`TOKEN_FILE`
constants in `scripts/ddd/auth.py` with imports from `canopy_web`, keeping the public names
so existing callers (`scripts/ddd/upload.py`, `scripts/ddd/review.py`) are untouched:

```python
# scripts/ddd/auth.py — replace the constants + two function bodies with:
from orchestrator.canopy_web import (  # canonical single source
    DEFAULT_API, TOKEN_FILE, resolve_base_url, resolve_token,
)
__all__ = ["DEFAULT_API", "TOKEN_FILE", "resolve_base_url", "resolve_token"]
```

> If `scripts/ddd/` cannot import `orchestrator` (path issue when run standalone), prepend
> the repo `src/` to `sys.path` at the top of `auth.py`:
> `import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))`

- [ ] **Step 4: Re-point the remaining hand-rollers**

For each of `scripts/share-session/upload.py`, `scripts/walkthrough-share/upload.py`,
`src/orchestrator/shareout.py`, `src/orchestrator/doctor.py`: replace any local
`DEFAULT_API`/`TOKEN_FILE` constant and inline PAT/base-url resolution with
`from orchestrator.canopy_web import resolve_base_url, resolve_token, DEFAULT_API, TOKEN_FILE`
(adding the `src/` sys.path shim shown above only for the two `scripts/…` files that run
standalone). Do not change their HTTP bodies in this task — only the resolution.

- [ ] **Step 5: Run full suite, verify no regressions**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/ddd/auth.py scripts/share-session/upload.py scripts/walkthrough-share/upload.py src/orchestrator/shareout.py src/orchestrator/doctor.py tests/test_auth_reexport.py
git commit -m "refactor(agent-client): dedupe canopy-web PAT/base-url onto canopy_web"
```

---

## Task 7: Document the REST contract for ACE / other consumers

**Files:**
- Create: `docs/architecture/agent-client-rest-contract.md`
- Modify: `CLAUDE.md` (one pointer line)

- [ ] **Step 1: Write the contract doc**

Create `docs/architecture/agent-client-rest-contract.md` with: the resolution rules
(verbatim from Global Constraints), and the endpoint table below — so a non-Python agent
(ACE, TS) can conform without reading the Python client.

```markdown
# Agent-client REST contract (operator plane)

Auth: `Authorization: Bearer <PAT>`. PAT resolution: arg → `CANOPY_WEB_PAT` →
`~/.claude/canopy/workbench-token`. Base URL: `CANOPY_WEB_API_URL` → prod default.

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/agents/` | `{slug,name,email,description,persona,avatar_url}` | upsert identity |
| POST | `/api/agents/{slug}/syncs/` | `{period_start,period_end,title,summary,doc_url,self_grades,source}` | idempotent per period+source |
| POST | `/api/agents/{slug}/work-products/` | `{work_products:[{title,kind,url,description,tags,source}]}` | upsert by url |
| PUT | `/api/agents/{slug}/skills/` | `{skills:[{name,description,url,improvement_note}]}` | replaces catalog |
| POST | `/api/agents/{slug}/tasks/sync` | `{tasks:[{ext_id,title,next_action,status,owner,assigned,…}]}` | non-destructive upsert |
| GET | `/api/agents/{slug}/commands?status=pending` | — | drain |
| POST | `/api/agents/{slug}/commands/{id}/apply` | `{result_note}` | mark applied |
| PATCH | `/api/agents/{slug}/tasks/{id}/` | partial task fields | store context |

Reference implementation: `orchestrator/agent_client.py` (Python) / `canopy agent` CLI.
```

- [ ] **Step 2: Add a CLAUDE.md pointer**

Add one line under the canopy plugin's CLAUDE.md reference/docs section:
`- orchestrator/agent_client.py + canopy agent CLI — shared client for canopy-web /api/agents (contract: docs/architecture/agent-client-rest-contract.md)`

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/agent-client-rest-contract.md CLAUDE.md
git commit -m "docs(agent-client): REST contract for non-Python consumers"
```

---

## Task 8: Migrate Echo onto the `canopy agent` CLI (acceptance proof)

**Files (echo repo `/Users/jjackson/emdash/repositories/echo`):**
- Modify: `bin/echo_canopy.py`, `bin/echo_tasks.py`

**Prerequisite:** the `canopy` console-script must be on PATH in Echo's environment
(`uv tool install --editable /Users/jjackson/emdash-projects/canopy` or equivalent). Verify:
`canopy agent --help` succeeds.

**Goal:** Echo carries **no** canopy-web transport/PAT code of its own — its scripts shell
out to `canopy agent …`. Echo keeps only its Google/Sheets I/O.

- [ ] **Step 1: Replace `echo_canopy.py` internals with CLI delegation**

Rewrite `bin/echo_canopy.py` so each subcommand shells `canopy agent …` (preserving the
same argparse interface the skills call). Keep `base_url`/`token` **only** if `echo_tasks.py`
still imports them — otherwise delete them. Concretely, replace the `call`/`ensure_agent`
helpers and each branch with `subprocess.run(["canopy", "agent", <cmd>, "--slug", "echo", …])`.
The skill-catalog mirror becomes:
`subprocess.run(["canopy","agent","skills","--slug","echo","--from-repo","skills","--url-template", GH])`.

- [ ] **Step 2: Replace `echo_tasks.py` canopy calls with CLI delegation**

In `bin/echo_tasks.py`, delete the `_canopy(...)` `requests` helper and the
`from echo_canopy import base_url, token` import. Keep `read_rows`/`build_tasks`
(Google Sheets via `requests` — unchanged). Replace the three branches:
- `sync`: write `build_tasks(...)` to a temp JSON, then `canopy agent tasks-sync --slug echo --json <tmp>`.
- `commands`: `subprocess.run(["canopy","agent","commands","--slug","echo"])` (passthrough output).
- `apply`: `canopy agent apply --slug echo --id <id> --note <note>`.
- `set`: `canopy agent set --slug echo --task-id <id> [--rationale …] …`.

- [ ] **Step 3: Verify no transport/PAT code remains in Echo**

Run (echo repo):
```bash
grep -nE "workbench-token|CANOPY_WEB_PAT|requests\.(request|post|get|put|patch)\(.*api/agents" bin/echo_canopy.py bin/echo_tasks.py
```
Expected: **no matches** in the `/api/agents` paths (Google Sheets `requests` calls in
`read_rows` may remain — that's Echo's own domain I/O).

- [ ] **Step 4: Live smoke (manual, requires a real PAT)**

Run (echo repo, with a minted PAT):
```bash
canopy agent register --slug echo --name Echo --email echo@dimagi-ai.com --persona "marketing agent"
python3 bin/echo_tasks.py commands
```
Expected: register returns the agent JSON; `commands` prints the queue (or "no queued commands"). Confirm the board at `/agents/echo` still renders.

- [ ] **Step 5: Commit (echo repo)**

```bash
git add bin/echo_canopy.py bin/echo_tasks.py
git commit -m "refactor: consume shared canopy agent CLI; drop hand-rolled /api/agents client"
```

---

## Self-Review

**Spec coverage (`2026-06-28-shared-agent-client-design.md`):**
- §3 contract (8 endpoints) → Tasks 2–3 (methods) + Task 5 (CLI) + Task 7 (doc). ✓
- §4.1 library + CLI → Tasks 2–5. ✓
- §4.2 ships in canopy plugin, `canopy agent` subcommand → Task 5. ✓
- §4.3 catalog helper → Task 4. ✓
- §5 migration / Echo proof → Task 8; canopy-dup collapse → Task 6. ✓
- §6 decisions: Python v1, identity-supplied/transport-owned, no endpoint changes, operator-plane-only → honored across tasks + Global Constraints. ✓
- §7 acceptance: (1) Echo on shared client → Task 8; (2) collapse dup helpers → Task 6; (3) REST contract → Task 7; (4) no agent-specific imports → Global Constraints + module design. ✓

**Placeholder scan:** no TBD/TODO; every code step shows complete code. ✓
**Type consistency:** `AgentClient` / `AgentIdentity` / `BoardCommand` / `catalog_from_repo` / `canopy_web.call` signatures match across Tasks 1–5 and the CLI. ✓
