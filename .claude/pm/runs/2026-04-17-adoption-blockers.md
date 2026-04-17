## 2026-04-17 — adoption-blockers

Scout lens: **adoption-blockers** — what would make a new user (Neal, Matt, Beth) walk away from the deployed app?

Context at run time: deploy of user-value cycle just succeeded. Stakeholders could open canopy.dimagi-ai.com at any time.

### Do it
1. **Non-Dimagi OAuth failure message** — Effort: S — Status: done
   - Branch: emdash/pm-1l6
   - The scout claimed there was NO feedback after non-Dimagi login. That was wrong — a server-side adapter (`apps/common/auth_adapter.py`) + template (`templates/auth/domain_rejected.html`) already existed.
   - Actual fix: improved the template copy — clearer explanation of why they're rejected, instructions to sign out of Google first (links to accounts.google.com/Logout), and a mailto:jjackson@dimagi.com contact for access requests.
   - Test added: `test_rejection_page_shows_email_domain_and_contact` asserts the rendered HTML contains all four elements.

### Closed
1. **First-run homepage + onboarding hero** — Why: user declined
   - Disposition: Close
   - Learning: Don't propose broad first-run/empty-state/onboarding polish work for canopy-web right now. User is still building for himself; stakeholder adoption isn't the current phase.
2. **Retry + human-readable errors in workspace analysis** — Why: user declined
   - Disposition: Close
   - Learning: Don't propose general error-handling UX polish. Specific bug fixes with clear repro are OK; speculative error-path improvements aren't.
3. **Guide reorder + inline glossary** — Why: user declined
   - Disposition: Close
   - Learning: Don't propose documentation/glossary/tab-reorder changes to canopy-web's Guide page.

### Meta-observations
- **User approves narrow, specific, verifiable fixes; closes broad UX polish.** Of 4 adoption-blocker proposals, 3 closures and 1 do-it. The one he took was the narrow edge-case (non-Dimagi OAuth). The three closures were all "improve UX for hypothetical new users." This is consistent with his self-declared priority: "more features for me to use it" (user-value run). Adoption polish is premature — adjust future scouts to focus on narrow, verifiable fixes until the user signals broader adoption is in scope.
- **Scout claims should be verified.** Scout said "no feedback after non-Dimagi OAuth" but the adapter + template already existed. Always grep for adapter patterns and templates before claiming absence of behavior.
- **Adoption-blockers lens may be too early** — might want to skip this lens in rotation until stakeholder adoption is prioritized. Next rotation should go to integration-depth.
