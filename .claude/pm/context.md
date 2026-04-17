# Canopy Web — Product Context

## What It Is
Collaborative web workspace for building reusable AI skills from conversations — the web layer on top of the canopy ecosystem.

## Who Uses It
- **Primary user**: Jonathan Jackson (solo) — builds, tests, and uses the tool daily to manage 13+ projects and extract skills from AI conversations
- **Usage pattern**: Daily workbench for project context tracking, skill authoring, and eval management. CLI agents and open claws also consume the API.
- **Future users**: Non-technical stakeholders (Neal, Matt, Beth) for demo/review, eventually broader team adoption

## What Matters Most
1. More features that make canopy-web useful in Jonathan's daily workflow
2. API-first design so CLI agents and open claws can consume the platform programmatically
3. Evals co-authored with skills (the reef lesson — skills without evals are unverifiable)

## Tech Stack
- Django 5 ASGI + uvicorn, PostgreSQL, React 19 + Vite + Tailwind 4 + shadcn/ui
- Anthropic Claude API via SSE streaming (dual backend: API key or CLI subscription)
- Runtime adapters for web, claude_code, open_claw
- GCP Cloud Run + Cloud SQL deployment

## Current State
V1 shipped: project workbench dashboard, skill discovery, workspace co-authoring flow, eval system, insights feed, Google OAuth, interactive guide. 23 PRs merged. Deployed to GCP Cloud Run. Solo usage — no other users yet.

## Known Considerations
- Reef failed because evals were deferred — canopy-web must keep skill+eval tightly coupled
- API is the real product; UI is one consumer. Design API-first for agent consumption.
- Warm Earth design system (stone/brown base, orange accent, DM Sans) shared with ace-web
- V1 has no prompt injection hardening — acceptable for single-tenant, must fix before external use
