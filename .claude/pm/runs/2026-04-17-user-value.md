## 2026-04-17 — user-value (first run, PM bootstrap)

Scout lens: **user-value** — what features make canopy-web more useful in Jonathan's daily workflow?

Context at run time: solo user managing 13+ projects. V1 shipped (23 PRs merged). Priority per user: "more features for me to use it."

### Do it
1. **Batch Context + Actions API** — Effort: S — Status: done
   - Branch: emdash/pm-1l6
   - Endpoints: `POST /api/projects/batch-context/`, `POST /api/projects/batch-actions/`
   - Shape: `{"updates": {slug: [entries]}}` → per-slug results with `created`/`errors`
   - Tests: 8 new tests in test_projects.py (cross-project creates, partial success, validation errors, invalid shape, empty updates)
   - Outcome: CLI agents can push context/actions across all 13+ projects in 2 API calls instead of 26+
2. **Workspace Session List + Resume** — Effort: S — Status: done
   - Endpoint: `GET /api/workspace/` with filters for status, collection, limit
   - Frontend: new `/workspaces` page with status filter chips, search by skill/collection, resume links
   - Nav: added "Workspaces" item to AppLayout
   - Tests: 7 new tests in test_workspace_engine.py (empty, filter, ordering, limit, invalid input)
   - Outcome: Workspace sessions are now discoverable. No more losing sessions after navigating away.

### Closed
1. **Context History Timeline** — Why: user closed without explicit reason
   - Disposition: Close
   - Learning: Don't re-propose context history timeline UI for canopy-web. The append-only context model exists, but surfacing history in the dashboard wasn't valued. May have felt like noise or redundant with git log.

### Meta-observations
- **Context bootstrap worked well** — memory files (user_role, workbench_vision, reef_failure) + CLAUDE.md + recent git log gave enough context to skip 2 of the 4 bootstrap questions. Only needed to ask "who uses it" and "what matters most."
- **User feedback mid-proposal was valuable** — the "clarify how we've defined/designed workspace" prompt surfaced a real confusion before committing to Do It. The proposal was correct in substance but needed design grounding before approval.
- **Lint errors in pre-existing code** — saw F401 and F841 on unrelated code when running full `ruff check`. Should scope lint to only touched files going forward to avoid confusing signal.
- **Frontend tests don't exist** — no vitest/jest harness in frontend/. Validation relies on `tsc -b && vite build` only. Future UI changes should note this gap.
- **Batch endpoints validate per-entry** — returning per-slug `errors` list is better than all-or-nothing. Enables CLI agents to log partial failures without retrying the whole batch.
