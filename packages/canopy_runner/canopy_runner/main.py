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
import datetime as dt
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

# CDP-down throttle. The CDP executor is otherwise stateless (no state file — see
# _run_once_cdp), but the human-facing "emdash is down" WARNING must fire ONCE per
# outage, not per tick, so this small counter lives at module scope for the loop
# process's lifetime. The per-tick machine signal is the degraded heartbeat (a status
# field, not spam); this gates only the one loud log. Emit it after this many
# consecutive unhealthy ticks so a brief emdash restart (a tick or two) doesn't cry wolf.
CDP_DOWN_SIGNAL_TICKS = 3
_cdp_down_ticks = 0
_cdp_down_signalled = False


def _reset_cdp_health_state() -> None:
    """Clear the CDP-down throttle (on recovery, and between tests)."""
    global _cdp_down_ticks, _cdp_down_signalled
    _cdp_down_ticks = 0
    _cdp_down_signalled = False


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


def _paused_agents(cfg: Config) -> set[str]:
    """Per-agent pause: agent slugs with a `PAUSED.<slug>` sentinel next to the state
    file (dropped by the menu-bar app). Distinct from the global `PAUSED` file, which
    halts everything. A paused agent's inbox is skipped and its queued turns are not
    claimed (the server excludes them), so its work simply waits until resumed."""
    d = Path(cfg.state_path).parent if cfg.state_path else Path.home() / ".canopy"
    try:
        return {p.name[len("PAUSED."):] for p in d.glob("PAUSED.*")}
    except OSError:
        return set()


def _maybe_check_inboxes(cfg: Config, client: Client, now_fn=time.time,
                         paused: set[str] | None = None) -> None:
    """Deterministic email trigger: at most every inbox_poll_seconds, poll each
    configured mailbox and enqueue email-origin turns. Best-effort — a failing inbox
    (auth expired) logs and is skipped, never crashes the loop. Paused agents are
    skipped so no new email turns are enqueued for them."""
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
    cap = getattr(cfg, "inbox_max_threads", 8)
    for agent, box in cfg.mailboxes.items():
        if paused and agent in paused:
            continue
        try:
            res = inbox_mod.check_inbox(
                client, agent, mailbox=box["account"], gog_client=box["client"],
                query=box.get("query", inbox_mod.DEFAULT_QUERY), max_threads=cap,
            )
            n_new, n_seen = len(res["new"]), len(res["seen"])
            # Log EVERY poll, not just ones that enqueue — otherwise a healthy poll that
            # finds nothing new is silent and you can't tell polling is happening at all.
            logger.info("inbox[%s]: polled — %d unread (%d NEW -> session, %d already tracked)",
                        agent, n_new + n_seen, n_new, n_seen)
        except Exception as exc:  # noqa: BLE001 — one bad inbox never kills the loop
            logger.warning("inbox check for %s failed: %s", agent, exc)
    try:
        stamp.write_text(str(now_fn()))
    except OSError:
        pass


def _fire_due_schedules(cfg: Config, client: Client, paused: set[str] | None = None) -> None:
    """Scheduled-turn trigger: sync the schedules this runner may fire, evaluate each
    cron locally, and report any due slot so the server materializes the turn.

    Unthrottled on purpose — unlike the inbox (a subprocess per mailbox), this is one
    HTTP GET, the same cost class as the claim it rides alongside, and the poll IS the
    tick: throttling it would just add latency to every slot. Best-effort — a failing
    sync (server down, token expired) logs and is skipped, never crashes the loop.

    Only reached when NOT globally paused: main()'s pause sentinel `continue`s before
    run_once, so a paused runner never fires (which would queue turns that all execute
    the instant it resumes). Per-agent pause is honored inside check_schedules.
    """
    now = dt.datetime.now(dt.UTC)
    try:
        # Import INSIDE the guard, not above it: canopy_cron is scheduling's ONLY
        # dependency, and a missing/broken one (an un-synced laptop env, a bad
        # install) must disable scheduling alone — not crash claiming and the inbox
        # with it. The import is the most likely failure, so it has to be caught too.
        from . import schedules as schedules_mod
        schedules_mod.check_schedules(client, cfg.runner_id, now=now, paused=frozenset(paused or ()))
    except Exception as exc:  # noqa: BLE001 — scheduling never kills claiming or the inbox
        logger.warning("scheduling unavailable this tick (claiming + inbox continue): %s", exc)


