## 2026-06-18 — user-value (agent workspace UI)

Lens applied to the new **agent workspace** (`/agents/echo`) — task board, command queue,
section panels — backed by a deep-research sweep on agent-supervision consoles (Devin/Cognition,
Cursor, GitHub Copilot Workspace, Lindy, Sierra, Factory, LangChain Agent Inbox, Linear,
Superhuman, Anthropic/Google-PAIR human-in-the-loop principles).

### Do it
1. **"Needs you" supervisor inbox** — Effort: M — Status: filed (canopy-web #133)
   - Typed Review/Question/Notify, ranked; "N waiting on you" badge; `/needs-you` API.
   - From: LangChain Agent Inbox + Devin Command Center + Linear My Issues.
2. **Activity & transparency** — Effort: M — Status: filed (canopy-web #134)
   - Render the queue contents + outcomes (`result_note`/`applied_at` already stored, unrendered);
     per-card "last did X / next Y"; grounded `source_url` link. From: Devin/Anthropic/Height.
3. **Theming drift → semantic tokens** — Effort: S–M — Status: filed (canopy-web #132)
   - Section panels (`AgentSyncsSection`/`WorkProducts`/`Skills`/`Overview`/`cards.tsx`) migrate
     off raw stone/orange to `@canopy/workbench` tokens (board + rail already did).

### Backlog (research surfaced; not proposed this cycle)
- Grounded confidence + track record (replace the bare confidence dot) — PAIR + Lee & See.
- Decline-with-reason → written to `contact-memory` (close the training loop) — PAIR + Horvitz.
- Progressive autonomy for *internal* low-stakes task types (outbound stays pinned) — Anthropic/Cursor/Factory.
- Command palette (Cmd+K) showing keybindings inline.
- Syncs as graded drill-to-evidence reports + a grades-over-time trend line — Sierra + Devin Session Insights.
- Link-back stamping + shareable URLs on deliverables/turns — GitHub/Claude + Stripe/Vercel.

### Closed
1. **Keyboard quick-disposition (1/2/3 + auto-advance + Undo)** — Why: user closed it.
   - Learning: don't re-propose keyboard-shortcut / triage-hotkey UX for the agent board.

### Meta-observations
- Deep external research converged tightly with the code-grounded scout — the research's
  "do-first cluster" (#1 inbox, #2 keyboard, #3 honest confidence) matched the grounded findings.
  High signal; worth doing both (research + grounded scout) rather than either alone.
- The strongest finding leveraged **existing-but-unrendered API data** (`result_note`/`applied_at`).
  Lesson 2 (check what already exists) surfaced a feature, not just a guardrail.
- User prefers **spec'd GitHub issues** for canopy-web work (dedicated repo agent) over building
  from the cross-repo (echo) session.
