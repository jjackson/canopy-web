"""Canopy Runner — a macOS menu-bar app with a click-to-open panel.

The menu-bar shows a status-tinted tree; clicking it opens a rich panel (an NSPopover
hosting a WKWebView) styled to canopy-web's Warm Earth palette — think Google Drive's
menu-bar UI rather than a plain text menu. The panel shows:

  * runner status + today's CREATE/REUSE tally, with Pause/Resume + Start/Stop controls
  * every agent (fetched live from canopy-web) as a card with its details; clicking a
    card opens that agent's home page on canopy-web in the browser

It is a thin control surface — no state of its own. Runner state is read from the
runner's own files (PAUSED sentinel, runner.log, launchctl); agent data is read from
the canopy-web API with the runner's bearer token. Pure stdlib + pyobjc (Cocoa+WebKit).

Run standalone: `python -m canopy_runner.menubar`. Packaged as "Canopy Runner.app"
by menubar/build_app.sh (Spotlight-launchable, menu-bar-only).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import subprocess
import threading
import urllib.error
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import objc
from AppKit import (
    NSAffineTransform,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBezierPath,
    NSColor,
    NSImage,
    NSMakePoint,
    NSMakeRect,
    NSMakeSize,
    NSMinYEdge,
    NSPopover,
    NSPopoverBehaviorTransient,
    NSRoundLineCapStyle,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSViewController,
)
from Foundation import NSObject, NSTimer
from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController

from canopy_runner.tree import ICON_INSET, ink_bounds, tree_segments

# ── config discovery (shared source of truth with the daemon) ───────────────────
CONFIG = Path(os.environ.get("CANOPY_RUNNER_CONFIG", "~/.canopy/runner.json")).expanduser()
LOG = Path(os.environ.get("CANOPY_RUNNER_LOG", str(CONFIG.with_name("runner.log")))).expanduser()
PLIST = Path(os.environ.get(
    "CANOPY_RUNNER_PLIST",
    "~/emdash-projects/canopy-web/packages/canopy_runner/launchd/com.canopy.runner.plist",
)).expanduser()
PAUSE_FILE = CONFIG.with_name("PAUSED")
HEARTBEAT = CONFIG.with_name("heartbeat")  # runner touches this every cycle (liveness)
LABEL = "com.canopy.runner"

GLYPH = {"running": "🟢", "paused": "🟡", "stopped": "🔴", "stale": "🟠"}
# Muted status tints for the tree icon — readable on both light + dark menu bars.
STATUS_RGB = {
    "running": (0.40, 0.71, 0.52),   # calm green
    "paused":  (0.89, 0.69, 0.28),   # amber
    "stopped": (0.85, 0.35, 0.32),   # red
    "stale":   (0.90, 0.57, 0.27),   # orange
}


def _tree_image(state: str, px: int = 18):
    """A spreading bare-branch tree, scaled to fill `px` and tinted by runner status.

    The segment geometry is measured and fitted rather than drawn at fixed coords, so
    the tree is centered and fills the icon box no matter how the shape is tuned.
    Drawn as a vector so it stays crisp on retina."""
    r, g, b = STATUS_RGB.get(state, STATUS_RGB["stopped"])
    segs = tree_segments()
    x0, y0, x1, y1 = ink_bounds(segs)
    span = max(x1 - x0, y1 - y0)  # fit the larger axis; uniform scale keeps proportions
    scale = px * (1 - 2 * ICON_INSET) / span
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def _draw(_rect) -> bool:
        NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0).set()
        # Ops apply to a point in reverse order of declaration: the ink is centered on
        # the origin, scaled up (line widths with it), then moved to the icon's middle.
        xf = NSAffineTransform.transform()
        xf.translateXBy_yBy_(px / 2, px / 2)
        xf.scaleBy_(scale)
        xf.translateXBy_yBy_(-cx, -cy)
        xf.concat()
        for a, b_, w in segs:
            path = NSBezierPath.bezierPath()
            path.moveToPoint_(NSMakePoint(*a))
            path.lineToPoint_(NSMakePoint(*b_))
            path.setLineWidth_(w)
            path.setLineCapStyle_(NSRoundLineCapStyle)
            path.stroke()
        return True

    img = NSImage.imageWithSize_flipped_drawingHandler_(NSMakeSize(px, px), False, _draw)
    img.setTemplate_(False)  # keep our status tint (not auto-recolored by the menu bar)
    return img


CARD_ACCENTS = [  # oklch categorical tokens, cycled per-agent for the initials avatar
    "oklch(0.757 0.161 53.57)",   # primary / orange
    "oklch(0.765 0.177 163.22)",  # success / emerald
    "oklch(0.746 0.16 232.66)",   # info / sky
    "oklch(0.828 0.189 84.43)",   # warning / amber
    "oklch(0.72 0.15 300)",       # special / violet
]


# ── config / status helpers (stdlib) ────────────────────────────────────────────
def _load_cfg() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _token(cfg: dict) -> str:
    tok = cfg.get("token", "")
    if tok.startswith("@"):
        try:
            return Path(tok[1:]).expanduser().read_text().strip()
        except Exception:  # noqa: BLE001
            return ""
    return tok


def _base(cfg: dict) -> str:
    return (cfg.get("base_url") or "https://labs.connect.dimagi.com/canopy").rstrip("/")


def _agent_pause_file(slug: str) -> Path:
    # Per-agent pause sentinel — a sibling of the global PAUSED, keyed by slug. The
    # runner scans these to skip a single agent's inbox + queued turns while others run.
    return CONFIG.with_name(f"PAUSED.{slug}")


def _agent_paused(slug: str) -> bool:
    return _agent_pause_file(slug).exists()


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=15)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _daemon_loaded() -> bool:
    return _launchctl("print", f"{_domain()}/{LABEL}").returncode == 0


def _log_stats() -> dict:
    out = {"fresh": False, "age_s": None, "created": 0, "reused": 0, "last": ""}
    try:
        text = LOG.read_text(errors="replace")
    except Exception:  # noqa: BLE001
        return out
    try:
        out["age_s"] = int(dt.datetime.now().timestamp() - LOG.stat().st_mtime)
        out["fresh"] = out["age_s"] < 120
    except Exception:  # noqa: BLE001
        pass
    today = dt.datetime.now().strftime("%Y-%m-%d")
    lines = text.splitlines()
    for ln in lines:
        if not ln.startswith(today):
            continue
        if "CREATE turn=" in ln:
            out["created"] += 1
        elif "REUSE" in ln and "turn=" in ln:
            out["reused"] += 1
    for ln in reversed(lines):
        if any(k in ln for k in ("cycle:", "PAUSED", "RESUMED", "starting")):
            out["last"] = re.sub(r"\s+", " ", ln)[-90:]
            break
    return out


def _heartbeat_age() -> int | None:
    """Seconds since the runner last cycled (touched the heartbeat file), or None if it
    has never written one. This — not the log — is the liveness signal: the runner touches
    it every cycle even when idle/paused, whereas idle log lines are ~15 min apart."""
    try:
        return int(dt.datetime.now().timestamp() - HEARTBEAT.stat().st_mtime)
    except OSError:
        return None


def _runner_state() -> dict:
    paused, loaded, st = PAUSE_FILE.exists(), _daemon_loaded(), _log_stats()
    hb = _heartbeat_age()
    # Fresh = cycled recently. Prefer the heartbeat (updated every cycle); fall back to the
    # log's mtime only for a runner too old to write a heartbeat file.
    fresh = (hb < 75) if hb is not None else st["fresh"]
    if not loaded:
        state = "stopped"
    elif paused:
        state = "paused"
    elif not fresh:
        state = "stale"
    else:
        state = "running"
    return {"state": state, "paused": paused, "hb_age": hb, **st}


# ── agent data (canopy-web API) ─────────────────────────────────────────────────
def _api(base: str, token: str, path: str) -> object:
    req = urllib.request.Request(f"{base}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _workspace_map(base: str, token: str) -> dict:
    """slug -> its workspace slug. The fleet legitimately spans workspaces (e.g. a
    chief-of-staff agent lives in a different tenant than the product agents), so we list
    each of the user's workspaces and record which agents are in it. That's how the panel
    links every agent to ITS OWN `/w/<ws>/agents/<slug>` — linking to the *active* workspace
    404s any agent that lives elsewhere (the bug that hid Ada/Eva)."""
    out: dict = {}
    try:
        wss = _api(base, token, "/api/workspaces/") or []
    except Exception:  # noqa: BLE001
        return out
    for w in (wss if isinstance(wss, list) else wss.get("items", [])):
        ws = w.get("slug")
        if not ws:
            continue
        try:
            data = _api(base, token, f"/api/w/{ws}/agents/")
        except Exception:  # noqa: BLE001
            continue
        items = data.get("items", data) if isinstance(data, dict) else data
        for a in items:
            if a.get("slug"):
                out[a["slug"]] = ws
    return out


def _agent_url(base: str, slug: str, ws: str) -> str:
    """Deep-link to the agent in ITS workspace; fall back to the flat (active-workspace)
    path only when we couldn't resolve a workspace."""
    return f"{base}/w/{ws}/agents/{slug}" if ws else f"{base}/agents/{slug}"