def _claim_and_execute(cfg: Config, client: Client, paused: set) -> str:
    """Claim at most one eligible turn and route it to an emdash session. The shared
    core of both the loop's iteration and the single-turn primitive, so they can't
    drift. Returns reused:/created:/failed:<id> or "idle" when nothing is queued."""
    from . import execute

    try:
        turn = client.claim(cfg.runner_id, paused_agents=sorted(paused))
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


def _run_once_cdp(cfg: Config, client: Client) -> str:
    """CDP executor: preflight emdash's CDP health → heartbeat (with macOS host, for
    reuse ownership) → claim one turn → route it to an emdash session (reuse or create).
    Turns finish synchronously (the runner owns the routing lifecycle; work continues in
    the visible session), so there is no injection state to track or schema to guard.

    Self-heal: the runner CONNECTS to emdash, it never launches it, so a closed/crashed
    emdash (or one launched without --remote-debugging-port) can't run work. If we claimed
    anyway, execute would hit the CDP-connect failure and fail the turn — and a failed turn
    is NOT auto-re-claimed, so one outage burned a turn per hit agent (real incident
    2026-07-17: 11 turns). So we PREFLIGHT: an unhealthy CDP skips the claim for this tick,
    leaving queued turns queued to auto-drain when emdash returns. Inbox + schedule polling
    still run (inbound work keeps ENQUEUING); only the claim is gated."""
    from . import readiness
    from .cdp_control import cdp_healthy, host_id

    global _cdp_down_ticks, _cdp_down_signalled
    healthy = cdp_healthy(port=cfg.cdp_port)
    host = host_id()
    if healthy:
        if _cdp_down_signalled:
            logger.info("emdash CDP healthy again on :%s — resuming claims after %d down tick(s)",
                        cfg.cdp_port, _cdp_down_ticks)
        _reset_cdp_health_state()
        _ready, _rnote = readiness.compute(cfg)
        client.heartbeat(cfg.runner_id, [], host=host, ready=_ready, ready_note=_rnote)
    else:
        _cdp_down_ticks += 1
        # Degraded heartbeat EVERY unhealthy tick — the machine-readable surface signal the
        # control plane + menu-bar app read ("alive but can't execute"). It's a status field,
        # overwritten each tick, so it is not spam.
        client.heartbeat(cfg.runner_id, [], degraded=True,
                         note=f"emdash CDP unreachable on :{cfg.cdp_port} — not claiming",
                         host=host)
        # ...and ONE loud WARNING after sustained downtime (not per tick), for the human log.
        if _cdp_down_ticks >= CDP_DOWN_SIGNAL_TICKS and not _cdp_down_signalled:
            logger.warning(
                "emdash CDP unreachable on 127.0.0.1:%s for %d consecutive ticks — SKIPPING "
                "the claim so queued turns wait instead of failing. Launch emdash with "
                "--remote-debugging-port=%s; the backlog auto-drains when it returns.",
                cfg.cdp_port, _cdp_down_ticks, cfg.cdp_port)
            _cdp_down_signalled = True

    # Report the open emdash sessions the phone can continue. A sqlite read of emdash's
    # DB, not CDP — keep it even while CDP is down. Best-effort: a read or POST failure
    # must never stop the tick.
    try:
        client.report_sessions(cfg.runner_id, emdash.list_open_sessions(cfg.emdash_db))
    except Exception:  # noqa: BLE001
        logger.debug("session report failed (non-fatal)", exc_info=True)
    paused = _paused_agents(cfg)
    # Inbound triggers run whether or not CDP is up, so inbound work still ENQUEUES while
    # emdash is down (it just waits, queued, until emdash is back). Only the claim is gated.
    _maybe_check_inboxes(cfg, client, paused=paused)
    # Fleet-audit review ingestion was removed when Ada moved to Items: approving
    # an Item dispatches its work server-side (in the decide transaction), so there
    # is no resolved review for the runner to poll. DDD findings reviews are applied
    # by the DDD orchestrator, never here.
    _fire_due_schedules(cfg, client, paused=paused)
    if not healthy:
        return "cdp_down"  # nothing claimed -> nothing burned; queued turns stay queued
    return _claim_and_execute(cfg, client, paused)


