# canopy_runner

A laptop-side runner (stdlib-only) that watches for claimed turns on the
canopy-web harness and triggers a visible emdash session by inserting a
queued automation run directly into emdash's local sqlite DB.

## One-time laptop setup

1. **Create the emdash automation** (emdash UI → Automations → New), one per
   agent:
   - Name: `canopy — automated turn execution (echo)`
   - Project: the agent's repo; Workspace: repo root or a persistent workspace
   - Schedule: none/disabled (the runner triggers runs; cron stays off)
   - Prompt: `/canopy:drain-turn echo`
   - Provider: claude, terminal (pty) mode

   Copy the automation id:
   ```bash
   sqlite3 ~/Library/Application\ Support/Emdash/emdash4.db "SELECT id,name FROM automations;"
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
     "automation_ids": {"echo": "<automation id from step 1>"},
     "expected_migration_id": 19
   }
   ```
   `token` may be a literal value or `@/path/to/token/file` (read + stripped
   at load time). `expected_migration_id` is the vetted emdash Drizzle
   migration pin — see "After an emdash update" below for how that's kept
   current across emdash releases.

4. **Sanity-check** the config:
   ```bash
   python3 -m canopy_runner.main --config ~/.canopy/runner.json --once
   ```

5. **Install the launchd job** to run the watch loop continuously:
   ```bash
   cp launchd/com.canopy.runner.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.canopy.runner.plist
   ```

6. **Smoke test**:
   ```bash
   python3 -m canopy_runner.main --config ~/.canopy/runner.json --once
   ```
   → should report `idle` (no claimed turns yet).

## Commands

- `run` (default when no subcommand is given) — the main watch loop. `--once`
  runs a single iteration (used by cron/tests/launchd health checks).
- `vet` — re-vet the emdash schema pin after an emdash update (see below).

## E2E check (Phase 0 exit criterion)

1. Enqueue a turn:
   ```bash
   curl -X POST {base}/api/harness/turns/ \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"agent_slug":"echo","origin":"manual","idempotency_key":"e2e-'$(date +%s)'"}'
   ```
2. Within ~2 min: an emdash session appears (Automations panel immediately;
   sidebar after promote) running `/canopy:drain-turn echo`.
3. Poll the turn until it resolves:
   ```bash
   curl {base}/api/harness/turns/{id} -H "Authorization: Bearer $TOKEN"
   ```
   → `done`, with events `queued → claimed → injected → emdash_task →
   running → work_summary → done`.
4. Close the laptop, enqueue another turn → it stays `queued`; reopen the
   laptop → it executes.

## After an emdash update

emdash auto-updates, and the runner refuses to write into its DB whenever
emdash's Drizzle migration id has moved past the vetted pin (`expected_migration_id`
in `runner.json`) — the runner goes `degraded` and stops injecting until
re-vetted. Rather than requiring a full manual re-vet on every emdash release,
`vet` fingerprints the schema of the three tables the adapter actually
touches (`automations`, `automation_runs`, `tasks`) and compares it to the
last-vetted fingerprint stored in `runner.json` (`emdash_fingerprint`):

```bash
python3 -m canopy_runner.main vet --config ~/.canopy/runner.json
```

- schema of the touched tables unchanged → the migration id bump was just
  noise; the pin (`expected_migration_id`) bumps automatically and the
  runner resumes on its next iteration
- schema changed → refuses to touch the config (naming the tables that
  changed) and stays degraded; before editing the pin by hand, re-verify the
  injection surface (the two writes — `INSERT INTO automation_runs`,
  `UPDATE tasks.type` — plus the columns they read) against the emdash
  source (see the spec §6.1)
- no fingerprint baseline stored yet: `vet` adopts one only when the pin
  already matches the actual migration id (i.e. a human vetted at this id).
  If the pin has drifted and there is no baseline, it refuses — verify the
  injection surface by hand, set `expected_migration_id` yourself, then
  re-run `vet` to adopt the fingerprint
