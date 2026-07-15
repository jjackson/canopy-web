"""Deterministic inbox trigger: read an agent's gmail and enqueue one email-origin
turn per NEW thread state. Runs in the runner loop — NO Ada, NO LLM judgment in the
hot path; "new email on a thread → a turn" is a fixed rule.

`gog gmail search --json` returns {threads: [{id (=thread_id), from, subject, date,
messageCount, labels}]}. Idempotency is keyed on (thread, messageCount) so each new
reply fires exactly one turn and re-polling the SAME state never double-fires. The
enqueued turn carries the thread_id, so execute_turn resolves it to the existing
session (continuity) or a fresh one.
"""
from __future__ import annotations

import json
import subprocess

# UNREAD only — the "new email" signal. Critically NOT "all recent threads":
# every matched thread becomes a turn → a claude session, so an over-broad query
# is a cost bomb. Idempotency (thread+messageCount) means an unread thread fires
# exactly once until its state changes.
DEFAULT_QUERY = "in:inbox is:unread newer_than:14d"


class InboxError(Exception):
    pass


def search_threads(mailbox: str, gog_client: str, query: str = DEFAULT_QUERY,
                   max_threads: int = 15, *, runner=subprocess.run) -> list[dict]:
    try:
        r = runner(
            ["gog", "gmail", "search", "--account", mailbox, "--client", gog_client,
             query, "--max", str(max_threads), "--json"],
            capture_output=True, text=True, timeout=45,
        )
    except FileNotFoundError as exc:
        raise InboxError("gog not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise InboxError("gog gmail search timed out") from exc
    if r.returncode != 0:
        raise InboxError(r.stderr.strip() or "gog gmail search failed")
    try:
        return json.loads(r.stdout or "{}").get("threads", []) or []
    except ValueError as exc:
        raise InboxError(f"non-JSON from gog gmail search: {(r.stdout or '')[:150]!r}") from exc


def check_inbox(client, agent: str, *, mailbox: str, gog_client: str,
                query: str = DEFAULT_QUERY, max_threads: int = 15, runner=subprocess.run) -> list[str]:
    """Enqueue an email-origin turn for each new thread state. Returns the thread ids
    enqueued. Idempotent on (thread, messageCount): re-polling is a no-op server-side."""
    threads = search_threads(mailbox, gog_client, query, max_threads, runner=runner)
    enqueued: list[str] = []
    for t in threads:
        tid = t.get("id")
        if not tid:
            continue
        count = t.get("messageCount", 1)
        frm, subj = t.get("from", ""), t.get("subject", "")
        # Clean command only — the agent's own /turn command does everything (reads the
        # thread, triages under guardrails, marks it read). The runner hands the exact
        # thread it already resolved so the agent doesn't re-scan the inbox.
        client.enqueue_turn(
            agent, "email", f"email-{agent}-{tid}-{count}",
            origin_ref={"thread_id": tid, "from": frm, "subject": subj},
            prompt=f"/turn --thread {tid}",
        )
        enqueued.append(tid)
    return enqueued