def drain_one(cfg: Config, client: Client) -> str:
    """Take exactly ONE queued turn, then exit — the "take a single turn" primitive.

    Unlike --once (a full loop iteration), this does NOT poll the inbox or fire
    schedules, so it can only run a turn that is ALREADY queued (dispatch one from the
    composer/API first); it never enqueues or spawns work you didn't ask for. It also
    runs while the daemon is paused — the global PAUSED sentinel gates main()'s loop, not
    this — so you can take one turn with the fleet otherwise off. Per-agent pauses ARE
    honoured (the claim skips a paused agent's turns)."""
    from . import readiness
    from .cdp_control import cdp_healthy, host_id

    if cfg.executor != "cdp":
        return run_once(cfg, client)  # legacy inject path has no targeted primitive
    # Same self-heal as the loop: claiming with emdash down would immediately fail (=burn)
    # the turn. Refuse instead — the caller re-runs once emdash is back on its debug port.
    if not cdp_healthy(port=cfg.cdp_port):
        logger.warning("emdash CDP unreachable on :%s — refusing to claim a turn (it would "
                       "immediately fail). Launch emdash with --remote-debugging-port=%s.",
                       cfg.cdp_port, cfg.cdp_port)
        client.heartbeat(cfg.runner_id, [], degraded=True,
                         note=f"emdash CDP unreachable on :{cfg.cdp_port}", host=host_id())
        return "cdp_down"
    _ready, _rnote = readiness.compute(cfg)
    client.heartbeat(cfg.runner_id, [], host=host_id(), ready=_ready, ready_note=_rnote)
    return _claim_and_execute(cfg, client, _paused_agents(cfg))


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
    parser.add_argument("--drain-one", action="store_true",
                        help="claim + run exactly ONE queued turn, then exit (no inbox poll, "
                             "no schedules; runs even while paused)")

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="run the main loop (default)")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--once", action="store_true", help="single iteration (for cron/tests)")
    run_parser.add_argument("--drain-one", action="store_true",
                            help="claim + run exactly ONE queued turn, then exit")

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
    if getattr(args, "drain_one", False):
        print(drain_one(cfg, client))
        return
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

    # Pause sentinel: the menu-bar app (or `touch ~/.canopy/PAUSED`) drops this file
    # to halt ALL token-spending work instantly without killing the process or fighting
    # launchd's KeepAlive. Paused = we still heartbeat (so the control plane sees the
    # runner alive-but-idle, not dead) but claim nothing, poll no inbox, spawn nothing.
    pause_file = Path(args.config).with_name("PAUSED")
    logger.info("  pause: drop %s to halt work (menu-bar app toggles this); remove to resume",
                pause_file)

    # Liveness heartbeat file: touched EVERY cycle (even idle/paused). The menu-bar app
    # reads its mtime to tell "running" from "stale" — the log alone is a bad signal
    # because idle cycles are deliberately quiet (~15 min between lines), which would
    # otherwise show a healthy idle runner as "stale".
    hb_file = Path(args.config).with_name("heartbeat")

    def _beat() -> None:
        try:
            hb_file.write_text(str(time.time()))
        except OSError:
            pass

    idle_streak = 0
    paused = False
    while True:
        _beat()
        if pause_file.exists():
            if not paused:
                logger.warning("PAUSED — sentinel %s present; skipping all work (no claim, no "
                               "inbox, no tokens). Resume via the menu-bar app or remove the file.",
                               pause_file)
                paused = True
            try:
                client.heartbeat(cfg.runner_id, [], note="paused", host=host)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(cfg.poll_seconds)
            continue
        if paused:
            logger.info("RESUMED — pause sentinel cleared; back to normal polling")
            paused = False
            idle_streak = 0
        try:
            result = run_once(cfg, client)
        except Exception:  # noqa: BLE001 — the loop must survive anything
            logger.exception("run_once crashed; continuing")
            result = "crashed"
        # One scannable line per cycle. Idle is quiet (a heartbeat every ~15 min so the
        # log shows the runner is alive without flooding); everything else logs at INFO.
        # "cdp_down" is quiet like "idle" — the throttled WARNING in _run_once_cdp and the
        # degraded heartbeat already carry the reason, so logging it every tick would be the
        # per-tick spam the preflight is meant to avoid.
        if result in ("idle", "cdp_down"):
            idle_streak += 1
            if idle_streak % max(1, (900 // max(cfg.poll_seconds, 1))) == 0:
                logger.info("cycle: %s (x%d) — runner alive, nothing claimed", result, idle_streak)
        else:
            if idle_streak:
                logger.info("cycle: %s (after %d idle)", result, idle_streak)
            else:
                logger.info("cycle: %s", result)
            idle_streak = 0
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()
