# SP4 — ace-web as the first cloud-runner consumer

**Status:** Draft for review · **Date:** 2026-07-20 · **Author:** Jonathan + Claude

> Sub-project 4 — the finale of the Wave 4 program
> (`2026-07-16-realtime-chat-cloud-runner-program-design.md`). ace-web stops
> spawning `claude -p` **inside its own Fargate container** and instead routes
> execution through **canopy-web's cloud runner** — becoming tenant #1 of the
> shared substrate. This is the payoff: it validates the framework-harvest thesis
> (ACE → Canopy) with a real second consumer and fixes ace-web's deploy-kills-runs
> pain for free (execution moves off the web tier onto a reclaimable runner tier).
>
> **Deploy-gated + cross-repo (ace-web).** This spec is the plan; it can't be
> end-to-end tested until SP2b is deployed (a live cloud runner) — but the canopy
> side (SP1/SP2a/SP2b) is already built to receive it.

## Where SP1–SP2b leave us
- canopy-web is the hub: `harness` (queue/claim/lease/ledger), `realtime` (live
  push), `chat` (Session/Message/Draft/presence unified on the ledger), and — from
  SP2b — session turns routable to a `kind=cloud` runner that runs real `claude`.
- The seam that makes SP4 non-breaking is already in place: `CHAT_STUB_EXECUTOR`
  flips chat from the inline stub to the cloud runner with **no data-model/API
  change**, and `claim_next_turn` already routes session/agent/project turns to a
  session-capable runner by tenant.

## The change (ace-web side)
ace-web today: human chats → `apps/sessions` `turn_driver` spawns `claude -p` via
`CLIBackend` in-container → streams over ace-web's own Channels WS.

SP4: ace-web enqueues the work to **canopy-web's harness** and observes the result,
instead of executing it locally. Two integration shapes (decide during brainstorm):

- **A — Delegate execution only (recommended first cut).** ace-web keeps its own
  chat UI + `Session`/`Message`, but its `turn_driver` stops calling `CLIBackend`
  and instead `POST`s a `Turn` to canopy-web (`/api/w/{ws}/harness/turns/`, target
  = an ace project/agent or a canopy chat session), then tails the `TurnEvent`
  ledger (`GET …/events?after=seq`, or canopy's realtime `turn.{id}` socket) and
  projects those events into its existing `Message` rows. A canopy **cloud runner**
  executes. ace-web's in-container subprocess pool is retired. Minimal ace-web
  churn; opp-specific concerns (Drive, decisions) stay in ace-web as opaque Turn
  metadata.
- **B — Full delegation to canopy chat.** ace-web's chat becomes a thin skin over
  canopy's `chat` app (Session/Message/Draft live in canopy). Bigger cutover; only
  if we want one chat store. Deferred — A proves the runner path with less risk.

## Auth / tenancy (cross-app)
- ace-web authenticates to canopy-web with a **PAT** (both apps have a PAT model).
  The Turn is enqueued into a canopy workspace ace-web's PAT-user belongs to.
- The cloud runner already pairs with a canopy PAT and claims by tenant; ace-web's
  turns are just more queued work in that tenant. No new canopy auth.
- CORS/WS-origin: canopy-web must allow ace-web's origin for the realtime socket
  (or ace-web polls the events cursor server-side — simpler first cut).

## The credential question (settled by SP2b)
The cloud runner runs claude on a **dedicated `claude setup-token`** (long-lived,
non-rotating, Max subscription), NOT a copy of ace-web's rotating OAuth blob —
which was proven to rotation-conflict. So ace-web and the runner do **not** share a
claude credential; the runner has its own. (See SP2b.)

## Sequencing
1. **SP2b deploy** — a live canopy cloud runner (needs the setup-token). Prove a
   canopy chat turn runs on it end-to-end.
2. **SP4a — execution delegation (shape A):** ace-web `turn_driver` enqueues to
   canopy + projects the ledger back; retire `CLIBackend`. Behind a per-env flag so
   it's a reversible cutover.
3. **SP4b — retire ace-web's in-container claude** entirely once A is proven; the
   deploy-kills-live-runs pain and the ALB-stickiness requirement go away.

## Non-goals / risks
- Not moving ace-web's opp/Drive/decision product logic into canopy (it stays
  product-side, travels as opaque Turn metadata — the framework/product boundary).
- Long autonomous ACE runs (multi-hour) vs. snappy chat: the warm-pool cloud runner
  fits chat; task-per-run isolation for long runs is a later runner option (SP2b
  §deferred), not an SP4 blocker.
- Real end-to-end validation requires the deployed runner + an ace-web deploy — so
  SP4 lands after SP2b is live, and ships behind a reversible flag.
