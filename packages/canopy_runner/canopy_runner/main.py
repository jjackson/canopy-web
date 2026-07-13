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
import time
from pathlib import Path

from . import emdash
from .client import Client, ClientError
from .config import Config

logger = logging.getLogger("canopy_runner")


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


def run_once(cfg: Config, client: Client) -> str:
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

    # 3. follow-up pass: recover unfinished injections, promote new emdash
    # tasks, forget stale entries. (A future task adds success-path eviction
    # of finished turns here via get_turn — this loop is structured so that
    # check can slot in at the top, before the recovery check below.)
    for turn_id, info in list(state["active"].items()):
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


def main() -> None:
    parser = argparse.ArgumentParser(description="canopy runner (emdash adapter)")
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true", help="single iteration (for cron/tests)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = Config.load(Path(args.config))
    client = Client(cfg.base_url, cfg.token)
    if args.once:
        print(run_once(cfg, client))
        return
    while True:
        try:
            run_once(cfg, client)
        except Exception:  # noqa: BLE001 — the loop must survive anything
            logger.exception("run_once crashed; continuing")
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    main()