def _pending_reviews(base: str, token: str, slugs: set) -> dict:
    """Pending canopy-web reviews attributed to an agent by run_id prefix (e.g.
    'ada-fleet-audit-…' -> ada). These are things the agent is waiting on YOU to decide,
    and they don't show up in needs-you (reviews are a separate model)."""
    try:
        data = _api(base, token, "/api/reviews/?status=pending")
    except Exception:  # noqa: BLE001
        return {}
    items = data if isinstance(data, list) else (data.get("items", []) if isinstance(data, dict) else [])
    by: dict = {}
    for r in items:
        head = (r.get("run_id") or "").split("-")[0]
        if head in slugs:
            by.setdefault(head, []).append({
                "type": "review",
                "title": r.get("title") or "Review pending",
                "url": f"{base}/review/{r.get('id')}",
                "created_at": r.get("created_at"),
            })
    return by


def fetch_agents(base: str, token: str) -> list[dict]:
    """List agents, then enrich each (parallel) with the KPIs that actually matter for
    supervising it: what's WAITING ON YOU (pending reviews + gated needs-you items, each
    with a click-through url), open task count, and last-active time. Best-effort."""
    if not token:
        return []
    try:
        data = _api(base, token, "/api/agents/")
    except Exception:  # noqa: BLE001
        return []
    items = data.get("items", data) if isinstance(data, dict) else data
    slugs = {a.get("slug") for a in items}
    rev_by = _pending_reviews(base, token, slugs)
    wsmap = _workspace_map(base, token)

    def _enrich(a: dict) -> dict:
        slug = a.get("slug", "")
        ws = wsmap.get(slug, "")
        detail, ny = {}, {}
        try:
            detail = _api(base, token, f"/api/agents/{slug}/")
        except Exception:  # noqa: BLE001
            pass
        try:
            ny = _api(base, token, f"/api/agents/{slug}/needs-you")
        except Exception:  # noqa: BLE001
            pass
        waiting = list(rev_by.get(slug, []))
        for it in (ny.get("items") or []):
            if it.get("type") in ("review", "question"):
                waiting.append({
                    "type": it["type"],
                    "title": it.get("title") or "",
                    "url": it.get("url") or _agent_url(base, slug, ws),
                    "created_at": it.get("created_at"),
                })
        return {**a, **detail, "_workspace": ws, "waiting": waiting}

    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(_enrich, items))


