# /supervisor as three tabs — Inbox · Sessions · Agents

**Status:** design approved 2026-07-17 (Jonathan).

## The problem

`/supervisor` grew section-by-section into a flat vertical stack of five independent
lists — Dispatch (composer), Open sessions, Waiting on you, Runners, Agents — that you
scroll top to bottom. On a phone that is a long scroll where every glance shows
everything at once instead of one thing well. The three things that actually matter
(the **inbox** of what needs you, the live **sessions** you can continue, the **agents**
you supervise) are buried among each other.

## The goal

Split the one long scroll into **three tabs**, each a focused view: **Inbox · Sessions ·
Agents**. Inbox is the default landing — it is what a push notification drops you into.

This is **pure recomposition**: the section components already exist and do not change.
Only `SupervisorPage` restructures, plus a thin tab shell.

## Design

### Tabs

Built on `canopy-ui`'s existing `Tabs` / `TabsList` / `TabsTrigger` / `TabsContent`
(a `@base-ui/react/tabs` wrapper, exported from `canopy-ui/ui`). Reuse it — do not
hand-roll a tab widget.

| Tab | Contents (existing components, unchanged) | Tab-label badge |
|---|---|---|
| **Inbox** (default) | `WaitingOnYou fleet={fleet}` | the waiting count = `fleet.total_waiting`, shown only when > 0 |
| **Sessions** | `Composer agents={agents}` on top, then `OpenSessions` | none |
| **Agents** | `AgentKpiCard` grid, then `RunnerStatus`, then the setup prompts (`InstallPrompt`, `PushToggle`) | — |

**Only the Inbox tab carries a count badge** (`fleet.total_waiting`, which `SupervisorPage`
already has and already feeds to `setBadge`). A Sessions count is deliberately omitted: the
open-session count lives inside `OpenSessions`'s own self-fetch, and surfacing it on the tab
would mean either duplicating that fetch in `SupervisorPage` or lifting `OpenSessions`'s
state up — both violate "components unchanged" for a non-essential badge. The act-now signal
is the inbox; that is the one badge worth wiring.

### Tab mechanism — URL-synced via a `?tab=` query param

The active tab syncs to a query param, using react-router's `useSearchParams`:

- `/supervisor` → **Inbox** (no param = default; this is what push already targets, so
  push keeps landing on the inbox with no change to the push payload).
- `/supervisor?tab=sessions` → **Sessions**; `/supervisor?tab=agents` → **Agents**.

Rationale over the alternatives:
- **vs. in-component state only:** a query param gives the phone back-button tab
  navigation (switching tabs pushes history), and makes a tab deep-linkable/shareable —
  both real phone expectations.
- **vs. nested routes** (`/supervisor/sessions`): the param keeps the single existing
  route in `router.tsx` (one line, `{ path: '/supervisor', element: <SupervisorPage/> }`)
  — no nested-route restructuring for a three-way in-page switch.

An unknown/garbage `?tab=` value falls back to Inbox (never a blank tab).

### Placement — top tab bar

A horizontal `TabsList` above the content. `/supervisor` has three consumers (phone PWA,
the menubar's WKWebView, the desktop browser); a top bar reads correctly on all three,
where a bottom (thumb) bar would look wrong on desktop. Full-width, evenly-split triggers
so it is thumb-reachable on a phone without being a desktop oddity.

### The odd pieces

- **`InstallPrompt` + `PushToggle`** move into the **Agents** tab (after the KPI cards +
  runners). They are one-time/occasional setup, not daily actions, so they leave the
  header. They already self-hide when not applicable (installed / unsupported), so the
  Agents tab is not cluttered once set up.
- **Header** (the `Supervisor` title + subtitle) stays above the tab bar, slimmed.

### Data loading — unchanged

Keep the existing `Promise.allSettled([listAgents, listRunners, getFleetNeedsYou])` load
in `SupervisorPage`, with its per-band error state (`errs.agents/runners/fleet`) and the
`setBadge(fleet.total_waiting)` effect. All three tabs render from this already-loaded
state, so switching tabs is instant. `OpenSessions` continues to self-fetch (it owns its
own loading/empty/error state). Per-band errors render inside their owning tab.

Because the fleet data loads regardless of the active tab, the Inbox count badge and the
app-icon badge stay correct even while the user is on another tab.

### What does NOT change

`WaitingOnYou`, `Composer`, `OpenSessions`, `AgentKpiCard`, `RunnerStatus` — untouched.
The push trigger, the fleet needs-you API, the sessions API — untouched. This is a layout
change confined to `SupervisorPage.tsx` plus the tab wiring.

## Testing

Playwright (`e2e/supervisor.spec.ts`), at desktop + Pixel 7 widths:
- Default landing (`/supervisor`) shows the **Inbox** tab (`WaitingOnYou`/`waiting-empty`
  visible; the Sessions/Agents content not visible).
- Clicking the **Sessions** tab shows the composer + open sessions; the existing composer
  and open-sessions dispatch tests move to run under that tab (the dispatch behaviour is
  unchanged — the tests just click into the tab first).
- Deep-link `/supervisor?tab=agents` lands on **Agents** (KPI cards + runner status
  visible).
- The Inbox tab shows the waiting-count badge when `total_waiting > 0` (the seed already
  produces waiting items); Sessions and Agents carry no count badge.
- No page-level horizontal scroll at phone width on any tab (the existing invariant test,
  extended to each tab).

Vitest: if any non-trivial pure helper falls out (e.g. resolving the active tab from the
`?tab=` param with the unknown-value fallback), unit-test it per this repo's
logic-in-vitest / behaviour-in-Playwright split. If the tab resolution is a one-line
inline lookup, no separate unit test is warranted.

## Rollout

Additive and safe: the same components, re-laid-out. No API, model, or migration change.
Ships as a normal frontend PR; CI does not run Playwright, so run it locally before merge.
