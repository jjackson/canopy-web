# Runner cascade — availability-aware primary/secondary routing per target

**Status:** design approved 2026-07-20 (Jonathan).

## The problem

Today a runner claims any queued turn whose target (agent or repo) is in its
`capabilities`, gated only by tenant. When two runners declare the same target they
**race**, and the loser-case is silent failure: on 2026-07-20 a phone dispatch to
`canopy-web` was claimed by the cloud runner `cloud-ec2-1`, which was *online* but whose
Claude Code was "not logged in", so the turn failed — while the laptop runner sat idle,
ready. We patched it by hand (removed `canopy-web` from the cloud runner's capabilities),
but that is a blunt, invisible, all-or-nothing lever.

What's actually wanted: **prefer the laptop when it's genuinely usable; fall back to the
cloud only when it isn't — and only for the targets opted into a fallback.**

Two capabilities are missing:
1. **A real "can this runner fire right now" signal.** `Runner.status` distinguishes
   online / offline / degraded, and #277/#278 already made the runner *preflight CDP
   health* (skip claiming + heartbeat `degraded` when emdash's debug port is down). But
   that does not catch "online, CDP reachable, but Claude Code not logged in" — the exact
   failure above — and none of it is visible on the phone.
2. **Ordered, availability-aware routing per target,** instead of a flat capability race.

## The model

**Readiness.** A runner reports two things, and the cascade treats `available = on AND
ready`:
- **on** — heartbeating recently (`Runner.live_status == online`). Already exists.
- **ready** — the runner's self-assessment that it can actually fire a turn, with a short
  `ready_note`. Computed by the runner from: the existing **proactive** `cdp_healthy(:port)`
  preflight (emdash up + debug port open), AND a **reactive** health flag — after a turn
  fails with an auth / execute-health error ("not logged in", CDP send failure), the runner
  reports `ready=false` until a clean run clears it. Auth cannot be probed proactively, so
  the reactive flag is how the cloud-not-logged-in case becomes visible; combined with the
  cascade, the *next* turn falls through to the next runner.

**Cascade.** Routing is governed by an **ordered list of runners per target**, with a
global **default** that every target inherits until overridden:
- A **default cascade** — one ordered runner list (e.g. `[laptop, cloud]`) that applies to
  any agent/repo without its own config. The default's *value* is Jonathan's to set and
  starts conservative (opting a target into a cloud fallback is an explicit override, not
  the fleet-wide default).
- **Per-target overrides** — a specific agent (`echo`) or repo (`canopy-web`) gets its own
  ordered runner list, replacing the default for that target. Future-proofs "some agents
  are cloud-primary": an override can order the cloud runner first.
- A target's **effective cascade** = its override if present, else the default.

**Routing.** When runner R polls to claim a queued turn for target X, R may claim it only
if R is the **highest-ranked *available* runner in X's effective cascade** — i.e. every
runner ranked above R in that cascade is currently *not* available (offline or not-ready).
A lower-ranked runner defers while a higher one is available, and takes over automatically
on its next poll once the higher one goes un-available. This makes the race — and the
cloud-not-logged-in failure — structurally impossible: the cloud only ever claims
`canopy-web` when the laptop is off or not-ready.

## Phasing

Two shippable phases. Phase A is independently useful (you can finally *see* why a runner
isn't firing) and is the prerequisite signal the cascade consumes.

### Phase A — the `ready` signal + mobile runner detail

- **Runner side:** compute `ready` (proactive `cdp_healthy` ∧ reactive execute-health) and
  a `ready_note`; send both in the heartbeat. The reactive flag flips off on an auth /
  execute-health failure in `execute_turn` and clears on the next clean run. Reuses the
  existing `cdp_healthy` preflight (#277/#278) rather than re-adding CDP detection.
- **canopy-web:** `Runner` gains `ready: bool` (default True) + `ready_note: str`; the
  heartbeat endpoint/schema accept and persist them; `RunnerOut` exposes them.
- **Mobile UI:** a **runner detail** view reached by tapping a runner in the Agents tab —
  on/off (live_status), **ready + why** (`ready_note`), kind, host, workspace, capabilities,
  last heartbeat. The list row gains a ready/not-ready indicator alongside the existing
  online dot.

Phase A changes **no routing** — it only adds the signal and its visibility. Safe on its
own; the cascade in Phase B consumes `ready`.

### Phase B — the cascade (default + per-target override) + availability-aware routing

- **Model:** a `RunnerCascade` (the default, `target=null`, and per-target rows) with an
  ordered set of runner references (a `rank` per runner). A migration seeds the **default**
  cascade from the current fleet so behavior is unchanged at rollout, and lifts today's
  ad-hoc `capabilities` into per-target overrides where they diverge from the default.
- **Routing:** `claim_next_turn` consults the target's effective cascade + each runner's
  `available` (on ∧ ready) and enforces the highest-ranked-available rule above. `capabilities`
  stays as the runner's self-declaration (a coarse "willing to do X") and intersects with
  the cascade; the cascade adds the *order* and the *availability gate*. The tenancy rule
  (derive from `paired_by`, #227) is unchanged.
- **Config UI:** set the default cascade (reorder runners); add/override a per-target cascade
  (pick + order runners). "Turn a runner off for X" is just removing it from X's cascade;
  "make the cloud primary for X" is ordering it first — the levers Jonathan asked for fall
  out of one model.

## Testing

- **Phase A:** runner unit tests — `ready` is false when `cdp_healthy` is false; the reactive
  flag flips on a simulated auth-failure and clears on a clean run; the heartbeat carries
  both. canopy-web: the heartbeat persists `ready`/`ready_note`; `RunnerOut` exposes them.
  Playwright: the runner detail view renders on/ready/why; the list shows a not-ready
  indicator (seed a not-ready runner).
- **Phase B:** the L1 mobile-loop E2E extends to prove the cascade — with two seeded runners
  where the primary is not-ready, `claim_next_turn` gives the turn to the secondary, and
  with the primary ready, the secondary defers. A default-vs-override test. The cross-tenant
  and one-executing-turn invariants still hold.
- Verify like CI (`.env` aside); run Playwright locally (CI doesn't).

## Non-goals

- Not remotely *pausing the runner process* — "off for a target" is cascade membership, not
  halting the daemon (the local PAUSED file / launchctl remains that lever).
- Not proactive auth detection — `ready`'s auth half is reactive by design.
- Not load-balancing across equal-rank runners — the cascade is a strict priority order.
