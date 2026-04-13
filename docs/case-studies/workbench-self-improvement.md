# Building the Canopy Workbench: A Self-Improvement Case Study

**Apr 10-13, 2026 | Jonathan Jackson + Claude**

The canopy workbench went from idea to deployed product in three days. Not
because the work was trivial, but because each phase produced artifacts that
made the next phase faster and better. This case study documents that loop --
and why it matters for canopy's thesis that AI systems should compound their
own improvements over time.

---

## Phase 1: Brainstorm -- Killing the dashboard (Apr 10)

The session started with a single conviction: "I want canopy-web to be more
than skill building." The existing app was a skill authoring tool. The vision
was a workbench -- a place where every project in the portfolio has a living,
observable presence.

Six visual directions were explored through companion mockups. Monochrome
palettes were rejected immediately -- "doesn't feel like the future." Generic
dashboard layouts with widget grids were killed next. What survived was Warm
Earth: stone and brown base tones, orange accent, DM Sans typography. Dense,
readable, opinionated.

The critical exercise was the 1-by-1 feature review. Every proposed feature
grouping was examined individually. Does Jonathan actually need a Gantt chart
view? No. A notification center? No. Inline chat per project? No. This
pruning eliminated roughly 40% of the planned surface area before a single
line of code was written.

Two insights emerged that shaped everything after:

- **The API is the real product.** The UI is one consumer. Canopy skills,
  open claws, and future agents are equally important consumers. Every
  feature had to be designed API-first.
- **Dense beats decorative.** Tables, not cards. Data, not chrome. The
  workbench should feel like a tool you use, not a marketing page you admire.

## Phase 2: Build -- Spec to deploy in one session (Apr 10-11)

With scope locked, the build moved fast. A spec became a plan, the plan was
split into independent tasks, and subagents executed them in parallel. The
initial project dashboard landed in PR #8: 8 commits, 7 new files, 21 tests.
It was deployed to GCP Cloud Run the same day.

But shipping wasn't the end -- it was the trigger. Seeing the dashboard live
on Cloud Run revealed what the mockups couldn't. Cards needed to be
full-width. The skills scanner needed to crawl nested directories. A guide
page was missing. Each observation became a follow-up PR, merged and
deployed within hours.

This rapid ship-and-iterate cycle was only possible because the API-first
design meant every change was a small surface. Add a field to the serializer,
update the React component, deploy. No cascading rewrites.

## Phase 3: Walkthrough QA -- The machine catches what eyes miss (Apr 11)

This is where the self-improvement loop first became visible.

The walkthrough skill -- itself a canopy artifact -- was pointed at the live
deployment. It scored Scene 1 at 2/5. The problem: dark project tiles
rendered against a light AppLayout background, making them nearly unreadable.
This was invisible in development because the dev server rendered slightly
differently than the production build.

The fix was applied inline and the walkthrough re-ran. It passed.

But Scene 5 scored 2/5 for a different reason: ALL legacy pages (skills
feed, workspace, settings, leaderboard) still used the old light-on-dark
color scheme. The new Warm Earth palette had been applied to the workbench
but not propagated to the rest of the app. This was a systemic issue across
20 files.

A single subagent dispatch converted all 20 files to the dark theme. The
walkthrough re-ran and scored 4.6/5 average across all scenes.

The key lesson: **the walkthrough skill caught two classes of bugs that
manual testing missed.** The first was a build-environment difference. The
second was a cross-page consistency violation. Both would have shipped to
users without the automated QA pass.

## Phase 4: Design refinement -- User feedback reshapes structure (Apr 12-13)

With the workbench deployed and visually consistent, Jonathan used it for
real work. The feedback was immediate and specific: "now/next/summary are all
the same thing." The expanded card layout had three sections that conveyed
nearly identical information in slightly different formats.

The fix was a restructure: summary (what is this project), actions (what has
happened recently), and details (deep context). Each section had a distinct
purpose and distinct data source.

This phase also added Framer Motion animations for card expansion and
multi-open card support. These weren't cosmetic -- they reduced cognitive
load when comparing projects side by side.

