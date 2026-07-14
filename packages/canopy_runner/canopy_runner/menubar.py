"""Canopy Runner — a macOS menu-bar app with a click-to-open panel.

The menu-bar shows just a status dot; clicking it opens a rich panel (an NSPopover
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
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMakeRect,
    NSMakeSize,
    NSMinYEdge,
    NSPopover,
    NSPopoverBehaviorTransient,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSViewController,
)
from Foundation import NSObject, NSTimer
from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController

# ── config discovery (shared source of truth with the daemon) ───────────────────
CONFIG = Path(os.environ.get("CANOPY_RUNNER_CONFIG", "~/.canopy/runner.json")).expanduser()
LOG = Path(os.environ.get("CANOPY_RUNNER_LOG", str(CONFIG.with_name("runner.log")))).expanduser()
PLIST = Path(os.environ.get(
    "CANOPY_RUNNER_PLIST",
    "~/emdash-projects/canopy-web/packages/canopy_runner/launchd/com.canopy.runner.plist",
)).expanduser()
PAUSE_FILE = CONFIG.with_name("PAUSED")
LABEL = "com.canopy.runner"

GLYPH = {"running": "🟢", "paused": "🟡", "stopped": "🔴", "stale": "🟠"}
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


def _runner_state() -> dict:
    paused, loaded, st = PAUSE_FILE.exists(), _daemon_loaded(), _log_stats()
    if not loaded:
        state = "stopped"
    elif paused:
        state = "paused"
    elif not st["fresh"]:
        state = "stale"
    else:
        state = "running"
    return {"state": state, "paused": paused, **st}


# ── agent data (canopy-web API) ─────────────────────────────────────────────────
def _api(base: str, token: str, path: str) -> object:
    req = urllib.request.Request(f"{base}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def fetch_agents(base: str, token: str) -> list[dict]:
    """List agents, then enrich each with its detail counts (parallel). Best-effort:
    a failed detail just leaves the base fields."""
    if not token:
        return []
    try:
        data = _api(base, token, "/api/agents/")
    except Exception:  # noqa: BLE001
        return []
    items = data.get("items", data) if isinstance(data, dict) else data

    def _detail(a: dict) -> dict:
        try:
            return {**a, **_api(base, token, f"/api/agents/{a['slug']}/")}
        except Exception:  # noqa: BLE001
            return a

    with ThreadPoolExecutor(max_workers=6) as ex:
        return list(ex.map(_detail, items))


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
def _card(agent: dict, base: str, i: int, paused: bool) -> str:
    slug = agent.get("slug", "")
    name = html.escape(agent.get("name") or slug)
    blurb = html.escape((agent.get("persona") or agent.get("description") or "").strip())
    email = html.escape(agent.get("email") or "")
    url = f"{base}/agents/{slug}"
    accent = CARD_ACCENTS[i % len(CARD_ACCENTS)]
    initial = (name[:1] or "?").upper()
    avatar = (f'<img class="av" src="{html.escape(agent["avatar_url"])}" alt="">'
              if agent.get("avatar_url") else
              f'<div class="av" style="background:{accent}">{initial}</div>')
    stats = []
    for label, key in (("turns", "turn_count"), ("tasks", "task_count"),
                       ("skills", "skill_count"), ("products", "work_product_count")):
        v = agent.get(key)
        if v is not None:
            stats.append(f'<span class="stat"><b>{v}</b> {label}</span>')
    last = _rel(agent.get("latest_turn_at"))
    # Per-agent pause control. stopPropagation so toggling pause doesn't also open the
    # agent's page. The whole card (minus this button) is the click target for open.
    pa = "pauseAgent" if not paused else "resumeAgent"
    plabel = "Pause" if not paused else "Resume"
    chip = '<span class="apill">Paused</span>' if paused else ""
    return f"""
    <div class="card{' ispaused' if paused else ''}" onclick="open_agent('{html.escape(url)}')" title="Open {name} on canopy-web">
      {avatar}
      <div class="body">
        <div class="row1"><span class="name">{name}</span>{chip}<span class="last">{last}</span></div>
        {f'<div class="blurb">{blurb}</div>' if blurb else ''}
        <div class="meta">{f'<span class="email">{email}</span>' if email else ''}</div>
        <div class="cardfoot">
          <div class="stats">{''.join(stats)}</div>
          <button class="apause" onclick="event.stopPropagation(); act_agent('{pa}','{slug}')">{plabel}</button>
        </div>
      </div>
    </div>"""


def render(state: dict, agents: list[dict], base: str) -> str:
    s = state["state"]
    pill_word = {"running": "Running", "paused": "Paused",
                 "stopped": "Stopped", "stale": "Stale"}[s]
    age = f'{state["age_s"]}s ago' if state.get("age_s") is not None else "no log"
    pause_label = "Resume" if state["paused"] else "Pause"
    pause_act = "resume" if state["paused"] else "pause"
    daemon_label, daemon_act = (("Stop daemon", "stop") if s != "stopped"
                                else ("Start daemon", "start"))
    cards = "".join(_card(a, base, i, _agent_paused(a.get("slug", "")))
                    for i, a in enumerate(agents)) or \
        '<div class="empty">No agents found (check the runner token / connection).</div>'
    last_line = html.escape(state.get("last") or "")

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
  .sectlabel {{ text-transform: uppercase; letter-spacing: .8px; font-size: 10px;
    color: var(--dim); font-weight: 700; padding: 12px 14px 4px; }}
  .list {{ padding: 2px 10px 12px; display: flex; flex-direction: column; gap: 7px; }}
  .card {{ display: flex; gap: 10px; padding: 10px; border-radius: 10px;
    background: var(--card); border: 1px solid var(--border); cursor: pointer; }}
  .card:hover {{ border-color: color-mix(in oklch, var(--primary) 45%, var(--border)); }}
  .card.ispaused {{ opacity: .58; }}
  .card.ispaused:hover {{ opacity: .8; }}
  .apill {{ font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px;
    color: var(--warn); background: color-mix(in oklch, var(--warn) 14%, transparent);
    border: 1px solid color-mix(in oklch, var(--warn) 30%, transparent);
    padding: 1px 6px; border-radius: 999px; }}
  .cardfoot {{ display: flex; align-items: center; gap: 10px; margin-top: 7px; }}
  .apause {{ margin-left: auto; font: inherit; font-size: 10.5px; font-weight: 600;
    color: var(--fg2); background: var(--muted); border: 1px solid var(--border);
    border-radius: 6px; padding: 2px 9px; cursor: pointer; }}
  .apause:hover {{ color: var(--fg); border-color: var(--dim); }}
  .av {{ width: 34px; height: 34px; border-radius: 9px; flex: none; object-fit: cover;
    display: flex; align-items: center; justify-content: center; color: var(--bg);
    font-weight: 700; font-size: 15px; }}
  .body {{ min-width: 0; flex: 1; }}
  .row1 {{ display: flex; align-items: baseline; gap: 8px; }}
  .name {{ font-weight: 650; font-size: 13.5px; }}
  .row1 .last {{ margin: 0; margin-left: auto; }}
  .blurb {{ color: var(--fg2); font-size: 12px; margin-top: 2px;
    overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
  .email {{ color: var(--dim); font-size: 11px; font-family: ui-monospace, monospace; }}
  .meta {{ margin-top: 4px; }}
  .stats {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .stat {{ color: var(--dim); font-size: 11px; }}
  .stat b {{ color: var(--fg); font-weight: 650; }}
  .empty {{ color: var(--dim); padding: 20px 14px; text-align: center; }}
  .foot {{ display: flex; gap: 6px; padding: 0 14px 14px; }}
  .foot .btn {{ flex: 1; text-align: center; }}
</style></head><body>
  <div class="hdr">
    <div class="titlerow">
      <span class="brand">🌲 Canopy Runner</span>
      <span class="pill {s}">{pill_word}</span>
    </div>
    <div class="sub">Today: <b>{state.get('created', 0)}</b> created · <b>{state.get('reused', 0)}</b> reused · log {age}</div>
    {f'<div class="last">{last_line}</div>' if last_line else ''}
    <div class="actions">
      <button class="btn primary" onclick="act('{pause_act}')">{pause_label}</button>
      <button class="btn" onclick="act('{daemon_act}')">{daemon_label}</button>
      <button class="btn" onclick="act('openLog')">Log</button>
      <button class="btn" onclick="act('refresh')">Refresh</button>
    </div>
  </div>
  <div class="sectlabel">Agents · {len(agents)}</div>
  <div class="list">{cards}</div>
  <div class="foot"><button class="btn" onclick="act('quit')">Quit menu-bar app</button></div>
<script>
  function send(m) {{ window.webkit.messageHandlers.bridge.postMessage(m); }}
  function act(a) {{ send({{action: a}}); }}
  function act_agent(a, slug) {{ send({{action: a, slug: slug}}); }}
  function open_agent(url) {{ send({{action: 'open', url: url}}); }}
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
        btn.setTitle_("🔴")
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

    # -- status dot --
    @objc.python_method
    def refresh_status(self):
        st = _runner_state()
        self._state = st
        self.item.button().setTitle_(GLYPH[st["state"]])

    def tick_(self, _timer):
        # Re-assert accessory (menu-bar-only) and refresh the dot.
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
