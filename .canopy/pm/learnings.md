# Product Management Learnings

Items closed or rejected during PM cycles. Read this before every scout run to avoid re-proposing.

## Closed Items
1. **Keyboard quick-disposition (1/2/3 + auto-advance + Undo) for the agent task board** — closed
   2026-06-18 (user-value). User dispositioned "Close." Don't re-propose keyboard-shortcut /
   triage-hotkey / command-palette-for-the-board UX for the agent workspace.

## Backlog
1. **Dashboard "capability spotlight"** — backlogged 2026-06-21 (capability-discoverability).
   Rotating "Canopy can also… <skill>" card on the homepage linking into the capability catalog.
   Revisit after the catalog page (canopy-web#142) lands. Effort: S.

## Preferences
- **canopy-web UI changes are tracked as spec'd GitHub issues** for a dedicated repo agent to
  implement, NOT built from the cross-repo (echo) PM session. File issues with a concrete file
  list + token/acceptance criteria (see #132 theming, #133 needs-you, #134 activity; and
  #142 capability catalog, #143 workflows view).
- **Design-system contract for any new canopy-web UI (as of PRs #139/#140/#141):** semantic
  design tokens only — no raw `stone-*`/`orange-*`/`zinc-*`/status palette literals; must be
  responsive (work at 375px); must support light + dark. Bake this into every UI issue's
  acceptance criteria. (`SessionSharePage` is the one intentional light-only public viewer.)

## Lessons
- **Showcase/discoverability lens — review the sibling app first, then verify the target's
  metadata shape.** When asked to surface a product's capabilities, (1) read the sibling app
  that already solved it (ace-web `/system`) for a concrete pattern + data-source decision, and
  (2) inventory the target's actual plugin metadata before assuming a 1:1 copy. ace has
  phase/ordinal/artifact frontmatter; canopy has only name+description, so grouping is by
  name-prefix family and the data source must be decided (skill-push vs vendor+reader), not
  assumed. Surfaced 2026-06-21.
