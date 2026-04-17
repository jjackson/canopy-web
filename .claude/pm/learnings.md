# Product Management Learnings

Items closed or rejected during PM cycles. Read this before every scout run to avoid re-proposing.

## Closed Items

1. **Context History Timeline in dashboard** (closed 2026-04-17, user-value run)
   - Proposal: Surface all context entries (not just latest) in expanded project cards as a timeline
   - Disposition: Close (no explicit reason given)
   - Don't re-propose: timeline/history views over ProjectContext, "where was I" journal UIs over context entries, context diff views

2. **First-run / onboarding polish** (closed 2026-04-17, adoption-blockers run)
   - Proposals: Empty-state hero on `/` with CTAs; Retry UI + human-readable errors in workspace analysis; Guide tab reorder + inline glossary
   - Disposition: Close (all three)
   - Don't re-propose: first-run empty state UIs, onboarding heroes, user-friendly error recovery UX, guide reorganization, glossary/concept-introduction work. Adoption polish is out of scope until user explicitly signals that stakeholder onboarding is the priority.

## Preferences

1. **Ground proposals in design docs before asking for disposition** — When a proposal touches a core concept (workspace, collection, skill schema), briefly summarize how that concept is currently designed before asking Do/Backlog/Close. User's clarification request ("can you clarify how we have defined/designed workspace?") showed this was needed. Applies especially when proposing UX changes to core primitives.

2. **Favor narrow, verifiable fixes over broad UX improvement** — User approves specific edge-case fixes with clear repro and test coverage. He closes broad UX polish proposals (empty states, onboarding, error messages, documentation reorgs). Pattern observed: user-value run shipped 2/3 narrow API improvements; adoption-blockers run shipped only 1/4 — the narrow OAuth fix, not the three UX polish proposals.
   - **Why:** Current phase is "more features for me to use it" (solo user). Stakeholder adoption isn't the current priority despite the presence of adoption-capable infrastructure (OAuth, deploy, etc.).
   - **How to apply:** Future scouts should weight proposals toward narrow, verifiable, high-signal fixes. Avoid proposing broad UX/polish/onboarding work until the user explicitly signals a phase change. If multiple proposals are tempting, drop the broad-polish ones and keep the specific-fix ones.

3. **Verify scout claims before proposing** — Adoption-blockers scout claimed "no feedback after non-Dimagi OAuth" but the server-side adapter + template already existed. Future scouts should grep for existing adapters/templates/middleware before claiming absence of behavior.
