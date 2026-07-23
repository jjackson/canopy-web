# Chat with a project (not just an agent)

**Date:** 2026-07-23
**Status:** Design — approved for planning

## Problem

The Sessions tab carries two ways to dispatch work:

1. The **`+ chat` picker** (`ChatSessionsPanel`) — "New chat with `<agent>`", which
   creates a `chat.Session` bound to an agent and opens the live chat surface.
2. The **`Composer` widget** (`apps/../components/supervisor/Composer.tsx`) — a quick
   one-shot dispatch box with an **Agent / Repo toggle**: agent mode fires a launchable
   skill or free prompt; repo mode free-types a repo name + picks a workspace and
   enqueues a `harness.Turn` directly.

The Agent/Repo toggle presents agents and repos as two *different kinds* of action.
They aren't: at the execution layer both bottom out in "emdash takes a project name,
makes a worktree, runs a session." The toggle is an artifact of building the surface
for agents first and later realizing it's useful on any project.

The user's actual model: **each agent runs 1:1 as a session in its own GitHub project;
an agent is never run in a foreign project.** So a dispatch target is an agent *or* a
project, never both — which is exactly the shape `harness.Turn` already enforces
(`agent XOR project XOR chat_session`). Nothing in the *data model* is wrong. What's
wrong is the *UI*: the toggle, and the fact that the conversational `+ chat` flow can
only start a chat with an agent, not with a plain project.

## Goal

