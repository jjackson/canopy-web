# canopy_runner

A laptop-side runner (stdlib-only) that watches for claimed turns on the
canopy-web harness and routes each one to a **visible emdash session**, driving
emdash's real UI over the Chrome DevTools Protocol (create a new session, or
reuse the existing session for that thread). It never writes to emdash's DB —
the only emdash-DB access is two READ-ONLY queries (`emdash.py`: `task_state`,
`list_open_sessions`) that answer "does this session still exist?" (the DOM
can't, because emdash virtualizes the sidebar).

## One-time laptop setup

1. **Launch emdash with its debug port** via the **"Emdash CDP"** Spotlight app
   (or any launcher that passes `--remote-debugging-port=9222`), and install the
   CDP sidecar deps once:
   ```bash
   cd canopy_runner/cdp && npm install
   ```

2. **Pair the runner** with canopy-web:
   ```bash
   curl -X POST {base}/api/harness/runners/ \
     -H "Authorization: Bearer $(cat ~/.claude/canopy/workbench-token)" \
     -H 'Content-Type: application/json' \
     -d '{"name":"jj-mbp","kind":"emdash","capabilities":{"agents":["echo"]}}'
   ```
   — note the returned `id`.

3. **Write `~/.canopy/runner.json`** (see `canopy_runner/config.py` for the
   full field list):
   ```json
   {
     "base_url": "https://labs.connect.dimagi.com/canopy",
     "token": "@~/.claude/canopy/workbench-token",
     "runner_id": "<uuid from step 2>",
     "emdash_db": "/Users/jjackson/Library/Application Support/Emdash/emdash4.db",
     "cdp_port": 9222,
     "mailboxes": {"hal": {"account": "hal@dimagi-ai.com", "client": "canopy"}},
     "inbox_poll_seconds": 300
   }
   ```
   `token` may be a literal value or `@/path/to/token/file` (read + stripped
   at load time). Unknown/legacy keys in the file are ignored, not rejected.

   **Email trigger.** `mailboxes` maps each agent to its gog `{account, client}`;
   the runner polls them every `inbox_poll_seconds` and enqueues an email-origin
   turn per new thread — the runner then reuses that thread's existing emdash
   session (continuity) or spawns a fresh one, rehydrating context. Cross-account:
   the durable link lives in canopy-web, so switching macOS accounts continues the
   thread (fresh local session, rehydrated) rather than losing it.

4. **Sanity-check / smoke test** the config:
   ```bash
   python3 -m canopy_runner.main --config ~/.canopy/runner.json --once
   ```
   → should report `idle` (no claimed turns yet), or `cdp_down` if emdash isn't
   up on its debug port.

5. **Install the launchd job** to run the watch loop continuously:
   ```bash
   cp launchd/com.canopy.runner.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.canopy.runner.plist
   ```

## Commands

- `run` (default when no subcommand is given) — the main watch loop. `--once`
  runs a single iteration (used by cron/tests/launchd health checks);
  `--drain-one` claims + runs exactly one queued turn, then exits.
- `verify-emdash` — read-only check that emdash's DB still has the columns the
  reads depend on (run after an emdash update; see below).

## E2E check

```bash
TOKEN=$(cat ~/.claude/canopy/workbench-token)
```

1. Enqueue a turn:
   ```bash
   curl -X POST {base}/api/harness/turns/ \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"agent_slug":"echo","origin":"manual","idempotency_key":"e2e-'$(date +%s)'"}'
   ```
2. Within seconds: an emdash session appears live in the sidebar (created or
   reused) running `/canopy:drain-turn echo`.
3. Poll the turn until it resolves:
   ```bash
   curl {base}/api/harness/turns/{id} -H "Authorization: Bearer $TOKEN"
   ```
   → `done`.
4. Close the laptop (or quit emdash), enqueue another turn → it stays `queued`
   (the runner reports `cdp_down` and doesn't claim); reopen → it executes.

## After an emdash update

emdash auto-updates. The runner drives emdash over CDP and reads its sqlite DB;
the reads are deliberately **fail-soft** (any sqlite error degrades to
`"unknown"`/`[]` so a read failure is never mistaken for "session gone"). The
cost of that safety is that a *silent* schema drift — emdash renaming a column
`task_state`/`list_open_sessions` name — wouldn't crash; it would quietly break
session reuse (duplicate sessions) and blank the phone's session list, with
nothing in the log.

`verify-emdash` is the guard against exactly that. Run it after an emdash update:

```bash
python3 -m canopy_runner.main verify-emdash --config ~/.canopy/runner.json
```

- all read columns present → exit 0, `✓ … schema intact`. Nothing else to do —
  everything else the runner assumes about emdash (it's installed, its CDP port,
  transcripts) fails LOUDLY and is obvious within a tick.
- a column drifted → exit 1, naming each missing `table.column`. Reconcile
  `task_state()` / `list_open_sessions()` in `canopy_runner/emdash.py` against
  emdash's new schema, then update `READ_SCHEMA` (the allowlist those two reads
  are checked against) to match.
- the DB itself can't be read → exit 2 (bad `emdash_db` path, or emdash not
  installed).
