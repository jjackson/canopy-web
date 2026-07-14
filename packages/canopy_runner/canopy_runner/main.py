"""Runner main loop.

One iteration (run_once):
  1. schema guard — drift => heartbeat(degraded) and do nothing else
  2. heartbeat with the active turn ids (renews leases)
  3. follow-up pass over active turns: recover any turn whose emdash run
     never made it in (see below), promote freshly-created emdash tasks
     to sidebar type='task', drop finished/lost turns from local state
  4. claim at most one new turn; save state (injected=False); inject the
     emdash automation run; mark injected=True and save again; post ledger
     events

State file makes restarts safe: on boot we re-read it and resume watching
already-injected turns instead of double-injecting.

Crash safety around inject: ``emdash_run_id`` is deterministic — it IS the
turn id (both are uuid strings; `automation_runs.id` is TEXT) — so the
sequence is: save state first (injected=False), then inject_run (idempotent
on run_id), then flip injected=True and save again. Every crash point is
accounted for:
  - crash before the first save: nothing was ever recorded locally; the
    turn's server-side lease expires and the turn goes LOST (terminal) —
    it is NOT re-claimed automatically and needs a manual/API re-enqueue.
  - crash after the first save but before/during inject_run: the follow-up
    pass sees injected=False (or a missing automation_runs row) and calls
    inject_run again — safe, because inject_run is a no-op if the row
    already exists.
  - crash after inject_run but before the second save: same as above, the
    follow-up pass reinjects (idempotent no-op) and just flips the flag.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
from pathlib import Path

from . import emdash
from .client import Client, ClientError
from .config import Config

logger = logging.getLogger("canopy_runner")

# How long we tolerate an emdash run reaching its terminal 'done' state while
# the server-side turn is still claimed/running before we consider the turn
# wedged (skill error / crash that never called /finish) and fail+evict it.
GRACE_SECONDS = 900


def _load_state(cfg: Config) -> dict:
    p = Path(cfg.state_path)
    if not p.exists():
        return {"active": {}}

    corrupt = False
    state: dict = {}
    try:
        state = json.loads(p.read_text())
        if not isinstance(state, dict) or not isinstance(state.get("active"), dict):
            corrupt = True
    except json.JSONDecodeError as exc:
        logger.error("corrupt state file %s: %s", p, exc)
        corrupt = True

    if corrupt:
        corrupt_path = Path(str(p) + ".corrupt")
        try:
            os.replace(p, corrupt_path)
            logger.error("quarantined corrupt state file %s -> %s; starting fresh", p, corrupt_path)
        except OSError as exc:
            logger.error("failed to quarantine corrupt state file %s: %s", p, exc)
        return {"active": {}}

    return state


def _save_state(cfg: Config, state: dict) -> None:
    p = Path(cfg.state_path)
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, p)  # atomic on POSIX — no torn/partial state file ever observed


def _fail_and_evict(cfg: Config, client: Client, state: dict, turn_id: str, note: str) -> str:
    """Fail a turn server-side (best-effort) and drop its state entry.

    Evicting the entry is the load-bearing part: as long as a turn id sits in
    state["active"], every heartbeat renews its lease, so the server can never
    sweep it — a permanently-broken entry would wedge the agent's lane forever.
    """
    try:
        client.fail_turn(turn_id, note)
    except ClientError as exc:
        logger.warning("fail_turn failed for %s: %s", turn_id, exc)
    state["active"].pop(turn_id, None)
    _save_state(cfg, state)
    return f"failed:{turn_id}"


def _maybe_check_inboxes(cfg: Config, client: Client, now_fn=time.time) -> None:
    """Deterministic email trigger: at most every inbox_poll_seconds, poll each
    configured mailbox and enqueue email-origin turns. Best-effort — a failing inbox
    (auth expired) logs and is skipped, never crashes the loop."""
    if not getattr(cfg, "mailboxes", None):
        return
    stamp = Path(cfg.state_path).with_name("inbox-last.txt") if cfg.state_path else Path("inbox-last.txt")
    try:
        last = float(stamp.read_text())
    except (OSError, ValueError):
        last = 0.0
    if now_fn() - last < cfg.inbox_poll_seconds:
        return
    from . import inbox as inbox_mod
    for agent, box in cfg.mailboxes.items():
        try:
            ids = inbox_mod.check_inbox(client, agent, mailbox=box["account"], gog_client=box["client"])
            if ids:
                logger.info("inbox[%s]: enqueued %d thread turn(s)", agent, len(ids))
        except Exception as exc:  # noqa: BLE001 — one bad inbox never kills the loop
            logger.warning("inbox check for %s failed: %s", agent, exc)
    try:
        stamp.write_text(str(now_fn()))
    except OSError:
        pass


def _run_once_cdp(cfg: Config, client: Client) -> str:
    """CDP executor: heartbeat (with macOS host, for reuse ownership) → claim one
    turn → route it to an emdash session (reuse or create). Turns finish synchronously
    (the runner owns the routing lifecycle; work continues in the visible session), so
    there is no injection state to track or schema to guard."""
    from . import execute
    from .cdp_control import host_id

    client.heartbeat(cfg.runner_id, [], host=host_id())
    _maybe_check_inboxes(cfg, client)
    try:
        turn = client.claim(cfg.runner_id)
    except ClientError as exc:
        logger.warning("claim failed: %s", exc)
        return "idle"
    if turn is None:
        return "idle"
    try:
        return execute.execute_turn(cfg, client, cfg.runner_id, turn)
    except Exception as exc:  # noqa: BLE001 — one turn must never kill the loop
        logger.exception("execute_turn crashed for %s", turn.get("id"))
        try:
            client.fail_turn(turn["id"], f"runner execute crashed: {exc}")
        except ClientError:
            pass
        return f"failed:{turn.get('id')}"


def run_once(cfg: Config, client: Client) -> str:
    if cfg.executor == "cdp":
        return _run_once_cdp(cfg, client)

    state = _load_state(cfg)
    active_ids = list(state["active"].keys())

    # 1. schema guard
    try:
        emdash.check_schema(cfg.emdash_db, cfg.expected_migration_id)
    except emdash.SchemaDrift as exc:
        logger.error("schema drift: %s", exc)
        client.heartbeat(cfg.runner_id, active_ids, degraded=True, note=str(exc))
        return "degraded"

    # 2. heartbeat (renews leases for active turns)
    client.heartbeat(cfg.runner_id, active_ids)

    # 3. follow-up pass: evict server-finished turns, recover unfinished
    # injections, promote new emdash tasks, forget stale entries.
    for turn_id, info in list(state["active"].items()):
        try:
            remote = client.get_turn(turn_id)
        except ClientError as exc:
            logger.warning("get_turn failed for %s: %s", turn_id, exc)
            remote = {"status": "running"}
        if remote.get("status") in ("done", "failed", "lost"):
            del state["active"][turn_id]
            _save_state(cfg, state)
            return f"evicted:{turn_id}"

        run_st = emdash.run_status(cfg.emdash_db, info["emdash_run_id"])

        # Recovery: injected=False means we crashed between saving state and
        # calling inject_run; run_st is None (with injected=True) means we
        # crashed after inject_run but the row never actually landed (or the
        # flag-flip save never happened) — either way, reinject (idempotent)
        # and move on. EXCEPT when the task was already promoted: a missing
        # run row then means emdash pruned a finished run, and reinjecting
        # would double-execute the turn — treat it as nothing-to-do.
        if (not info.get("injected") or run_st is None) and not info.get("task_promoted"):
            automation_id = cfg.automation_ids.get(info["agent"])
            if automation_id is None:
                return _fail_and_evict(
                    cfg, client, state, turn_id,
                    f"no emdash automation configured for agent '{info['agent']}'",
                )
            try:
                emdash.inject_run(
                    cfg.emdash_db, automation_id, info["emdash_run_id"],
                    task_name=f"canopy-turn-{info['agent']}",
                )
            except ValueError as exc:
                # automation missing / deleted / disabled — permanent for this
                # turn; fail-and-evict so the heartbeat stops renewing its lease.
                logger.error("reinject failed for %s: %s", turn_id, exc)
                return _fail_and_evict(cfg, client, state, turn_id, str(exc))
            info["injected"] = True
            _save_state(cfg, state)
            return f"reinjected:{turn_id}"

        task = emdash.find_task(cfg.emdash_db, info["emdash_run_id"])
        if task and not info.get("task_promoted"):
            emdash.promote_task(cfg.emdash_db, task["id"])
            info["task_promoted"] = True
            _save_state(cfg, state)
            try:
                client.post_events(turn_id, [{
                    "kind": "status",
                    "payload": {"status": "emdash_task", "task_id": task["id"], "task_name": task["name"]},
                }])
            except ClientError as exc:
                logger.warning("event post failed for %s: %s", turn_id, exc)
            return f"promoted:{task['id']}"
        if run_st in ("failed", "skipped"):
            try:
                client.fail_turn(turn_id, f"emdash run {run_st}")
            except ClientError as exc:
                logger.warning("fail_turn failed for %s: %s", turn_id, exc)
            del state["active"][turn_id]
            _save_state(cfg, state)
            return f"failed:{turn_id}"

        # Finish-less-session wedge: the emdash run reached its terminal
        # 'done' state (checked above: remote wasn't already done/failed/lost)
        # but the claude session never POSTed /finish (skill error, crash) —
        # the server turn is still claimed/running. Left alone, the entry
        # would sit in state["active"] forever, heartbeats would renew its
        # lease forever, and this agent's lane would be blocked permanently.
        # Give it GRACE_SECONDS to close on its own, then fail+evict.
        if run_st == "done":
            completed_seen_at = info.get("completed_seen_at")
            if completed_seen_at is None:
                info["completed_seen_at"] = time.time()
                _save_state(cfg, state)
            elif time.time() - completed_seen_at > GRACE_SECONDS:
                return _fail_and_evict(
                    cfg, client, state, turn_id,
                    "emdash run finished but turn never closed (grace expired)",
                )

    # 4. claim new work (one turn per iteration keeps the loop simple)
    try:
        turn = client.claim(cfg.runner_id)
    except ClientError as exc:
        logger.warning("claim failed: %s", exc)
        return "idle"
    if turn is None:
        return "idle"

    turn_id = turn["id"]
    agent = turn.get("agent_slug", "")
    automation_id = cfg.automation_ids.get(agent)
    if not automation_id:
        try:
            client.fail_turn(turn_id, f"no emdash automation configured for agent '{agent}'")
        except ClientError as exc:
            logger.warning("fail_turn failed: %s", exc)
        return f"failed:{turn_id}"

    # emdash_run_id is deterministic (== turn_id), so a crash between saving
    # state and calling inject_run leaves behind exactly enough information
    # for the follow-up pass to finish the job — see module docstring.
    emdash_run_id = turn_id
    state["active"][turn_id] = {
        "emdash_run_id": emdash_run_id,
        "agent": agent,
        "task_promoted": False,
        "injected": False,
    }
    _save_state(cfg, state)
    try:
        emdash.inject_run(
            cfg.emdash_db, automation_id, emdash_run_id, task_name=f"canopy-turn-{agent}"
        )
    except ValueError as exc:
        # automation missing / deleted / disabled — permanent for this turn;
        # fail-and-evict so the just-saved entry can't keep renewing the lease.
        logger.error("inject failed for %s: %s", turn_id, exc)
        return _fail_and_evict(cfg, client, state, turn_id, str(exc))
    state["active"][turn_id]["injected"] = True
    _save_state(cfg, state)
    try:
        client.post_events(turn_id, [{
            "kind": "status",
            "payload": {"status": "injected", "emdash_run_id": emdash_run_id},
        }])
    except ClientError as exc:
        logger.warning("event post failed: %s", exc)
    return f"injected:{turn_id}"


def _write_config_atomic(cfg_path: Path, raw: dict) -> None:
    """Same tmp + os.replace pattern as _save_state — a crash mid-write must
    never truncate the only config file the runner has."""
    tmp = Path(str(cfg_path) + ".tmp")
    tmp.write_text(json.dumps(raw, indent=2))
    os.replace(tmp, cfg_path)


def vet(cfg_path: Path) -> str:
    """Re-vet the emdash schema pin after an emdash release moves the migration id.

    emdash auto-updates, so a bare migration-id pin would degrade every runner
    on every release. Instead: fingerprint the schema of the three tables the
    adapter actually touches (``emdash.VETTED_TABLES``). Decision table:

    - no stored fingerprint AND pin == actual id → adopt the fingerprint
      (bootstrap: a human vetted at this id), return "unchanged".
    - no stored fingerprint AND pin != actual id → "refused". With no baseline
      there is nothing to verify the schema against, so auto-vetting would be
      zero-verification; a human must re-vet the injection surface, update
      ``expected_migration_id`` by hand, then re-run vet to adopt the
      fingerprint. Config untouched.
    - stored fingerprint differs → "refused" (the changed tables are named).
      Config untouched.
    - stored fingerprint matches → bump the pin ("vetted:<old>-><new>"), or
      "unchanged" if the pin is already current. A backward id move (restored
      DB) still vets but prints a warning.
    - no ``__drizzle_migrations`` table at all (bad ``emdash_db`` path, or the
      DB predates Drizzle) → "refused" with a clear message instead of a raw
      traceback. Config untouched.
    """
    raw = json.loads(Path(cfg_path).read_text())
    db = raw["emdash_db"]
    current_fp = emdash.table_fingerprint(db, emdash.VETTED_TABLES)
    current_tables = emdash.per_table_fingerprints(db, emdash.VETTED_TABLES)
    conn = sqlite3.connect(db)
    try:
        try:
            actual_id = conn.execute("SELECT MAX(id) FROM __drizzle_migrations").fetchone()[0]
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                print(
                    f"no __drizzle_migrations table in {db} — is emdash_db pointed at the"
                    " right file? refusing to vet"
                )
                return "refused"
            raise
    finally:
        conn.close()

    old_id = raw["expected_migration_id"]
    stored_fp = raw.get("emdash_fingerprint", "")

    if not stored_fp:
        if actual_id != old_id:
            print(
                f"no fingerprint baseline and pin {old_id} != actual migration id {actual_id}"
                " — refusing to re-pin; re-vet by hand: verify the injection surface against"
                " the emdash source, update expected_migration_id, then re-run vet to adopt"
                " the fingerprint"
            )
            return "refused"
        # Bootstrap: the human vetted at this id — adopt the fingerprint.
        raw["emdash_fingerprint"] = current_fp
        raw["emdash_table_fingerprints"] = current_tables
        _write_config_atomic(cfg_path, raw)
        return "unchanged"

    if stored_fp != current_fp:
        stored_tables = raw.get("emdash_table_fingerprints", {})
        if stored_tables:
            changed = sorted(
                name
                for name in set(stored_tables) | set(current_tables)
                if stored_tables.get(name) != current_tables.get(name)
            )
        else:
            # Legacy baseline (combined hash only) — can't decompose a sha256,
            # so name the whole vetted set.
            changed = list(emdash.VETTED_TABLES)
        print(f"schema of {changed} changed — refusing to re-pin; re-vet by hand")
        return "refused"

    raw["emdash_fingerprint"] = current_fp
    raw["emdash_table_fingerprints"] = current_tables
    if actual_id == old_id:
        _write_config_atomic(cfg_path, raw)
        return "unchanged"
    if actual_id < old_id:
        print(
            f"warning: migration id moved backward {old_id}->{actual_id}"
            " (restored emdash DB?) — schema fingerprint matches, re-pinning anyway"
        )
    raw["expected_migration_id"] = actual_id
    _write_config_atomic(cfg_path, raw)
    return f"vetted:{old_id}->{actual_id}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="canopy runner (emdash adapter)")
    # Top-level --config/--once keep the bare invocation (no subcommand) working —
    # the launchd plist invokes `-m canopy_runner.main --config ...` with no
    # subcommand, and that must keep behaving like `run`.
    parser.add_argument("--config", help="path to runner.json")
    parser.add_argument("--once", action="store_true", help="single iteration (for cron/tests)")

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="run the main loop (default)")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--once", action="store_true", help="single iteration (for cron/tests)")

    vet_parser = subparsers.add_parser(
        "vet", help="re-vet the emdash schema pin after an emdash update"
    )
    vet_parser.add_argument("--config", required=True)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    command = args.command or "run"

    if command == "vet":
        if not args.config:
            parser.error("vet requires --config")
        print(vet(Path(args.config)))
        return

    # command == "run" (explicit "run" subcommand, or the bare/default invocation)
    if not args.config:
        parser.error("--config is required")
    cfg = Config.load(Path(args.config))
    client = Client(cfg.base_url, cfg.token)
    if args.once:
        print(run_once(cfg, client))
        return

    # Startup banner — the log opens with exactly what this runner is configured to
    # do, so `~/.canopy/runner.log` is self-explaining.
    try:
        from .cdp_control import host_id
        host = host_id()
    except Exception:  # noqa: BLE001
        host = "?"
    logger.info("canopy-runner starting | runner=%s host=%s executor=%s cdp_port=%s",
                cfg.runner_id, host, cfg.executor, cfg.cdp_port)
    logger.info("  poll: claim every %ss | inbox every %ss | mailboxes=%s",
                cfg.poll_seconds, cfg.inbox_poll_seconds,
                ",".join(sorted(getattr(cfg, "mailboxes", {}))) or "(none)")
    logger.info("  COST note: idle cycles + inbox polls are ~free (HTTP only); a 'CREATE' "
                "line = one NEW claude session (tokens), 'REUSE' = none. grep the log for CREATE.")

    idle_streak = 0
    while True:
        try:
            result = run_once(cfg, client)
        except Exception:  # noqa: BLE001 — the loop must survive anything
            logger.exception("run_once crashed; continuing")
            result = "crashed"
        # One scannable line per cycle. Idle is quiet (a heartbeat every ~15 min so the
        # log shows the runner is alive without flooding); everything else logs at INFO.
        if result == "idle":
            idle_streak += 1
            if idle_streak % max(1, (900 // max(cfg.poll_seconds, 1))) == 0:
                logger.info("cycle: idle (x%d) — runner alive, nothing to do", idle_streak)
        else:
            if idle_streak:
                logger.info("cycle: %s (after %d idle)", result, idle_streak)
            else:
                logger.info("cycle: %s", result)
            idle_streak = 0
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()
