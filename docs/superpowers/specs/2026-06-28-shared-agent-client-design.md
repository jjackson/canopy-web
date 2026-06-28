# Shared Agent-Client — the framework's first harvested piece

**Status:** Draft for review · **Date:** 2026-06-28 · **Author:** Jonathan + Claude
**Parent:** `2026-06-24-canopy-framework-harvest-design.md` (Wave 0)

> Design spec for one focused piece, not the whole program. Turns into an
> implementation plan next.

---

## 1. Problem

Every agent that talks to canopy-web's agent workspace (`/api/agents/*`) **hand-rolls its
own client**:

- **Echo** — `bin/echo_canopy.py` (register / syncs / work-products / skills) +
  `bin/echo_tasks.py` (tasks sync / commands drain / apply / patch). ~120 lines of PAT
  resolution + REST plumbing.
- **canopy plugin** — duplicates the same PAT-resolve-and-POST helper across **4** scripts
  (`scripts/ddd/auth.py`, `scripts/walkthrough-share/upload.py`,
  `scripts/share-session/upload.py`, `src/orchestrator/shareout.py`).
- **ACE** — its own PAT client to ace-web.

Each is the *same* contract: resolve a PAT (`CANOPY_WEB_PAT` env →
`~/.claude/canopy/workbench-token`), `POST /api/agents/` to upsert identity, then push
syncs / work-products / skills / tasks and drain the command queue. The duplication is the
first, cheapest instance of the framework's whole thesis: **a generic capability every
agent re-implements should live in Canopy once.**

This piece is deliberately first because it is **ACE-independent, fully reversible, and has
a living spec already written in Python** (Echo). We are not inventing a contract; we are
extracting one that three agents already implement.

## 2. Goal & non-goals

**Goal:** one shared agent-client — the framework's `agents` SDK + a thin CLI — that any
agent imports instead of hand-rolling. Echo runs entirely on it (proof); the canopy plugin
and ACE adopt it next.

**Non-goals (YAGNI / out of scope for this piece):**
- No new `/api/agents` endpoints. v1 is exactly the surface Echo already uses.
- **No run lifecycle.** Runs / steps / artifacts / verdicts are W2 / Wave 1 — explicitly
  not here. This client is the *operator-plane* (board, syncs, work-products, skills).
- No frontend changes. The board UI already exists.
- No multi-tenancy changes (Wave 3).

## 3. The contract (extracted from Echo, the most complete consumer)

The client wraps these existing canopy-web endpoints — unchanged:

| Method | Endpoint | Purpose | Echo source |
|---|---|---|---|
| POST | `/api/agents/` | Upsert agent identity (slug/name/email/persona/avatar) | `echo_canopy.py:ensure_agent` |
| POST | `/api/agents/{slug}/syncs/` | Post a manager sync (doc_url, summary, self_grades, period) | `echo_canopy.py sync` |
| POST | `/api/agents/{slug}/work-products/` | Upsert work products (by url) | `echo_canopy.py work` |
| PUT | `/api/agents/{slug}/skills/` | Replace the skill catalog (mirror repo) | `echo_canopy.py skills` |
| POST | `/api/agents/{slug}/tasks/sync` | Non-destructive task upsert | `echo_tasks.py sync` |
| GET | `/api/agents/{slug}/commands?status=pending` | **Drain** queued board actions | `echo_tasks.py commands` |
| POST | `/api/agents/{slug}/commands/{id}/apply` | Mark a command applied (+ result_note) | `echo_tasks.py apply` |
| PATCH | `/api/agents/{slug}/tasks/{id}/` | Store task context (rationale/source/plan) | `echo_tasks.py set` |

**Auth + transport (the duplicated core, centralized once):** PAT resolution ladder
(`arg → CANOPY_WEB_PAT env → ~/.claude/canopy/workbench-token`), base URL
(`CANOPY_WEB_API_URL` → prod default), `Authorization: Bearer`, JSON, uniform error
surfacing.

## 4. Shape

### 4.1 Two layers

