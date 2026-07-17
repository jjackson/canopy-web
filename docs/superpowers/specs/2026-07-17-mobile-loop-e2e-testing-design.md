# End-to-end testing for the canopy-mobile → runner → emdash loop

**Status:** design approved 2026-07-17 (Jonathan — "build all three").

## The problem

The dispatch/continue loop crosses four boundaries: the phone browser → canopy-web
(cloud) → the runner (laptop) → emdash (an Electron app driven over CDP). Today every
piece is tested in isolation — pytest for the server, pytest-with-fakes for the runner,
Playwright for the UI — but **nothing exercises the whole software chain in one pass**, and
the one link that cannot be safely automated is the physical CDP drive into real emdash
(it types into a live session).

The goal: a real, repeatable way to prove the loop works end to end before trusting it live
— three layers, each as real as it can safely be.

## Layer 1 — Automated cross-component E2E (`tests/test_mobile_loop_e2e.py`)

The reusable "does the whole software loop actually work" test. In-process, CI-able, zero
side effects, no emdash, no prod.

**What it exercises, for real:** a live HTTP canopy-web server + the **real runner code**
(`canopy_runner.main.drain_one`, the #270 single-turn primitive) hitting it over real HTTP
with a real Bearer PAT. Only the very edge — `cdp_control`'s Node/CDP subprocess — is
swapped for a recording fake, because that edge is the Electron drive.

**Mechanism:**
- Use pytest-django's `live_server` fixture (a real HTTP server over the WSGI app; the
  harness routes are plain Ninja HTTP, WSGI-compatible — no Channels/WS needed here).
