"""Fleet inbox filters — the junk guard, defined ONCE here and applied to any/all
agent mailboxes via gog Gmail filters. Conservative by design: only obviously
automated / marketing mail is skipped-inbox + marked-read, so a real message from a
person never gets silently archived. Edit ``FILTERS`` and re-run
``canopy-runner apply-filters --config … [--agent hal]`` to update the fleet.

Gmail filters apply to FUTURE mail only (not the existing inbox) — that's the point:
keep junk from ever becoming a turn (= a session = tokens), without touching history.
"""
from __future__ import annotations

import json
import subprocess

# Each rule: a Gmail match `query` + actions. Keep this list conservative and legible.
FILTERS: list[dict] = [
    {
        "name": "automated-noreply",
        "query": 'from:(noreply OR no-reply OR donotreply OR "do-not-reply" OR mailer-daemon OR postmaster)',
        "archive": True, "mark_read": True,
    },
    {
        "name": "promotions",
        "query": "category:promotions",
        "archive": True, "mark_read": True,
    },
    {
        "name": "social",
        "query": "category:social",
        "archive": True, "mark_read": True,
    },
]


class FilterError(Exception):
    pass


def _existing_queries(mailbox: str, client: str, *, runner=subprocess.run) -> set[str]:
    """Gmail-search queries already covered by a filter on this mailbox (for dedup)."""
    try:
        r = runner(["gog", "gmail", "settings", "filters", "list",
                    "--account", mailbox, "--client", client, "--json"],
                   capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if r.returncode != 0:
        return set()
    try:
        items = json.loads(r.stdout or "{}").get("filters") or []
    except ValueError:
        return set()
    out = set()
    for f in items:
        q = (f.get("criteria") or {}).get("query")
        if q:
            out.add(q)
    return out


def apply_filters(mailbox: str, client: str, *, runner=subprocess.run, dry_run: bool = False) -> dict:
    """Apply the framework FILTERS to one mailbox, idempotently (skips ones whose query
    is already filtered). Returns {applied:[names], skipped:[names]}."""
    existing = _existing_queries(mailbox, client, runner=runner)
    applied, skipped = [], []
    for flt in FILTERS:
        if flt["query"] in existing:
            skipped.append(flt["name"])
            continue
        cmd = ["gog", "gmail", "settings", "filters", "create",
               "--account", mailbox, "--client", client, "--query", flt["query"]]
        if flt.get("archive"):
            cmd.append("--archive")
        if flt.get("mark_read"):
            cmd.append("--mark-read")
        if flt.get("add_label"):
            cmd += ["--add-label", flt["add_label"]]
        if dry_run:
            cmd.append("--dry-run")
        r = runner(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise FilterError(f"filter '{flt['name']}' on {mailbox}: {r.stderr.strip() or 'gog failed'}")
        applied.append(flt["name"])
    return {"applied": applied, "skipped": skipped}