def _rel(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        s = (dt.datetime.now(dt.timezone.utc) - t).total_seconds()
    except Exception:  # noqa: BLE001
        return "—"
    if s < 90:
        return "just now"
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= n:
            return f"{int(s // n)}{unit} ago"
    return "just now"


# ── HTML render (Warm Earth dark) ───────────────────────────────────────────────
def _avatar(agent: dict, i: int, cls: str = "av") -> str:
    name = html.escape(agent.get("name") or agent.get("slug") or "?")
    if agent.get("avatar_url"):
        return f'<img class="{cls}" src="{html.escape(agent["avatar_url"])}" alt="">'
    accent = CARD_ACCENTS[i % len(CARD_ACCENTS)]
    return f'<div class="{cls}" style="background:{accent}">{(name[:1] or "?").upper()}</div>'


def _waiting_item(w: dict, agent: dict, i: int) -> str:
    """One 'waiting on you' row — a pending review or a gated needs-you item. The whole
    row is a click target that opens the thing (the review screen, the task, etc.)."""
    kind = w.get("type", "review")
    chip = {"review": "Review", "question": "Question"}.get(kind, kind.title())
    who = html.escape(agent.get("name") or agent.get("slug") or "")
    title = html.escape(w.get("title") or chip)
    when = _rel(w.get("created_at"))
    url = html.escape(w.get("url") or "")
    return f"""
    <div class="wi wi-{kind}" onclick="open_agent('{url}')" title="Open on canopy-web">
      {_avatar(agent, i, "av sm")}
      <div class="wibody">
        <div class="wirow"><span class="wchip {kind}">{chip}</span><span class="wtitle">{title}</span></div>
        <div class="wmeta">{who} · waiting {when}</div>
      </div>
      <span class="wgo">›</span>
    </div>"""


def _card(agent: dict, base: str, i: int, paused: bool) -> str:
    """Compact agent KPI row — the mobile-style card: who, status, the KPIs that matter
    (waiting-on-you · open tasks · last active), pause/resume, click-through to the agent."""
    slug = agent.get("slug", "")
    name = html.escape(agent.get("name") or slug)
    url = _agent_url(base, slug, agent.get("_workspace", ""))
    waiting = agent.get("waiting") or []
    tasks = agent.get("task_count")
    last = _rel(agent.get("latest_turn_at"))
    kpis = []
    if waiting:
        kpis.append(f'<span class="kpi hot">⏳ <b>{len(waiting)}</b> waiting</span>')
    if tasks is not None:
        kpis.append(f'<span class="kpi"><b>{tasks}</b> tasks</span>')
    kpis.append(f'<span class="kpi">active {last}</span>')
    pa = "pauseAgent" if not paused else "resumeAgent"
    plabel = "Pause" if not paused else "Resume"
    chip = '<span class="apill">Paused</span>' if paused else ""
    return f"""
    <div class="card{' ispaused' if paused else ''}" onclick="open_agent('{html.escape(url)}')" title="Open {name} on canopy-web">
      {_avatar(agent, i)}
      <div class="body">
        <div class="row1"><span class="name">{name}</span>{chip}</div>
        <div class="kpis">{''.join(kpis)}</div>
      </div>
      <button class="apause" onclick="event.stopPropagation(); act_agent('{pa}','{slug}')">{plabel}</button>
    </div>"""


def render(state: dict, agents: list[dict], base: str) -> str:
    s = state["state"]
    pill_word = {"running": "Running", "paused": "Paused",
                 "stopped": "Stopped", "stale": "Stale"}[s]
    hb = state.get("hb_age")
    checked = f"{hb}s ago" if hb is not None else "—"
    # Primary action is always the meaningful next step for the current state:
    #   stopped -> Start daemon (there's nothing to pause), else Pause/Resume the runner.
    # Pausing while stopped did nothing visible, which read as "the button is broken".
    if s == "stopped":
        primary_html = "<button class=\"btn primary\" onclick=\"act('start')\">Start daemon</button>"
        daemon_html = ""
    else:
        plabel = "Resume" if state["paused"] else "Pause"
        pact = "resume" if state["paused"] else "pause"
        primary_html = f"<button class=\"btn primary\" onclick=\"act('{pact}')\">{plabel} runner</button>"
        daemon_html = "<button class=\"btn\" onclick=\"act('stop')\">Stop daemon</button>"
    idx = {a.get("slug"): i for i, a in enumerate(agents)}

    # "Waiting on you" — the actionable inbox across the fleet (pending reviews + gated
    # needs-you items), highest-value first so the one thing to act on is at the top.
    waiting_rows = []
    order = {"review": 0, "question": 1}
    for a in agents:
        for w in (a.get("waiting") or []):
            waiting_rows.append((order.get(w.get("type"), 2), a, w))
    waiting_rows.sort(key=lambda t: (t[0], (t[2].get("created_at") or "")))
    if waiting_rows:
        waiting_html = "".join(_waiting_item(w, a, idx.get(a.get("slug"), 0))
                               for _, a, w in waiting_rows)
    else:
        waiting_html = '<div class="empty ok">Nothing needs you right now.</div>'
    waiting_n = len(waiting_rows)

    any_agent_paused = any(_agent_paused(a.get("slug", "")) for a in agents)
    all_act, all_label = (("resumeAllAgents", "Resume all") if any_agent_paused
                          else ("pauseAllAgents", "Pause all"))
    cards = "".join(_card(a, base, i, _agent_paused(a.get("slug", "")))
                    for i, a in enumerate(agents)) or \
        '<div class="empty">No agents found (check the runner token / connection).</div>'

    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
  :root {{
    --bg: oklch(0.147 0.004 49.25); --card: oklch(0.216 0.006 56.04);
    --muted: oklch(0.268 0.007 34.3); --border: oklch(0.268 0.007 34.3);
    --fg: oklch(0.923 0.003 48.72); --fg2: oklch(0.809 0.005 56.0);
    --dim: oklch(0.553 0.013 58.07); --primary: oklch(0.757 0.161 53.57);
    --ok: oklch(0.765 0.177 163.22); --warn: oklch(0.828 0.189 84.43);
    --danger: oklch(0.63 0.2 25);
  }}
  * {{ box-sizing: border-box; margin: 0; }}
  html,body {{ background: var(--bg); color: var(--fg);
    font: 13px/1.45 -apple-system, "SF Pro Text", system-ui, sans-serif; }}
  body {{ padding: 0; }}
  .hdr {{ position: sticky; top: 0; background: var(--bg); padding: 12px 14px 10px;
    border-bottom: 1px solid var(--border); z-index: 2; }}
  .titlerow {{ display: flex; align-items: center; gap: 8px; }}
  .brand {{ font-weight: 650; font-size: 14px; letter-spacing: .2px; }}
  .pill {{ margin-left: auto; font-size: 11px; font-weight: 600; padding: 2px 9px;
    border-radius: 999px; border: 1px solid transparent; }}
  .pill.running {{ color: var(--ok); background: color-mix(in oklch, var(--ok) 12%, transparent); border-color: color-mix(in oklch, var(--ok) 30%, transparent); }}
  .pill.paused {{ color: var(--warn); background: color-mix(in oklch, var(--warn) 12%, transparent); border-color: color-mix(in oklch, var(--warn) 30%, transparent); }}
  .pill.stopped {{ color: var(--danger); background: color-mix(in oklch, var(--danger) 14%, transparent); border-color: color-mix(in oklch, var(--danger) 32%, transparent); }}
  .pill.stale {{ color: var(--warn); background: color-mix(in oklch, var(--warn) 10%, transparent); }}
  .sub {{ color: var(--dim); font-size: 11px; margin-top: 5px; }}
  .sub b {{ color: var(--fg2); font-weight: 650; }}
  .last {{ color: var(--dim); font-size: 10px; margin-top: 3px; font-family: ui-monospace, monospace;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .actions {{ display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }}
  .btn {{ font: inherit; font-size: 11px; font-weight: 600; color: var(--fg2);
    background: var(--muted); border: 1px solid var(--border); border-radius: 7px;
    padding: 4px 10px; cursor: pointer; }}
  .btn:hover {{ color: var(--fg); border-color: var(--dim); }}
  .btn.primary {{ color: var(--bg); background: var(--primary); border-color: var(--primary); }}
  .sectlabel {{ display: flex; align-items: center; text-transform: uppercase; letter-spacing: .8px;
    font-size: 10px; color: var(--dim); font-weight: 700; padding: 13px 14px 5px; }}
  .sectlabel .cnt {{ color: var(--fg2); margin-left: 5px; }}
  .sectlabel .mini {{ margin-left: auto; font-size: 10px; letter-spacing: 0; text-transform: none;
    color: var(--fg2); background: var(--muted); border: 1px solid var(--border);
    border-radius: 6px; padding: 2px 8px; cursor: pointer; font-weight: 600; }}
  .sectlabel .mini:hover {{ color: var(--fg); border-color: var(--dim); }}
  .list {{ padding: 2px 10px 10px; display: flex; flex-direction: column; gap: 7px; }}
  /* waiting-on-you rows */
  .wi {{ display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 10px;
    background: var(--card); border: 1px solid var(--border); cursor: pointer; }}
  .wi:hover {{ border-color: color-mix(in oklch, var(--primary) 55%, var(--border)); }}
  .wi-review {{ border-left: 3px solid var(--warn); }}
  .wi-question {{ border-left: 3px solid var(--info, oklch(0.746 0.16 232.66)); }}
  .wibody {{ min-width: 0; flex: 1; }}
  .wirow {{ display: flex; align-items: center; gap: 7px; }}
  .wchip {{ font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px;
    padding: 1px 6px; border-radius: 999px; flex: none; }}
  .wchip.review {{ color: var(--warn); background: color-mix(in oklch, var(--warn) 15%, transparent); }}
  .wchip.question {{ color: oklch(0.746 0.16 232.66); background: color-mix(in oklch, oklch(0.746 0.16 232.66) 15%, transparent); }}
  .wtitle {{ font-weight: 620; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .wmeta {{ color: var(--dim); font-size: 11px; margin-top: 2px; }}
  .wgo {{ color: var(--dim); font-size: 18px; flex: none; }}
  /* agent KPI rows */
  .card {{ display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 10px;
    background: var(--card); border: 1px solid var(--border); cursor: pointer; }}
  .card:hover {{ border-color: color-mix(in oklch, var(--primary) 45%, var(--border)); }}
  .card.ispaused {{ opacity: .55; }}
  .card.ispaused:hover {{ opacity: .8; }}
  .apill {{ font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px;
    color: var(--warn); background: color-mix(in oklch, var(--warn) 14%, transparent);
    border: 1px solid color-mix(in oklch, var(--warn) 30%, transparent);
    padding: 1px 6px; border-radius: 999px; }}
  .apause {{ font: inherit; font-size: 10.5px; font-weight: 600; flex: none;
    color: var(--fg2); background: var(--muted); border: 1px solid var(--border);
    border-radius: 6px; padding: 3px 10px; cursor: pointer; }}
  .apause:hover {{ color: var(--fg); border-color: var(--dim); }}
  .av {{ width: 32px; height: 32px; border-radius: 9px; flex: none; object-fit: cover;
    display: flex; align-items: center; justify-content: center; color: var(--bg);
    font-weight: 700; font-size: 14px; }}
  .av.sm {{ width: 26px; height: 26px; border-radius: 7px; font-size: 12px; }}
  .body {{ min-width: 0; flex: 1; }}
  .row1 {{ display: flex; align-items: center; gap: 7px; }}
  .name {{ font-weight: 650; font-size: 13.5px; }}
  .kpis {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 3px; }}
  .kpi {{ color: var(--dim); font-size: 11px; }}
  .kpi b {{ color: var(--fg); font-weight: 650; }}
  .kpi.hot {{ color: var(--warn); }}
  .kpi.hot b {{ color: var(--warn); }}
  .empty {{ color: var(--dim); padding: 14px; text-align: center; font-size: 12px; }}
  .empty.ok {{ color: var(--ok); }}
  .foot {{ display: flex; gap: 6px; padding: 4px 14px 14px; }}
  .foot .btn {{ flex: 1; text-align: center; }}
</style></head><body>
  <div class="hdr">
    <div class="titlerow">
      <span class="brand">Canopy Runner</span>
      <span class="pill {s}">{pill_word}</span>
    </div>
    <div class="sub">Today: <b>{state.get('created', 0)}</b> created · <b>{state.get('reused', 0)}</b> reused · checked {checked}</div>
    <div class="actions">
      {primary_html}
      {daemon_html}
      <button class="btn" onclick="act('openLog')">Log</button>
      <button class="btn" onclick="act('refresh')">Refresh</button>
    </div>
  </div>
  <div class="sectlabel">Waiting on you<span class="cnt">· {waiting_n}</span></div>
  <div class="list">{waiting_html}</div>
  <div class="sectlabel">Agents<span class="cnt">· {len(agents)}</span>
    <button class="mini" onclick="act('{all_act}')">{all_label}</button>
  </div>
  <div class="list">{cards}</div>
  <div class="foot"><button class="btn" onclick="act('quit')">Quit menu-bar app</button></div>
<script>
  function send(m) {{ window.webkit.messageHandlers.bridge.postMessage(m); }}
  function act(a) {{ send({{action: a}}); }}
  function act_agent(a, slug) {{ send({{action: a, slug: slug}}); }}
  function open_agent(url) {{ if (url) send({{action: 'open', url: url}}); }}
</script></body></html>"""


# ── the pyobjc app: status item → popover(WKWebView) ────────────────────────────
class Controller(NSObject):
    def init(self):
        self = objc.super(Controller, self).init()
        if self is None:
            return None
        self.cfg = _load_cfg()
        self.agents: list = []
        return self

    # -- lifecycle --
    def applicationDidFinishLaunching_(self, _notif):
        bar = NSStatusBar.systemStatusBar()
        self.item = bar.statusItemWithLength_(NSVariableStatusItemLength)
        btn = self.item.button()
        btn.setImage_(_tree_image("stopped"))
        btn.setTarget_(self)
        btn.setAction_("toggle:")

        cfg = WKWebViewConfiguration.alloc().init()
        ucc = WKUserContentController.alloc().init()
        ucc.addScriptMessageHandler_name_(self, "bridge")
        cfg.setUserContentController_(ucc)
        frame = NSMakeRect(0, 0, 440, 600)
        self.web = WKWebView.alloc().initWithFrame_configuration_(frame, cfg)

        vc = NSViewController.alloc().init()
        vc.setView_(self.web)
        self.pop = NSPopover.alloc().init()
        self.pop.setContentSize_(NSMakeSize(440, 600))
        self.pop.setBehavior_(NSPopoverBehaviorTransient)
        self.pop.setContentViewController_(vc)

        self.refresh_status()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            5.0, self, "tick:", None, True)

    def applicationSupportsSecureRestorableState_(self, _app):
        return True

    # -- status icon --
    @objc.python_method
    def refresh_status(self):
        st = _runner_state()
        self._state = st
        self.item.button().setImage_(_tree_image(st["state"]))

    def tick_(self, _timer):
        # Re-assert accessory (menu-bar-only) and refresh the icon.
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.refresh_status()

    # -- panel open/close --
    def toggle_(self, sender):
        if self.pop.isShown():
            self.pop.performClose_(sender)
            return
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        btn = self.item.button()
        self.pop.showRelativeToRect_ofView_preferredEdge_(btn.bounds(), btn, NSMinYEdge)
        self._render_from_cache()      # instant paint from what we have
        self._reload_async()           # then refresh data in the background

    # Main-thread render trampoline (ObjC selector so performSelectorOnMainThread works).
    def renderMain_(self, _obj):
        self._render_from_cache()

    @objc.python_method
    def _render_from_cache(self):
        html_str = render(self._state, self.agents, _base(self.cfg))
        self.web.loadHTMLString_baseURL_(html_str, None)

    @objc.python_method
    def _reload_async(self):
        def work():
            agents = fetch_agents(_base(self.cfg), _token(self.cfg))
            self.agents = agents
            self.refresh_status()
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "renderMain:", None, False)
        threading.Thread(target=work, daemon=True).start()

    # -- JS bridge --
    def userContentController_didReceiveScriptMessage_(self, _ucc, message):
        body = message.body()
        action = body.get("action") if hasattr(body, "get") else None
        if action == "open":
            webbrowser.open(body.get("url", ""))
            self.pop.performClose_(None)
        elif action in ("pause", "resume"):
            self._set_pause(action == "pause")
            self.refresh_status()
            self._render_from_cache()
        elif action in ("pauseAgent", "resumeAgent"):
            slug = body.get("slug") if hasattr(body, "get") else None
            if slug:
                self._set_agent_pause(slug, action == "pauseAgent")
            self._render_from_cache()   # instant reflect (agents already cached)
        elif action in ("pauseAllAgents", "resumeAllAgents"):
            for a in self.agents:
                if a.get("slug"):
                    self._set_agent_pause(a["slug"], action == "pauseAllAgents")
            self._render_from_cache()
        elif action in ("start", "stop"):
            self._daemon(action)
            self.refresh_status()
            self._render_from_cache()
        elif action == "openLog":
            if LOG.exists():
                subprocess.run(["open", str(LOG)])
        elif action == "refresh":
            self._render_from_cache()
            self._reload_async()
        elif action == "quit":
            NSApplication.sharedApplication().terminate_(None)

    @objc.python_method
    def _set_pause(self, paused: bool):
        try:
            if paused:
                PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
                PAUSE_FILE.write_text(dt.datetime.now().isoformat())
            elif PAUSE_FILE.exists():
                PAUSE_FILE.unlink()
        except Exception:  # noqa: BLE001
            pass

    @objc.python_method
    def _set_agent_pause(self, slug: str, paused: bool):
        f = _agent_pause_file(slug)
        try:
            if paused:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(dt.datetime.now().isoformat())
            elif f.exists():
                f.unlink()
        except Exception:  # noqa: BLE001
            pass

    @objc.python_method
    def _daemon(self, action: str):
        if action == "start":
            if PLIST.exists():
                _launchctl("bootstrap", _domain(), str(PLIST))
                _launchctl("kickstart", f"{_domain()}/{LABEL}")
        else:
            _launchctl("bootout", f"{_domain()}/{LABEL}")


def main() -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    controller = Controller.alloc().init()
    app.setDelegate_(controller)
    app.run()


if __name__ == "__main__":
    main()
