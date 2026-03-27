# Canopy Web

Collaborative web workspace for building reusable AI skills from conversations.

## Architecture

- **Backend:** Django 5 ASGI + uvicorn, PostgreSQL
- **Frontend:** React 19 + Vite + Tailwind CSS 4 + shadcn/ui
- **AI:** Anthropic Claude API via SSE streaming
- **Canopy:** Integrated as git submodule at `./canopy/`

## Development

```bash
# Backend
cp .env.example .env  # Add ANTHROPIC_API_KEY
pip install -e ".[dev]"
python manage.py migrate
python manage.py runserver

# Frontend
cd frontend && npm install && npm run dev

# Both (via honcho)
honcho start -f Procfile.dev

# Docker
docker compose up
```

## Testing

```bash
pytest                           # All backend tests
pytest tests/test_workspace_engine.py -v  # Specific
cd frontend && npm run build     # Frontend type check + build
```

## Key URLs

- `/` — Skill discovery feed
- `/workspace/:id` — Co-authoring workspace
- `/skills/:id` — Skill detail + eval history
- `/leaderboard` — Eval improvement leaderboard
- `/api/` — REST API
- `/admin/` — Django admin
- `/health/` — Health check

## API Endpoints

### Collections
- `POST /api/collections/` — Create collection
- `GET /api/collections/{id}/` — Get collection with sources
- `POST /api/collections/{id}/sources/` — Add source

### Workspace
- `POST /api/workspace/start/{collection_id}/` — Start workspace (SSE stream)
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

## Design Decisions

- APP UI: dense, readable, tables not cards
- Workspace flow: Ingest → AI proposes Approach + Eval → Review/Edit → Test → Publish
- SSE streaming for AI responses (Scout pattern)
- Overwrite-with-history versioning
- No auth in V1 (single-tenant internal tool)
- PostgreSQL on Cloud SQL (GCP deployment)
