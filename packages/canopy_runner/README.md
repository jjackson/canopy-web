# canopy_runner

A laptop-side runner (stdlib-only) that watches for claimed turns on the
canopy-web harness and triggers a visible emdash session by inserting a
queued automation run directly into emdash's local sqlite DB.

## Setup

1. Create a `runner.json` config (see `canopy_runner/config.py` for the full
   field list — `base_url`, `token` (or `@/path/to/token/file`), `runner_id`,
   `emdash_db`, `automation_ids`, `expected_migration_id`).
2. Run once to sanity-check: `python3 -m canopy_runner.main --config ~/.canopy/runner.json --once`
3. Install the launchd plist (or your platform's equivalent) to run the loop
   continuously: `python3 -m canopy_runner.main --config ~/.canopy/runner.json`
   (bare invocation — no subcommand needed; this is equivalent to `run`).

## Commands

- `run` (default when no subcommand is given) — the main watch loop. `--once`
  runs a single iteration (used by cron/tests/launchd health checks).
- `vet` — re-vet the emdash schema pin after an emdash update (see below).

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
- schema changed → refuses to touch the config and stays degraded; before
  editing the pin by hand, re-verify the injection surface (the two writes —
  `INSERT INTO automation_runs`, `UPDATE tasks.type` — plus the columns they
  read) against the emdash source (see the spec §6.1)
