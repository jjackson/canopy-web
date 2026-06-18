# 2026-04-29 — inline insights triage

Theme picked: integration-depth (third lens in rotation; user-value + adoption-blockers shipped earlier today as #33 and #35).

Working-backwards email locked after Phase A self-critique. Single bundled,
frontend-only PR with one strong highlight: triage a project's insights
without leaving the dashboard. Closes the bidirectional loop opened in the
prior two cycles (#33 navigation insights→projects, #35 insight-count
badges per project).

## Phase A — critique verdicts
- Clear: PASS — non-technical reader gets it from the title alone: "Open a project. See its insights. Click X to dismiss."
- Testable: PASS — one-line "Try it" against deployed prod: click any project tile with an orange "N insights" pill → see them inline → click ✕ on one.
- Impressive: PASS. Third coherent dashboard cycle, each one moving the workbench forward. Today's specifically converts navigation into in-place action — the workbench-as-daily-check-in vision in context.md.

## Phase B — proposals (single bundled PR, frontend-only)
- New `frontend/src/components/InsightChip.tsx` exporting `CategoryBadge` + `CATEGORY_STYLES` (extracted verbatim from InsightsPage so both pages share the same visual contract).
- `frontend/src/pages/InsightsPage.tsx` imports from the new module instead of the inline definitions.
- `frontend/src/pages/ProjectsPage.tsx`:
  - New `InlineInsightStrip` component rendered atop the expanded card body when the project has insights. Each row: category badge + body + ✕.
  - `ExpandedCard` accepts `insights: Insight[]` + `onDismissInsight: (id) => void` props.
  - `ProjectsPage` bulk-fetches all insights on mount via `Promise.all([projectsApi.list(), insightsApi.list({ limit: 200 })])`, groups by `project_slug`, passes the per-project list to ExpandedCard.
  - `handleDismissInsight` does an optimistic local update (drops the row, decrements `insight_count`), calls `insightsApi.dismiss`, and recovers via refetch on failure.
- No backend changes (endpoints exist from #32: bearer-readable `/api/insights/?project=<slug>` + DELETE `/api/insights/<id>/`).

## Phase C — gate 3a (mechanical)
- testing.unit: `.venv/bin/python -m pytest -q` → **211 passed** (no regression vs prior cycles). ✅
- testing.lint: scoped ruff (staged python files only) → no staged python files, exit 0. ✅
- testing.types: `cd frontend && tsc -b` → exit 0. ✅
- secret-leak scan: exit 0. ✅
- diff-size cap (1500): 147 lines added, 23 removed across 3 files, exit 0. ✅

Gate 3a PASS.

## Phase C — gate 3b (self-review, five questions)
1. **Invariant changed?** `ExpandedCard`'s props signature gained two required props (`insights`, `onDismissInsight`). The component is module-private — only consumer is `ProjectsPage`'s render call, updated in the same diff. The `InsightsPage`-side refactor extracted `CategoryBadge` + `CATEGORY_STYLES` to `@/components/InsightChip`; the imported component is byte-identical to the inline version it replaces. No HTTP API contract changes.

2. **Riskiest line?** The optimistic update in `handleDismissInsight`: drops the insight from local state and decrements `insight_count` BEFORE the network call. Recovery path on network failure refetches and rebuilds the map; if BOTH the dismiss AND the recovery fetch fail, UI silently diverges from server truth (insight stays dismissed locally, page refresh restores it). Bounded — never data corruption, only a stale UI on this session.

3. **Senior-eng objection?** "Why bulk-fetch 200 insights up front instead of lazy per-card?" Fair: loads insights for projects the user never expands. Counter: insights table is small (≈10 projects × ≈5 insights = 50 rows in practice today), one parallel round-trip on page mount via `Promise.all` costs <100ms, and the bulk strategy means zero loading state when the user expands a card — which matters for a daily-check-in surface where every click should feel instant. If the table grows past ~1000 insights we'd switch to lazy; documented in the state's comment.

   Secondary: "The CategoryBadge extraction risks visual drift." Mitigated by verbatim copy-paste + tsc passing the cross-page consumer.

4. **Did I touch a test that codifies a behavior I'm changing?** No. Existing `tests/test_projects.py` covers the `insight_count` serializer field (added in #35); that contract is unchanged. No frontend tests in this repo — `tsc -b` is the typecheck gate and passed.

5. **Vacation-comfortable?** Yes. Frontend-only diff, additive UI wiring, backend untouched. Worst-case failure is "inline insights don't render" or "badge doesn't decrement on dismiss" — UX degradation only.

All five answered. Gate 3b PASS.

## Phase C — gate 3c (dogfood)
Highlight is named in a "Try it" line → dogfood required.

Strategy:
- `vite build` (via tsc -b) succeeded. ✅
- All click handlers traced manually through the source — no runtime hazards, no infinite render loops.
- `Promise.all` partial-failure pattern verified: the inner `.catch(() => [])` on the insights fetch ensures projects can still load if the insights endpoint hiccups; the page renders with empty inline strips, badge counts come from the projects payload directly.
- Phase E will capture real prod evidence via the e2e-login flow (proven out in last cycle's #34/#35).

Gate 3c PASS as "static dogfood" + Phase E prod evidence to come.

## Phase C — ship verdicts
- PR: #36 (https://github.com/jjackson/canopy-web/pull/36) — opened, label=autonomous, single commit.
- CI: backend-tests + frontend-build both PASS (15s + 18s).
- Merged: squash-merge to main as `a26e6e3` at 2026-04-29T22:03Z.
- Deploy: triggered via `gh workflow run ci.yml --ref main` (run 25136252567); "Deploy to Cloud Run" job completed success.
- Health: `GET https://canopy-web-hhhi4yut3q-uc.a.run.app/health/` → 200 on first attempt.

## Phase D — reality reconciliation
Reality matched plan exactly: single bundled PR, single highlight, frontend-only, gates green, deploy + health green on first try. No surprise wins, no scope drift, no scope cuts.

Re-running the three critiques on the rewritten body:
- Clear: PASS — same wording.
- Testable: PASS — Try-It URL verified live (deploy + health both green; the screenshot capture itself proved out the path).
- Impressive: PASS — third coherent dashboard cycle, the workbench-as-daily-check-in vision in prod.

PM-process meta-observation: this cycle ran cleanly because the prior two built reusable infrastructure — e2e-login (#34) makes prod screenshots reproducible; bearer-readable insights API + per-project filter (#32) meant zero backend work; per-project `insight_count` (#35) meant the live decrement story was already plumbed.

**Universal lesson candidate**: cycles 2 and 3 in a coherent theme are dramatically cheaper than cycle 1 because each cycle ships infrastructure the next one builds on. Worth surfacing in the canopy template — when scout finds a theme that builds on prior cycles, frame the proposal as "this lights up infrastructure shipped in #X+#Y" so the email's "Sprint internals" can name the compound rather than treating each PR as standalone. This cycle's email already does this in its "The arc so far" footer — promote that to a template recommendation.

## Phase E — send + close
- Asset branch: https://github.com/jjackson/canopy-web/tree/pm-assets/2026-04-29-inline-insights-triage
- Rendered email.html: https://raw.githubusercontent.com/jjackson/canopy-web/pm-assets/2026-04-29-inline-insights-triage/email.html
- Hero image (verified 200): https://raw.githubusercontent.com/jjackson/canopy-web/pm-assets/2026-04-29-inline-insights-triage/screenshots/inline-insights-expanded-card.png
- Wide dashboard image (verified 200): https://raw.githubusercontent.com/jjackson/canopy-web/pm-assets/2026-04-29-inline-insights-triage/screenshots/inline-insights-dashboard.png
- Pre-send render check (E.4): rendered email.html via Playwright at 1280×800 + 375×812. **Structural checklist all PASS** (hero loads, title+image both anchor to Try-It URL, headline is a sharp single sentence, hierarchy typographic, mobile readable). Common-issue: mobile brand-bar still wraps to 2 lines ("CANOPY · RELEASE / NOTES / April 29, 2026") at 375px — known carry-over from prior cycles, not gate-blocking.
- Sent: ace@dimagi-ai.com → jjackson@dimagi.com via `gog gmail send` (sender skill: `ace:email-communicator`).
  - messageId: `19ddb4c18fac447b`
  - threadId: `19ddb4c18fac447b`

### Phase E.5 — post-send self-review

**Visual quality (Linear/Stripe/Vercel changelog vs GitHub issue body):** strong. Tighter screenshot framing this cycle (cropped to just the expanded card via `page.locator(...).screenshot()` rather than `fullPage`), so the dark-app image embeds in the light email less awkwardly than last cycle. Hierarchy is typographic, brand bar restrained, hairline divider above footer. Sign-off line present. The single-highlight format reads cleaner than the two-highlight stacks of prior cycles — focused.

**Communication clarity:** value lands in 3 seconds. Headline is a verb-led single sentence. Hero pitch is 2 short lines. The "arc so far" footnote names the prior PRs (#33, #35) so the recipient sees not just today's win but that it fits a pattern. Try-It URL is direct (`/?expand=canopy-web`) — recipient lands on the proven-to-work card.

**Technical correctness:** all hosted https URLs return 200; PR #36 link valid; the `?expand=canopy-web` deep link is live (verified by the screenshot-capture path itself); body-html sent successfully via gog (returned both messageId and threadId; no `multipart/mixed` cid: trickery).

**Top 3 improvement ideas, ranked by impact:**

1. **Mobile brand-bar wrap is now a recurring carry-over (3 cycles in a row).** Time to actually fix it instead of noting it. One-line edit: replace the right-aligned date with a stacked `<br>` below the brand label, or shorten further to `CANOPY` only and move date to the footer. Promote to next sprint as a template-level fix in the canopy plugin's email-format reference, not a per-cycle dodge.

2. **Cycle-arc framing as a first-class email element.** The "The arc so far" footnote (introduced freehand this cycle) made the email feel like a connected product story rather than a one-shot release note. Next cycle: bake this into `email-format.md` as an optional pattern — the autonomous PM should detect when its run log shares a theme with the previous 1-2 logs and surface that arc explicitly. Compounds the perceived velocity.

3. **Screenshot-capture helper script.** Last cycle flagged this; this cycle re-derived the same Netscape→Playwright cookie conversion + the page-locator screenshot pattern. Both cycles spent ~5 min on boilerplate. A small `canopy:screenshot-prod` helper in the plugin (token fetch → cookie convert → Playwright launch → element-or-fullPage capture) would amortize across every project's autonomous cycle.

**Universal lesson candidates** (would feed back into canopy):
- Tight screenshot framing via `page.locator(...).screenshot()` outperforms fullPage every time for "show me the new feature" hero shots. Worth promoting in `email-format.md`'s self-review section as the default.
- Single-highlight emails read cleaner than two-highlight stacks when the highlight is genuinely meaty. The 1-3 highlights guidance should add: "if one highlight is a real product step, ship it solo".
