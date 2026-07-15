"""CDP execution — the sanctioned path (supersedes DB injection + app patching).

The runner owns the harness Turn *routing* lifecycle (start → done) and drives
emdash over CDP to either REUSE an existing session (continuity) or CREATE a fresh
one (rehydrating context from the durable SessionLink). The WORK then happens in
the visible, intervenable emdash session.

Session reuse is verify-before-reuse: the control plane only proposes reuse when
THIS runner's macOS host owns the live session; if the emdash task turns out to be
gone (archived, or belongs to the other account), we fall back to create+rehydrate.
"""
from __future__ import annotations

import datetime as dt
import logging
import re

from . import cdp_control

logger = logging.getLogger("canopy_runner.execute")


def _thread_key(turn: dict) -> str:
    ref = turn.get("origin_ref") or {}
    return ref.get("thread_key") or ref.get("thread_id") or f"{turn['agent_slug']}:main"


def _slug(text: str, n: int = 28) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:n].strip("-")


def _task_name(agent: str, turn: dict, now=None) -> str:
    """A HUMAN-READABLE, per-thread-UNIQUE emdash task name: agent + subject slug +
    a short thread discriminator + MMDD-HHMM, e.g. 'hal-security-alert-6355-0714-1514'.
    The discriminator (last chars of the thread key) is what stops two DIFFERENT threads
    with the same subject in the same minute from colliding onto one name. Recorded in the
    SessionLink, so reuse opens this exact name — legible, not a bare hash."""
    stamp = (now or dt.datetime.now()).strftime("%m%d-%H%M")
    ref = turn.get("origin_ref") or {}
    label = _slug(ref.get("subject") or "") or _slug(turn.get("origin") or "")
    disc = re.sub(r"[^a-z0-9]", "", _thread_key(turn).lower())[-4:]
    bits = [agent] + ([label] if label else []) + [b for b in (disc, stamp) if b]
    return "-".join(bits)


def execute_turn(cfg, client, runner_id: str, turn: dict) -> str:
    """Route one claimed turn to an emdash session (reuse or create). Returns a short
    action string: reused:<id> | created:<id>:<task> | failed:<id>."""
    turn_id = turn["id"]
    agent = turn["agent_slug"]
    ref = turn.get("origin_ref") or {}
    thread_key = _thread_key(turn)
    # The prompt is a clean command — the agent's own /turn command does all the work.
    # Default (board turns with no prompt): a full turn. drain-turn is retired.
    work_prompt = turn.get("prompt") or "/turn"

    plan = client.resolve_session(runner_id, agent, thread_key)
    client.start(turn_id)

    # --- reuse the existing session, if the control plane says this runner owns it ---
    if plan.get("reuse") and plan.get("emdash_task_id"):
        task = plan["emdash_task_id"]
        try:
            cdp_control.open_and_send(task, work_prompt, port=cfg.cdp_port)
        except cdp_control.CDPError as exc:
            if "TASK_NOT_FOUND" not in str(exc):
                # The task EXISTS but the send glitched (transient). Creating a fresh
                # session here would DUPLICATE the live one and orphan its context —
                # the exact bug that spawned two Hal sessions. Fail the turn instead
                # (it can be retried); never duplicate.
                logger.error("reuse send FAILED on existing '%s' (agent=%s): %s — NOT creating "
                             "a duplicate; failing the turn for retry", task, agent, str(exc)[:200])
                client.post_events(turn_id, [{"kind": "error",
                    "payload": {"status": "reuse_send_failed", "task": task, "detail": str(exc)[:300]}}])
                client.fail_turn(turn_id, f"reuse send failed on existing session '{task}' — "
                                          f"not spawning a duplicate; retry")
                return f"failed:{turn_id}"
            logger.warning("reuse: task '%s' is gone (agent=%s) — creating fresh + rehydrating", task, agent)
            client.post_events(turn_id, [{"kind": "status",
                "payload": {"status": "reuse_task_gone", "task": task}}])
        else:
            logger.info("REUSE  turn=%s agent=%s thread=%s -> existing session '%s' (no new claude session)",
                        turn_id, agent, thread_key, task)
            client.post_events(turn_id, [{"kind": "status",
                "payload": {"status": "reused_session", "task": task, "thread_key": thread_key}}])
            client.record_session(runner_id, agent, thread_key, emdash_task_id=task)
            client.finish(turn_id, note=f"delivered to existing session '{task}'")
            return f"reused:{turn_id}"

    # --- create a fresh session, rehydrating durable context when we have it ---
    prompt = work_prompt
    summary = plan.get("summary") or ""
    if summary:
        prompt = (f"[Continuing prior work on this thread — context from earlier sessions "
                  f"(a fresh session, possibly a different machine):]\n{summary}\n\n{work_prompt}")
    if plan.get("reuse"):
        # We got here from a reuse that fell back — worth flagging: a persistently
        # failing reuse means a NEW session per turn (cost). Investigate the task.
        logger.warning("REUSE FELL BACK to CREATE for thread=%s (agent=%s) — the linked "
                       "emdash session was unreachable; check for a stuck/gone task", thread_key, agent)
    try:
        res = cdp_control.create_task(agent, prompt, task_name=_task_name(agent, turn), port=cfg.cdp_port)
    except cdp_control.CDPError as exc:
        logger.error("CREATE failed turn=%s agent=%s: %s", turn_id, agent, exc)
        client.fail_turn(turn_id, f"emdash create failed: {exc}")
        return f"failed:{turn_id}"

    task = res.get("task") or ""
    logger.info("CREATE turn=%s agent=%s thread=%s -> new session '%s' rehydrated=%s "
                "(NEW claude session = tokens)", turn_id, agent, thread_key, task, bool(summary))
    client.post_events(turn_id, [{"kind": "status",
        "payload": {"status": "created_session", "task": task, "thread_key": thread_key,
                    "rehydrated": bool(summary)}}])
    client.record_session(
        runner_id, agent, thread_key, emdash_task_id=task,
        agent_task_ext_id=ref.get("agent_task_ext_id"),
        summary=summary or None,
    )
    client.finish(turn_id, note=f"created session '{task}'" + (" (rehydrated)" if summary else ""))
    return f"created:{turn_id}:{task}"
