# Project Workbench — Design Spec

**Date:** 2026-04-10
**Status:** Draft
**Scope:** Canopy-web expansion — project registry + workbench homepage

## Problem

Jonathan runs 13+ active projects simultaneously and context-switches constantly. There's no single surface that answers "what was I working on?" or "what's next?" across all projects. Existing tools (GitHub, terminal, canopy session reviews) produce text that's forgettable and unscannable. Meanwhile, CLI agents and open claws have no shared registry of projects — they can't look up where something is deployed or what the current work context is.

## Solution

A **shared project registry** backed by canopy-web's database, exposed via public API, with a dense tile-grid homepage as the primary human view. The API is the real product — it's the shared brain between Jonathan and his AI agents. The UI is one consumer of it.

## What We're Building

### 1. Data Model

**Project** — the registry entry for a repo.

| Field | Type | Notes |
|-------|------|-------|
| name | CharField(100) | Display name |
| slug | SlugField(unique) | URL-safe identifier, e.g. `canopy-web` |
| repo_url | URLField(blank) | GitHub URL |
| deploy_url | URLField(blank) | Production/staging URL |
| visibility | CharField | `public` or `private` (controls guide generation, not access) |
| status | CharField | `active`, `stale`, `archived` |
| created_at | DateTimeField(auto) | |
| updated_at | DateTimeField(auto) | |

**ProjectContext** — a piece of context about a project, written by a human or agent.

| Field | Type | Notes |
|-------|------|-------|
| project | ForeignKey(Project) | |
| context_type | CharField | `current_work`, `next_step`, `summary`, `note`, `insight` |
| content | TextField | Free-text, typically 1-3 sentences |
| source | CharField(100) | Who wrote it: `jonathan`, `canopy:activity-summary`, `ace:orchestrator`, etc. |
| created_at | DateTimeField(auto) | |

Design decisions:
- **No auth** — public API, single-tenant internal tool (matches existing canopy-web pattern).
- **Context is append-only** — new entries don't overwrite old ones. The API returns the latest per type, but history is preserved for the chat panel to reference later.
- **Source field** — tracks provenance so you know if a human or an agent wrote the context. Useful for trust/debugging.
- **No tags, no stack, no language** — Jonathan doesn't care about auto-scanned metadata. If it matters later, it's easy to add fields.

### 2. API

All endpoints follow canopy-web's existing `{success, data, error}` envelope pattern.

**Projects CRUD:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/` | List all projects (ordered by updated_at desc). Returns latest context per type for each project. |
| POST | `/api/projects/` | Create a project. Body: `{name, slug, repo_url?, deploy_url?, visibility?, status?}` |
| GET | `/api/projects/:slug/` | Get project with all context entries (latest per type + full history). |
| PATCH | `/api/projects/:slug/` | Update project fields (name, deploy_url, status, etc.) |
| DELETE | `/api/projects/:slug/` | Delete project and all context. |

**Context (the important part):**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects/:slug/context/` | Push a new context entry. Body: `{context_type, content, source}` |
| GET | `/api/projects/:slug/context/` | List all context entries for a project (newest first). Query param: `?type=current_work` to filter. |
| GET | `/api/projects/:slug/context/latest/` | Get just the latest entry per context_type. Designed for agents that need a quick read. |

**Seed endpoint (convenience):**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects/seed/` | Bulk-create projects from a list. Body: `{projects: [{name, slug, repo_url, ...}]}`. Skips existing slugs. Used for initial setup. |

### 3. Frontend

**New homepage at `/`** — replaces the current skill discovery feed.

Layout: **War Room tile grid** (4 columns on desktop, 2 on tablet, 1 on mobile).

Each tile shows:
- **Project name** (prominent)
- **Deploy badge** — green dot + hostname if deployed, gray "—" if not
- **Current work** — latest `current_work` context, 1-2 lines, truncated
- **Next step** — latest `next_step` context, muted, 1 line
- **Quick links** — GitHub icon → repo, external link icon → live site

Tile behavior:
- Click tile → expands inline (same page, no route change) to show full context history, all links, and a text input to update context
- Inline edit: you can type a new `current_work` or `next_step` directly from the expanded tile, saves via `POST /api/projects/:slug/context/`

**Visual direction:** Warm Earth palette (stone/brown base, orange accent `#fb923c`). DM Sans font. Dense but readable.

**Nav change:** `Projects` (active) | Skills | Leaderboard | Guide | Settings

**Existing pages move:**
- Skill discovery feed moves from `/` to `/skills`
- All other routes unchanged

### 4. Management Command: Seed Projects

`python manage.py seed_projects` — creates the initial 13 projects from the brainstorming session:

| slug | name | repo_url | deploy_url | visibility | status |
|------|------|----------|------------|------------|--------|
| canopy-web | canopy-web | github.com/jjackson/canopy-web | canopy.run.app | public | active |
| ace | ace | github.com/jjackson/ace | — | public | active |
| ace-web | ace-web | github.com/jjackson/ace-web | labs.connect.dimagi.com/ace | public | active |
| commcare-ios | commcare-ios | github.com/jjackson/commcare-ios | — | public | active |
| connect-search | connect-search | github.com/jjackson/connect-search | — | private | active |
| connect-website | connect-website | github.com/jjackson/connect-website | — | public | active |
| canopy | canopy | github.com/jjackson/canopy | — | private | active |
| connect-labs | connect-labs | github.com/jjackson/connect-labs | labs.connect.dimagi.com | public | active |
| chrome-sales | chrome-sales | github.com/jjackson/chrome-sales | — | private | active |
| scout | scout | github.com/jjackson/scout | — | public | active |
| canopy-skills | canopy-skills | github.com/jjackson/canopy-skills | — | public | active |
| reef | reef | github.com/jjackson/reef | — | public | archived |
| commcare-connect | commcare-connect | github.com/jjackson/commcare-connect | — | public | active |

## What We're NOT Building (Yet)

- **Chat panel** — future right-side AI co-pilot. The API is designed so it can read project context, but no UI yet.
- **Canopy skills** (activity-summary, user-guide, best-practice-reviewer) — separate specs. The API is ready for them to push context.
- **Cross-project intelligence in the UI** — the Feed/Briefing views are compelling but need the canopy skills to generate the insights first. The `ProjectContext` model can store these (context_type: `insight`) once the skills exist.
- **Shared design system extraction** — canopy-web and ace-web should converge visually, but that's a separate effort after both have enough UI.
- **Auth/tokens** — public API for now. Add token auth when needed.
- **Detail page** — no `/projects/:slug` route. The expanded tile IS the detail view. Add a detail page later if the tile isn't enough.

## How This Connects to the Bigger Picture

1. **This spec** builds the registry + homepage + API.
2. **Next:** Canopy skill `activity-summary` reads git history, pushes `summary` context entries via the API.
3. **Next:** Canopy skill `user-guide` generates guides for `visibility: public` projects.
4. **Next:** Canopy skill `best-practice-reviewer` compares repos, pushes `insight` context entries.
5. **Later:** Chat panel on the right side, backed by the same API.
6. **Later:** Shared Warm Earth design system extracted for ace-web.

## Success Criteria

- Opening the homepage shows all 13 projects in a dense grid with current context visible
- You can update "current work" and "next step" from the UI in under 5 seconds
- A canopy skill can `POST /api/projects/canopy-web/context/` and the UI reflects it on next load
- An open claw can `GET /api/projects/` and get the full registry with latest context
- The page loads in under 1 second with 13 projects
