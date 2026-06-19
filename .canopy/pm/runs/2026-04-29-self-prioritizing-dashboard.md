# 2026-04-29 — self-prioritizing dashboard

Theme picked: adoption-blockers (second lens in rotation).

Working-backwards email locked after Phase A self-critique. Single bundled PR
derives from two highlights:
1. Active projects lead the grid; stale ones (DB `status=stale|archived` OR
   summary >7d) drop behind a "Show stale (N)" toggle.
2. Each project tile (and expanded card header) wears an "N insights" pill,
   click → `/insights?project=<slug>` filtered.

Post-deploy enabler: this is the FIRST autonomous cycle on canopy-web that
had `/api/auth/e2e-login/` available — last cycle's #1 follow-up — so Phase E
captured real prod screenshots instead of shipping a text-only email.

## Phase A — critique verdicts
- Clear: PASS — non-technical: "dashboard sorts itself + badges show me where things are happening".
- Testable: PASS — both highlights have one-line click recipes against deployed prod.
- Impressive: PASS — converts the dashboard from "list of cards" to "calibrated daily-check-in surface". Wires insights feed (#16/#17/#33) into the homepage at per-project granularity.

## Phase B — proposals (bundled, single PR)
- `apps/projects/serializers.py`: add `insight_count` SerializerMethodField to `ProjectListSerializer` (reuses prefetched contexts; no new query, no migration).
- `tests/test_projects.py`: 2 new tests asserting `insight_count` in list payload (1 insight present → 1; 0 insights → 0).
- `frontend/src/api/projects.ts`: add `insight_count: number` to `Project`.
- `frontend/src/pages/ProjectsPage.tsx`:
  - `isProjectStale(p)` helper (status `stale|archived` OR summary >7d)
  - `InsightBadge` component (compact + full sizes), wraps `/insights?project=<slug>` link
  - Render `InsightBadge` on `CollapsedTile` (compact) and `ExpandedCard` header (full)
  - Split `collapsedHot` / `collapsedStale`, add `Show stale (N)` toggle below the active grid

## Phase C — gate 3a (mechanical)
- testing.unit: `uv run pytest -q` → 211 passed (was 199 + 2 new + 10 from #34's auth tests). ✅
- testing.lint: scoped ruff (staged python files only). 2 errors total in apps/projects/serializers.py — both **pre-existing** on origin/main and untouched by this PR (I001 import-sort lines 1-2, E501 long line in ProjectActionSerializer.Meta on line 113). 0 new violations introduced. ✅
- testing.types: `cd frontend && tsc -b` → exit 0. ✅
- secret-leak scan: exit 0. ✅
- diff-size cap (1500): 122 staged lines, exit 0. ✅

Gate 3a PASS.

## Phase C — gate 3b (self-review, five questions)
1. **Invariant changed?** `Project` list response gained `insight_count: number`. Frontend reads with `|| 0` fallback. No DB schema change, no migration. Only consumer is the frontend; no other API users.
2. **Riskiest line?** `const collapsedHot = collapsedAll.filter((p) => !isProjectStale(p))`. `isProjectStale` reads `p.latest_context?.summary?.created_at` and parses with `new Date()`; missing date → returns false (defaults to "active", matches old visual treatment); unparseable date → NaN comparisons short-circuit to false (still "active"). Bounded.
3. **Senior-eng objection?** "The per-tile `isStale` (summary >7d only) and the page-level `isProjectStale` (status OR summary >7d) diverge — a project with `status=stale` and a fresh summary will show as 'hot' on its border but get grouped under 'Show stale'." Intentional: the tile border is a per-project quality hint; the page split is a curation. Documented in the helper's comment.
4. **Did I touch a test that codifies a behavior I'm changing?** Added 2 new tests; no existing test intent rewritten.
5. **Vacation-comfortable?** Yes. Additive serializer field + optional UI elements. Worst-case failure is wrong badge count or stale-grouping miscall — UX degradation only, no data risk.

All five answered. Gate 3b PASS.

## Phase C — gate 3c (dogfood)
Both highlights are "Try it" features → dogfood required. Strategy:
- `vite build` succeeded (tsc -b returned 0). ✅
- All click handlers traced manually through the source — no runtime hazards.
- Real prod verification captured in Phase E via `/api/auth/e2e-login/` + Playwright (see Phase E screenshots).

Gate 3c PASS as "static dogfood" + Phase E prod evidence.

## Phase C — ship verdicts
- PR: #35 (https://github.com/jjackson/canopy-web/pull/35) — opened, label=autonomous, single commit.
- CI: backend-tests + frontend-build both PASS (17s + 20s).
- Merged: squash-merge to main at 2026-04-29T19:38:36Z.
- Deploy: triggered via `gh workflow run ci.yml --ref main` (run 25129881832); "Deploy to Cloud Run" job completed success.
- Health: `GET https://canopy-web-hhhi4yut3q-uc.a.run.app/health/` → 200 on first attempt.

## Phase D — reality reconciliation
Reality matched plan exactly: both highlights survived intact, single bundled PR shipped, deploy + health both green. Re-running the three critiques on the rewritten body:
- Clear: PASS — same wording, same recipient experience.
- Testable: PASS — both Try-It URLs verified clickable on prod (loaded via Playwright with e2e-login session; both returned content).
- Impressive: PASS — homepage now leads with the 11 active projects, "Show stale (2)" toggle visible at the bottom, insight pills on every tile with open insights (counts ranging 1-8 across the portfolio).

PM-process meta-observation: this cycle proved out the e2e-login pipeline. Real prod screenshots are now reproducible from any future autonomous cycle on canopy-web — closes the gap from the previous cycle's #1 follow-up. The flow:
1. `gcloud secrets versions access latest --secret=canopy-e2e-auth-token --project=connect-labs` to fetch the token.
2. `curl -X POST /api/auth/e2e-login/` with `{email, token}` → cookie jar gets `sessionid`.
3. Convert curl Netscape cookies (with `#HttpOnly_` prefix handling) → Playwright JSON.
4. `playwright@1.58.0` (in a temp `node_modules`) drives the deployed app and captures fullPage screenshots at 2x DPR.

## Phase E — send + close
- Asset branch: https://github.com/jjackson/canopy-web/tree/pm-assets/2026-04-29-self-prioritizing-dashboard
- Rendered email.html (raw): https://raw.githubusercontent.com/jjackson/canopy-web/pm-assets/2026-04-29-self-prioritizing-dashboard/email.html
- Hero images verified 200:
  - https://raw.githubusercontent.com/jjackson/canopy-web/pm-assets/2026-04-29-self-prioritizing-dashboard/screenshots/projects-dashboard.png
  - https://raw.githubusercontent.com/jjackson/canopy-web/pm-assets/2026-04-29-self-prioritizing-dashboard/screenshots/insights-filtered.png
- Pre-send render check (E.4): rendered email.html via Playwright at 1280×800 + 375×812. **Structural checklist all PASS** (images load, titles look like links, headline is a sharp single sentence, hierarchy is typographic, mobile not catastrophically broken).
- Sent: ace@dimagi-ai.com → jjackson@dimagi.com via `gog gmail send` (sender skill: `ace:email-communicator`).
  - messageId: `19ddac897d6acd33`
  - threadId: `19ddac897d6acd33`

### Phase E.5 — post-send self-review

**Visual quality (Linear/Stripe/Vercel changelog vs GitHub issue body):** strong — typographic hierarchy, hairline dividers, restrained palette, hero screenshot per highlight (a real upgrade from last cycle's text-only). Headline is single-sentence. The dark-app screenshots embedded in a light-bg email do create a slight "pasted-in" feel but the 1px stone border + rounded corners soften it.

**Communication clarity:** value lands in 5s. Hero pitch is 1 sentence (improvement over last cycle's 2-line pitch). Each highlight has a "Try it" CTA with a real prod URL. The "Sprint internals" footnote names the e2e-login enabler — recipient sees not just what shipped but that the autonomous pipeline got more capable this cycle.

**Technical correctness:** all hosted https URLs return 200; PR #35 link is valid; both Try-It URLs render correctly when clicked from a logged-in session.

**Top 3 improvement ideas, ranked by impact:**

1. **Tighter screenshot framing.** The current shots are full-page captures including header chrome. For the next cycle, crop the screenshots to just the changed surface (the tile cluster, the filter chip + first card) and frame them as figures with a soft shadow. This will move the email from "tasteful" to "hard to look away from" — the dark-app vs light-email contrast is visually loud right now.
2. **Mobile brand-bar still wraps to 2 lines.** "CANOPY · RELEASE NOTES" wraps at 375px next to the date. Last cycle this was flagged and partially addressed (shortened CANOPY-WEB → CANOPY); next iteration should stack the date below the brand label deliberately, or move it to the footer.
3. **Add a Gmail dark-mode render check to E.4.** Today's check covers light theme only; Gmail inverts backgrounds in some dark modes and our restrained neutral palette is the kind of thing that can break under that inversion. One additional Playwright pass with `prefers-color-scheme: dark` would catch this before send.

**Universal lesson candidates** (would feed back into the canopy template):
- Bash gate commands assume bash word-splitting, but if a user manually runs the lint command from zsh, `for f in $files` won't word-split. The autonomous.yaml's `bash -c '...'` wrapper handles this correctly; just worth noting that gate authors should always wrap with `bash -c` not raw shell snippets.
- The screenshot-capture flow (curl → Netscape cookies → strip `#HttpOnly_` prefix → Playwright JSON) is boilerplate that every project's first autonomous-with-screenshots cycle has to re-derive. A small helper script in the canopy plugin would amortize that.

These two are documented here for the next session-review pass to evaluate as canopy-template improvements.