- **Delete the `Composer` widget** from the Sessions tab.
- **Extend the `+ chat` picker** to list **agents first, then projects** (union across
  all the caller's workspaces). Picking an agent starts an agent chat (unchanged);
  picking a project starts a **project chat** — a live chat session whose turns run in
  that repo's checkout, with no persona.

Non-goals: running an agent in a project that isn't its own; merging the `Agent` and
`Project` tables; any change to the `agent XOR project` turn model; any runner/emdash
change.

## Why this is the right layering

`Agent` and `Project` legitimately differ as product entities (persona, email, skill
catalog, schedules, board, KPI cards vs. context/actions/insights/tiles) and sit in
different architecture tiers (`agents` = framework substrate; `projects` = product).
We keep them separate. We also keep `agent XOR project` — per the 1:1 rule a target is
genuinely one or the other. The only unification is at the **UI/presentation** layer
(one picker instead of a toggle) plus the **execution plumbing** that lets an
agentless chat session name its checkout. The `Session.project` field is a **bare
string** (the emdash project name), mirroring `Turn.project` — **not** a FK to
`projects.Project` — so `apps/chat` never imports product code and the framework/product
boundary holds.

## What already works (no change needed)

- **The runner is project-generic.** `execute_chat_turn` already computes
  `target = agent_slug or project` and calls `cdp_control.create_task(target, ...)`
  (`packages/canopy_runner/.../execute.py`). `resolve_session` / `record_session`
  already accept `project=` and `workspace=`. Once the claim payload carries the
  session's `project` + `workspace`, an agentless project session runs in that repo's
  checkout with **zero runner/emdash changes**.
- **Cross-workspace project listing is free.** `_scoped_project_queryset` on the flat
  mount already unions every workspace the caller belongs to
  (`apps/projects/api.py:129`). The `+ chat` picker calls `/api/projects/slugs/` on the
  flat route and gets the union.

## Changes

### Backend

1. **`apps/chat/models.py`** — add to `Session`:
   ```python
   project = models.CharField(max_length=100, blank=True, default="")
   ```
   A session targets an agent XOR a project (or neither — the existing agentless case).
   Add a `CheckConstraint` `chat_session_not_agent_and_project` forbidding both set at
   once. New migration in `apps/chat/migrations/`.

2. **`apps/chat/schemas.py`** — `SessionCreateIn.project: str | None = None`;
   surface `SessionOut.project: str` (the session list renders it for project chats).

3. **`apps/chat/api.py`** — `create_session`: accept `payload.project`; reject a
   payload with both `agent_slug` and `project` (422, RFC 7807); pass `project` through.
   Update `_out` to include `project`. Workspace is resolved as today from the tenant
   pin (`/api/w/{ws}/chat/`) — the client posts a project chat to the project's own
   workspace route (it knows the workspace from the picker), so no project→workspace
   lookup is needed server-side and `apps/chat` stays free of any `projects` import.

4. **`apps/chat/services.py`** — `create_session(..., project="")`: set it on the row.

5. **`apps/harness/models.py`** — `Turn.target`: in the agentless-session branch, fall
   back to `self.chat_session.project` before the synthetic `session:<hex>` marker.

6. **`apps/harness/schemas.py`** — `TurnOut` claim payload:
   - `project` resolves to `obj.project or (obj.chat_session.project if session else "")`.
   - `resolve_workspace_slug` also returns `obj.chat_session.workspace_id` for a session
     turn (today it returns `None`; the runner needs the workspace to record a
     tenant-gated `SessionLink` for a project session).
   - The project is **not** copied onto the `Turn.project` column — the
     `turn_targets_agent_xor_project_xor_session` constraint forbids it; it is resolved
     from `chat_session.project` at serialization time only.

7. **`apps/projects/api.py` + `schemas.py`** — `ProjectSlugOut` gains `workspace: str`;
   add `"workspace"` to the `.values(...)` in `get_project_slugs`. (The value is
   `workspace_id`, i.e. the workspace slug.)

8. **Regenerate OpenAPI types** — `frontend/src/api/generated.ts`.

### Frontend

9. **`frontend/src/api/chat.ts`** — `CreateSessionInput.project?: string`;
   `createSession` sends `project` in the body. For a project chat the caller passes
   `workspace` (the project's), so the POST targets `/api/w/{ws}/chat/` and the session
   lands in the right tenant.

10. **Project slug client** — add/extend a `listProjectSlugs()` helper returning
    `{ slug, name, workspace }[]` from `/api/projects/slugs/`.

11. **`frontend/src/components/chat/ChatSessionsPanel.tsx`**
    - Load projects alongside agents (flat `/api/projects/slugs/` = cross-workspace).
    - `+ chat` dropdown: **Agents** group (unchanged), a separator, then a **Projects**
      group listing each project + its workspace chip.
    - `startChat` handles both: agent → `createSession({ agentSlug, workspace })`;
      project → `createSession({ project, workspace })`. Navigate via the returned
      `s.workspace` in both cases (`/w/${s.workspace}/chat/${s.id}`).
    - Session-list rows: render an agent session as "with `<agent>`" (unchanged) and a
      project session as its repo name (from `s.project`).

12. **`frontend/src/pages/SupervisorPage.tsx`** — remove the `Composer` import and its
    render in the Sessions tab.

13. **Delete dead code** — `frontend/src/components/supervisor/Composer.tsx`,
    `frontend/src/lib/dispatchPrompt.ts`, and their tests, **after** confirming no other
    importers. `enqueueTurn` in `frontend/src/api/harness.ts` is retained (used by the
    Continue flow and other callers) — verify before removing anything there.

## Tradeoff being accepted

The `Composer`'s one-shot capabilities go away: firing a **launchable skill** from a
dropdown and the **free-prompt / repo quick-dispatch**. Both are recovered inside a
chat — the first message can be `/ace:turn …` or any prompt — which is more consistent
than a parallel dispatch path. This is a deliberate simplification, not a regression to
paper over.

## Known limitation / follow-up (not in scope)

`claim_next_turn` routes session turns to any session-capable runner regardless of
`project` (`Q(chat_session__isnull=False)`). A project chat session could be claimed by
a runner that can't drive that repo, failing at emdash. Gating project sessions to
runners that declare the repo (`runner.project_names()`) is a follow-up, not required
for this change.

## Testing

- **Backend**
  - `apps/chat`: create a project session (project set, agent null); reject both-set
    (422); `SessionOut.project` surfaced; agentless-without-project still allowed.
  - `apps/harness`: `Turn.target` returns `chat_session.project` for an agentless
    session-with-project turn; `TurnOut` surfaces that `project` + the session's
    `workspace_slug`; the XOR check constraint still holds (project not on `Turn.project`).
  - `apps/projects`: `/api/projects/slugs/` includes `workspace`; still cross-workspace
    on the flat mount.
- **Frontend**
  - `ChatSessionsPanel`: renders the Projects group; starting a project chat calls
    `createSession` with `project` + `workspace` and navigates to the returned route.
  - Session list renders a project session by repo name.