The most consequential addition was the canopy hook integration. A post-run
hook was wired into the canopy skill runner so that every skill execution
automatically recorded an action against the relevant project. This turned
the workbench from a static dashboard into a live activity feed. The
end-to-end chain was verified: run the doc-regen skill, watch the hook fire,
confirm the API records the action, see the UI update.

## Phase 5: Cross-portfolio intelligence -- The loop closes (Apr 13)

The final phase tested whether the workbench could generate its own insights.

First, the chrome-sales daily briefing was examined as a negative example.
That project had tried to generate daily recommendations for a sales team
and failed. The failure mode was instructive: **generic advice kills
actionability.** Recommendations like "consider reviewing your pipeline"
are worse than no recommendations because they train users to ignore the
system.

Armed with that lesson, a portfolio-review skill was built. It pulled data
from GitHub (commit history, PR activity, issue counts) across all 13
tracked projects and generated cross-project insights. Six insights were
produced from real data.

Then the skill evaluated its own output. Rating: 3/5.

The self-evaluation was specific about why each insight fell short. One
insight correctly identified that a project had gone stale but offered no
actionable next step. Another detected a pattern across projects but
attributed causation without evidence. A third was accurate and actionable
but too obvious -- the user already knew it.

This self-evaluation was fed back into the skill, and the prompt was
refined to require evidence chains and specific actions. The improved skill
produced better output on the next run.

This is the loop closing: the workbench generated insights, evaluated them
critically, improved the generator based on the evaluation, and ran again.

---

## The loop

```
Build -> Deploy -> QA -> Fix -> Build more ->
Deploy -> User feedback -> Redesign -> Build ->
Deploy -> Generate insights -> Self-evaluate ->
Improve the evaluator -> Repeat
```

Each phase's output became the next phase's input:

- The **brainstorm** produced a scoped spec that prevented overbuilding.
- The **build** produced a deployed product that the walkthrough could test.
- The **walkthrough** caught visual bugs that humans missed.
- **User feedback** on the live product drove structural redesign.
- The **action tracker** enabled the portfolio-review skill to have data.
- The **portfolio-review skill** generated insights that were then evaluated.
- The **self-evaluation** improved the skill that produced the insights.

No phase was wasted. No artifact was throwaway.

## Principles

**1. Deploy early, evaluate live.**
Static screenshots and dev servers hide real problems. The walkthrough caught
a build-environment rendering difference that only manifested in the
production Cloud Run deployment. Ship first, then assess.

**2. Kill features the user won't use.**
The 1-by-1 feature review eliminated 40% of planned work. Every feature that
survived had a specific user (Jonathan) with a specific use case. "Might be
useful" is not a use case.

**3. Generic advice is worthless.**
The chrome-sales lesson: every recommendation needs an evidence chain and a
specific action. "Consider reviewing X" is noise. "X has had zero commits in
14 days despite 3 open issues; here is the most impactful one to close" is
signal.

**4. The API is the real product.**
Every feature was designed API-first so agents could consume it alongside the
UI. The project context endpoint, the action tracker, the insights feed --
all are REST APIs that the UI renders but that canopy skills call directly.

**5. Self-evaluation drives quality.**
Rating the portfolio-review output at 3/5 and explaining WHY each insight
failed was more valuable than the insights themselves. The evaluation
produced a concrete list of improvements. The insights produced information
the user already had.

## By the numbers

| Metric | Value |
|---|---|
| PRs merged | 17 in 3 days |
| Backend tests | 148+ |
| Projects tracked | 13, with 6 generating real insights |
| Canopy skills created | 3 (activity-summary, portfolio-review, hook wiring) |
| Files converted to dark theme | 20, in one subagent dispatch |
| Walkthrough-driven bugs caught | 2, fixed before any user saw them |

---

## Why this matters for canopy

Canopy's thesis is that AI skills should improve themselves over time. This
workbench build is a small-scale proof of that thesis. The walkthrough skill
improved the product it was testing. The portfolio-review skill evaluated its
own output and used the evaluation to get better. The action tracker created
the data that made the insights possible.

None of these improvements required a separate "improvement phase." They
happened as natural byproducts of building and using the system. That is the
compounding loop canopy is designed to enable -- not improvement as a
scheduled activity, but improvement as a side effect of use.
