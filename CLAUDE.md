# Canopy Web

Collaborative web workspace for building reusable AI skills from conversations.

## Architecture

- **Backend:** Django 5 ASGI + uvicorn, PostgreSQL
- **Frontend:** React 19 + Vite + Tailwind CSS 4 + shadcn/ui
- **AI:** Anthropic Claude API via SSE streaming. Dual backend — direct API key (`AI_BACKEND=api`) or Claude Code CLI subscription (`AI_BACKEND=cli`), switchable at runtime via `/api/ai/switch/`.
- **Runtime adapters:** `apps/skills/adapters/` produces skill artifacts for `web`, `claude_code`, and `open_claw` runtimes.
- **Canopy:** Integrated as git submodule at `./canopy/`
- **Deployment:** GCP Cloud Run + Cloud SQL via `./deploy.sh` (see PR #3 for resources). Production settings in `config/settings/production.py`.

## Development

Backend uses [`uv`](https://docs.astral.sh/uv/) for dependency management (uv.lock is committed). Install uv first if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
# Backend
cp .env.example .env  # Set AI_BACKEND=api + ANTHROPIC_API_KEY, or AI_BACKEND=cli
uv sync --extra dev
uv run python manage.py migrate
uv run python manage.py seed_demo   # optional: 5 demo skills with eval history
uv run python manage.py runserver

# Frontend
cd frontend && npm install && npm run dev

# Both (via honcho)
uv run honcho start -f Procfile.dev

# Docker (backend + frontend + Postgres)
docker compose up

# Deploy to GCP Cloud Run (local). CI also has a manual deploy job —
# trigger it from the Actions tab ("CI / Deploy" → Run workflow).
./deploy.sh                  # runs tests + frontend build first
SKIP_TESTS=1 ./deploy.sh     # bypass test gate (emergencies only)
```

When `AI_BACKEND=cli`, the `claude` binary must be on PATH and authenticated. In Docker, use the headless auth flow at `/settings` (drives `claude setup-token` via PTY; token persists in `CLAUDE_CODE_OAUTH_TOKEN`).

## Testing

```bash
uv run pytest                                    # All backend tests
uv run pytest tests/test_workspace_engine.py -v  # Specific
cd frontend && npm run build                     # Frontend type check + build
```

CI (`.github/workflows/ci.yml`) runs both on every PR and on push to main. Deploy is a separate manual job in the same workflow — trigger it from the Actions tab via "Run workflow"; the deploy step waits for the test jobs to pass before shipping. Walkthrough QA spec at `docs/walkthroughs/canopy-web-demo.yaml` (run via `/walkthrough canopy-web-demo`).

## Key URLs

- `/` — Project workbench (tile grid dashboard)
- `/skills` — Skill discovery feed
- `/workspaces` — Workspace session list (resume in-progress sessions)
- `/new` — New collection / source ingestion flow
- `/workspace/:sessionId` — Co-authoring workspace
- `/skills/:skillId` — Skill detail + eval history
- `/leaderboard` — Eval improvement leaderboard
- `/guide` — Interactive walkthrough ("Try It Now" sample flow + adapter reference)
- `/insights` — Cross-portfolio AI insights feed
- `/settings` — AI backend status, switch backends, headless Claude CLI auth
- `/api/` — REST API
- `/admin/` — Django admin
- `/health/` — Health check

## API Endpoints

### Projects
- `GET /api/projects/` — List projects with latest context
- `POST /api/projects/` — Create project
- `GET /api/projects/{slug}/` — Project detail with full context
- `PATCH /api/projects/{slug}/` — Update project
- `DELETE /api/projects/{slug}/` — Delete project
- `POST /api/projects/{slug}/context/` — Push context entry
- `GET /api/projects/{slug}/context/` — List context entries
- `GET /api/projects/{slug}/context/latest/` — Latest context per type
- `POST /api/projects/seed/` — Bulk seed projects
- `POST /api/projects/batch-context/` — Create context entries across many projects in one request (body: `{updates: {slug: [...]}}`)
- `POST /api/projects/batch-actions/` — Record actions across many projects in one request (body: `{updates: {slug: [...]}}`)
- `POST /api/projects/{slug}/actions/` — Record a skill action
- `GET /api/projects/{slug}/actions/` — List actions (filter: ?skill=name)
- `GET /api/projects/{slug}/actions/summary/` — Latest action per skill

### Insights
- `GET /api/insights/` — List all insights across projects (filter: ?category=ship_gap)
- `DELETE /api/insights/{id}/` — Dismiss an insight

### Collections
- `POST /api/collections/` — Create collection
- `GET /api/collections/{id}/` — Get collection with sources
- `POST /api/collections/{id}/sources/` — Add source

### Workspace
- `GET /api/workspace/` — List workspace sessions (filter: ?status=proposed, ?collection=id, ?limit=50)
- `POST /api/workspace/start/{collection_id}/` — Start workspace (SSE stream)
- `POST /api/workspace/analyze/{collection_id}/` — Run AI analysis to propose approach + eval
- `GET /api/workspace/{session_id}/` — Get workspace state
- `PATCH /api/workspace/{session_id}/edit/` — Edit skill draft
- `POST /api/workspace/{session_id}/publish/` — Publish skill

### Skills
- `GET /api/skills/` — List skills
- `GET /api/skills/{id}/` — Skill detail
- `POST /api/skills/{id}/adapter/` — Generate runtime adapter

### Evals
- `GET /api/evals/{skill_id}/` — Eval suite detail
- `POST /api/evals/{skill_id}/run/` — Run eval
- `GET /api/evals/{skill_id}/history/` — Eval history
- `POST /api/evals/{skill_id}/cases/` — Add eval case
- `PATCH /api/evals/{skill_id}/cases/{case_id}/` — Edit / remove eval case

### AI backend (`apps/common`)
- `GET /api/ai/status/` — Current backend + auth state
- `POST /api/ai/switch/` — Switch between `api` and `cli` at runtime
- `POST /api/ai/auth/start/` — Begin headless Claude CLI login
- `POST /api/ai/auth/complete/` — Submit OAuth code
- `GET /api/ai/auth/poll/` — Poll auth status

## Design Decisions

- APP UI: dense, readable, tables not cards
- Workspace flow: Ingest → AI proposes Approach + Eval → Review/Edit → Test → Publish
- SSE streaming for AI responses (Scout pattern)
- Overwrite-with-history versioning
- No auth in V1 (single-tenant internal tool)
- PostgreSQL on Cloud SQL (GCP deployment)
- Dual AI backend lets users run either against an API key or their own Claude Code subscription

## Reference Docs

- `docs/superpowers/plans/2026-03-27-canopy-web-implementation.md` — Original implementation plan and file structure
- `docs/designs/canopy-web-design.md` — Product design + glossary (open claw, skill, collection, eval suite, workspace session)
- `docs/designs/ceo-plan-conversation-to-agent.md` — CEO review, scope decisions, deferred work
- `docs/walkthroughs/canopy-web-demo.yaml` — Walkthrough QA spec (5 skills, varied scores)
- `TODOS.md` — Deferred V2 work (proactive detection, MCP layer, prompt hardening, OAuth integrations, multi-tenant auth, cowork adapter)