1. **`AgentClient` library (Python).** Constructed with an *agent identity* (slug/name/
   email/persona) supplied by the consumer; the client owns auth/transport/serialization.
   ```python
   from canopy_agent import AgentClient
   c = AgentClient(slug="echo", name="Echo", email="echo@dimagi-ai.com", persona="…")
   c.register()
   c.post_sync(doc_url=…, title=…, summary=…, self_grades={"work":"C+"}, period=…)
   c.put_skills(catalog_from_repo("skills/*/SKILL.md"))
   for cmd in c.pending_commands():        # the drain loop
       …do the work…
       c.apply_command(cmd.id, result_note="…")
   ```
2. **Thin CLI** — a **`canopy agent …` subcommand** of the existing `canopy` console-script
   (`[project.scripts] canopy = "orchestrator.cli:main"`), wrapping the library so
   shell-driven skills (Echo's `task-tracker`) keep working with one-liners:
   `canopy agent commands`, `canopy agent apply --id N --note "…"`.

### 4.2 Where it lives & how agents get it

Per the parent doc's stance (**Canopy is the framework; agents depend on Canopy**): the
client ships **in the canopy plugin** (Python helper lib + console-script). Agents that
already depend on Canopy import it; they no longer vendor their own copy.

- **Python agents (Echo, canopy plugin):** import `canopy_agent` directly.
- **ACE (TypeScript):** v1 deliverable is the **documented REST contract** (this doc's §3)
  plus the Python CLI it can shell out to; a native TS port is deferred (ACE already has a
  working client — adopting is value-add, not a blocker).

### 4.3 Skill-catalog helper

The `catalog_from_repo()` logic (glob `skills/*/SKILL.md`, parse frontmatter `name` +
folded `description`, build `{name,description,url,improvement_note}`) is generic and moves
into the client as a helper — every plugin-shaped agent has this exact need.

## 5. Migration / proof

1. Build `AgentClient` + CLI in the canopy plugin; unit-test against the §3 contract.
2. **Re-point Echo onto it:** replace `echo_canopy.py` + `echo_tasks.py` internals with the
   shared client (keep Echo's CLI entry names so `task-tracker`/`canopy-publish` skills are
   untouched); Echo supplies only its identity + the sheet-read (Google) half. Delete the
   duplicated transport/PAT code. **Echo passing is the acceptance test.**
3. Adopt in the canopy plugin: collapse the 4 duplicated PAT helpers onto the shared client.
4. Document the REST contract for ACE; ACE adopts opportunistically.

## 6. Decisions

- **Language v1 = Python**, because the two reference consumers (Echo, canopy plugin) are
  Python and the contract already exists there. REST contract is the real interface; TS is
  a later port, not a v1 requirement.
- **Identity supplied by the consumer, transport owned by the client.** The client knows
  nothing domain-specific — it only knows `/api/agents`. (Keeps it on the generic side of
  the one-way arrow: the framework client never imports an agent's domain.)
- **No endpoint changes.** If a gap appears, it's a separate change to `apps/agents`, not
  smuggled into the client.
- **Operator-plane only.** The run lifecycle is explicitly Wave 1; this client must not grow
  run/step/verdict surface area or it will collide with W2.

## 7. Acceptance

1. Echo runs its full turn (register, sync, work-products, skills PUT, tasks sync, commands
   drain + apply, task patch) entirely through the shared client; `echo_canopy.py` +
   `echo_tasks.py` carry **no** transport/PAT code of their own.
2. The canopy plugin's 4 duplicated PAT helpers are replaced by one import.
3. The §3 REST contract is documented for ACE.
4. The client has zero imports of any agent-specific module (the one-way invariant; covered
   by the Wave 0 import-linter check).

## 8. Resolved seams (were open; now closed)

- **CLI:** a `canopy agent …` subcommand of the existing `canopy` console-script — not a new
  binary.
- **Packaging:** the canopy plugin is already an installable package (`name = "canopy"`,
  `src/` layout, console-script via `orchestrator.cli:main`). The client lands as a new
  module under `src/` (`canopy_agent/` or `orchestrator/agent_client.py`); **no new
  packaging seam needed.** Agents depending on Canopy get it for free.

## 9. Still open (for the plan)

- Exact module path (`src/canopy_agent/` standalone vs `orchestrator/agent_client.py`).
- Whether ACE's TS adoption is in this piece's scope or explicitly deferred (lean: deferred —
  document the REST contract, don't block on a TS port).
