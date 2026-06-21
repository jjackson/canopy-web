## 2026-06-21 — capability-discoverability (custom lens)

Lens (user-directed): make canopy-web display the **canopy plugin's** capabilities
wholistically ("I can't remember everything canopy can do"). Basis: ace-web's
layout of all of ace's skills + agents.

### Scout evidence
- Gap confirmed: canopy-web has NO surface for the plugin's own capabilities.
  `/skills` = user-authored skills, `/agents` = AI agents (Echo), `/guide` = one
  walkthrough. Plugin surface invisible: **47 skills, 5 agents, 41 commands**.
- ace-web basis: `/system` "System Blueprint" — backend `apps/system/reader.py`
  parses plugin SKILL.md/agent frontmatter → `/api/system/overview` →
  `frontend/src/pages/SystemPage.tsx` + `components/system/*`. 3 tabs
  (skills-by-phase, agents+owned-skills, MCP tools). Plugin = source of truth.
- Canopy differs: frontmatter is only name+description (no phase/ordinal/artifact
  metadata). Natural grouping = name-prefix family (ddd ×14, walkthrough ×4,
  pm ×3, portfolio ×2, session ×3). Plugin NOT vendored in canopy-web (no
  .gitmodules) → data-source is a fork: skill-push to an API (canopy-native,
  recommended) vs vendor-plugin + backend reader (ace parity, heavier).

### Do it (filed as issues per standing preference)
1. **Canopy System catalog page (/system)** — Effort: L — Status: issue filed
   - jjackson/canopy-web#142 (skill-push data source recommended; cross-repo
     publisher in jjackson/canopy noted)
2. **Holistic "workflows" view (capability composition)** — Effort: M/L — Status: issue filed
   - jjackson/canopy-web#143 (depends on #142; curated chains: DDD/PM/walkthrough/portfolio)

### Backlog
1. **Dashboard "capability spotlight"** — Effort: S — Why not now: ship the
   catalog (#142) first; this is a passive-discovery nudge that links into it.
   Revisit after #142 lands. (rotating "canopy can also… <skill>" card on `/`.)

### Closed
(none)

### Meta-observations
- For a "showcase / discoverability" lens, the highest-leverage scout move was
  (a) reviewing the sibling app (ace-web) that already solved it — gave a concrete
  pattern + the data-source decision for free — and (b) inventorying the target's
  actual plugin metadata shape BEFORE assuming a 1:1 copy. ace's phase/artifact
  metadata doesn't exist in canopy, so a naive mirror would have over-built.
- Data-source fork (push vs vendor) is the real architectural decision; surfaced
  it inside the proposal rather than hand-waving "read the plugin."