- Seed via the ORM: a `User` (an `@dimagi.com` email so `auto_join_workspaces` applies), a
  `Workspace` (`dimagi`), a `PersonalToken` for that user (the runner's Bearer credential),
  and a `Runner` owned by the user (`workspace=dimagi`, `host=<fixed>`, `capabilities`
  including `projects`, `status=ONLINE`, fresh heartbeat).
- Report one open session through the **real endpoint** (`POST /runners/{id}/sessions`), so
  the display row **and** the continue `SessionLink` exist exactly as the runner would
  create them.
- Enqueue a Continue through the **real endpoint** (`POST /api/harness/turns/` with
  `project` + the `emdash:{task}` `thread_key` in `origin_ref`), so a real QUEUED turn
  exists.
- Build a runner `Config` with `base_url=live_server.url`, `token=<raw PAT>`,
  `executor="cdp"`, a fixed `runner_id`, and a throwaway `emdash_db` path.
- **The recording fake emdash:** monkeypatch, on `canopy_runner.cdp_control`,
  `open_and_send` and `create_task` to append their args to a list and return a plausible
  result; monkeypatch `host_id` to the fixed host (so `reusable_by` matches); monkeypatch
  `canopy_runner.emdash.task_state` to return `"live"` (the reuse path's DB check).
- Call `drain_one(cfg, Client(base_url, token))`.

**Asserts (the whole chain landed):**
1. `open_and_send` was called exactly once with `(task="<the reported task>",
   text="<the dispatched prompt>")` — the prompt reached the exact session, via reuse (not
   `create_task`).
2. The turn transitioned to `done` (read it back via `GET /api/harness/turns/{id}` or the
   ORM).
3. The `SessionLink`'s live hint was re-recorded by the run (`record_session` on the reuse
   branch).

**A second case — a fresh dispatch (no prior session) creates:** dispatch a Continue for a
`thread_key` with no `SessionLink`; assert `create_task` (not `open_and_send`) was called
with the prompt, and the turn is `done`. This pins the create-vs-reuse fork end to end.

**Why in-process + recording fake, not a real subprocess runner + fake CDP server:** the
in-process form runs the identical `drain_one` → `_claim_and_execute` → `execute_turn` code
path over real HTTP against the real server, so everything *except* the Electron drive is
the production path. A subprocess + fake CDP sidecar would add a lot of infra to also
exercise `cdp_control`'s ~30 lines of subprocess plumbing, which its own unit tests already
cover. The seam we stub is exactly the seam that needs a real Mac + real emdash — which is
Layer 3.

## Layer 2 — Live deploy-smoke script (`scripts/qa/smoke_mobile_loop.py`)

The packaged version of the sequence run by hand after each deploy. Sibling to the existing
`scripts/qa/smoke_deployed.py` (same PAT-over-Bearer convention, same `CANOPY_URL`/PAT env
shape). Pure API + stdlib `urllib` (no Playwright — this is the server loop, not the
browser), so it runs anywhere with a token.

**Sequence (against a live/deployed server):**
1. Resolve the caller's runner (`GET /api/harness/runners/`); pick the target runner + its
   workspace. (Fail clearly if the caller has no runner.)
2. Report a small, clearly-synthetic session set to that runner
   (`POST /runners/{id}/sessions`) — e.g. one session `smoke-loop` on a `smoke` project.
3. `GET /api/harness/sessions` → assert the reported session appears (tenant-scoped list).
4. Dispatch a Continue for it (`POST /api/w/{ws}/harness/turns/` with the `emdash:{task}`
   thread_key) → assert a QUEUED turn is created.
5. `resolve-session` for that thread_key → assert `reuse=True` and the right
   `emdash_task_id` (the server half of continue).
6. **Cleanup:** cancel the dispatched turn (`POST /turns/{id}/cancel`), and re-report an
   empty session set to that runner to clear the synthetic rows. Leave prod as found.

Prints a per-step PASS/FAIL summary and exits non-zero on any failure. Idempotent
(idempotency keys derived from a run stamp passed in, since scripts can't call `Date.now()`
in the workflow sense — here it is a normal Python script, so `time.time()` is fine).

**Guard:** the script only ever writes to a runner the **caller owns** and only synthetic
`smoke-*` rows, and it always attempts cleanup — so running it against prod is safe and
self-undoing.

## Layer 3 — Real-emdash validation (`docs/runbooks/mobile-loop-real-emdash.md` + helper)

The final link types into real emdash, so it is human-gated, not a CI test. Deliverables:

- **A runbook** (`docs/runbooks/mobile-loop-real-emdash.md`): the exact steps to prove a
  Continue lands in a real emdash session using `--drain-one` **without** restarting the
  fleet daemon — update the daemon checkout, ensure emdash is running with the CDP port,
  add `projects` to the runner's capabilities via `PATCH /runners/{id}`, dispatch one
  benign prompt from the phone (or the smoke script) into a **scratch** session, run
  `python -m canopy_runner.main --drain-one --config …`, and confirm the prompt appears in
  that emdash session. Explicitly notes the pause sentinel does not block `--drain-one`, so
  the fleet stays otherwise off.
- **A thin helper** (`scripts/qa/dispatch_one_continue.py`): dispatches exactly one Continue
  turn (target repo/agent + thread_key + prompt as args) against a live server and prints
  the turn id — so the runbook's "dispatch one" step is one command, and the human then
  runs `--drain-one` and eyeballs emdash. No emdash automation; the helper stops at the
  dispatch.

## Testing the tests

- Layer 1 is itself run by `uv run pytest tests/test_mobile_loop_e2e.py` — it must pass in
  CI (it uses `live_server`, no external services). Verify like CI: `.env` moved aside.
- Layer 2 / the Layer 3 helper are scripts; smoke-check them by running against the local
  `e2e/backend.sh` server (or prod with a PAT) once, and confirm the PASS summary +
  self-cleanup. They are not unit-tested (they ARE the test), but their pure argument
  parsing / URL building can carry a tiny unit check if non-trivial.

## Non-goals

- Not automating the physical emdash drive (Layer 3 is deliberately manual).
- Not a load/perf harness — this is correctness of the loop.
- Not replacing the existing per-component tests — this sits on top of them.
