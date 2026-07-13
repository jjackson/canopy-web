"""Runner main loop.

One iteration (run_once):
  1. schema guard — drift => heartbeat(degraded) and do nothing else
  2. heartbeat with the active turn ids (renews leases)
  3. follow-up pass over active turns: promote freshly-created emdash tasks
     to sidebar type='task'; drop finished/lost turns from local state
  4. claim at most one new turn; inject the emdash automation run; record
     state; post ledger events

State file makes restarts safe: on boot we re-read it and resume watching
already-injected turns instead of double-injecting.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from pathlib import Path

from . import emdash
from .client import Client, ClientError
from .config import Config

logger = logging.getLogger("canopy_runner")


def _load_state(cfg: Config) -> dict:
    p = Path(cfg.state_path)
    if p.exists():
        return json.loads(p.read_text())
    return {"active": {}}


def _save_state(cfg: Config, state: dict) -> None:
    Path(cfg.state_path).write_text(json.dumps(state, indent=2))


def run_once(cfg: Config, client: Client, now_fn=time.time) -> str:
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

    # 3. follow-up pass: promote new emdash tasks, forget stale entries
    for turn_id, info in list(state["active"].items()):
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
        run_st = emdash.run_status(cfg.emdash_db, info["emdash_run_id"])
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

    emdash_run_id = str(uuid.uuid4())
    emdash.inject_run(
        cfg.emdash_db, automation_id, emdash_run_id, task_name=f"canopy-turn-{agent}"
    )
    state["active"][turn_id] = {
        "emdash_run_id": emdash_run_id,
        "agent": agent,
        "task_promoted": False,
    }
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
