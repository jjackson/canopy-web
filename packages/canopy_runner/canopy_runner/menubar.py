"""Canopy Runner — a lightweight macOS menu-bar app to watch + control the runner.

It is a *thin control surface* over the launchd-managed runner daemon; it holds no
state of its own. Everything it shows is read live from the runner's own files:

  * pause      → presence of the PAUSED sentinel (sibling of runner.json)
  * alive      → `launchctl print` for the LaunchAgent + freshness of runner.log
  * activity   → today's CREATE / REUSE / cycle lines tail-parsed from runner.log

Controls:
  * Pause / Resume        → create / remove the PAUSED sentinel (instant, token-safe)
  * Start / Stop daemon   → launchctl bootstrap / bootout (the nuclear option)
  * Quick links           → open the relevant canopy-web pages in the browser
  * Open runner log        → reveal ~/.canopy/runner.log

Run standalone: `python -m canopy_runner.menubar`. Packaged as "Canopy Runner.app"
(LSUIElement, so menu-bar-only, no dock icon) by menubar/build_app.sh — Spotlight-
launchable like "Emdash CDP".

Config is discovered from CANOPY_RUNNER_CONFIG (default ~/.canopy/runner.json); the
log path from CANOPY_RUNNER_LOG (default alongside it). Pure stdlib + rumps.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import webbrowser
from pathlib import Path

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

LABEL = "com.canopy.runner"                      # the LaunchAgent label
CONFIG = Path(os.environ.get("CANOPY_RUNNER_CONFIG", "~/.canopy/runner.json")).expanduser()
LOG = Path(os.environ.get("CANOPY_RUNNER_LOG", str(CONFIG.with_name("runner.log")))).expanduser()
PLIST = Path(os.environ.get(
    "CANOPY_RUNNER_PLIST",
    "~/emdash-projects/canopy-web/packages/canopy_runner/launchd/com.canopy.runner.plist",
)).expanduser()
PAUSE_FILE = CONFIG.with_name("PAUSED")

# Menu-bar glyphs — status legible at a glance from the top of the screen.
GLYPH = {"running": "🟢", "paused": "🟡", "stopped": "🔴", "stale": "🟠"}


def _load_cfg() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _links(cfg: dict) -> list[tuple[str, str]]:
    """Quick links → canopy-web. Flat paths (/, /agents, /timeline …) 302 into the
    caller's active workspace, so we don't need to know the workspace slug here."""
    base = (cfg.get("base_url") or "https://labs.connect.dimagi.com/canopy").rstrip("/")
    return [
        ("🌲  Workbench", f"{base}/"),
        ("🤖  Agents (turns & needs-you)", f"{base}/agents"),
        ("📰  Timeline", f"{base}/timeline"),
        ("💡  Insights", f"{base}/insights"),
        ("🧵  Shared sessions", f"{base}/sessions"),
        ("⚙️  Settings (AI backend)", f"{base}/settings"),
    ]


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=15)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _daemon_loaded() -> bool:
    r = _launchctl("print", f"{_domain()}/{LABEL}")
    return r.returncode == 0


def _log_stats() -> dict:
    """Tail-parse runner.log: freshness, today's CREATE/REUSE counts, last cycle line."""
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
        elif "REUSE  turn=" in ln or "REUSE turn=" in ln:
            out["reused"] += 1
    for ln in reversed(lines):
        if "cycle:" in ln or "PAUSED" in ln or "RESUMED" in ln or "starting" in ln:
            out["last"] = re.sub(r"\s+", " ", ln)[-90:]
            break
    return out


class RunnerApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Canopy Runner", quit_button=None)
        self.cfg = _load_cfg()

        self.status_item = rumps.MenuItem("Runner: …")
        self.stats_item = rumps.MenuItem("—")
        self.pause_item = rumps.MenuItem("⏸  Pause runner", callback=self.toggle_pause)

        links = rumps.MenuItem("🔗  Quick links")
        for label, url in _links(self.cfg):
            links.add(rumps.MenuItem(label, callback=self._opener(url)))

        self.menu = [
            self.status_item,
            self.stats_item,
            None,
            self.pause_item,
            None,
            links,
            rumps.MenuItem("📄  Open runner log", callback=self.open_log),
            None,
            rumps.MenuItem("▶︎  Start daemon", callback=self.start_daemon),
            rumps.MenuItem("■  Stop daemon", callback=self.stop_daemon),
            None,
            rumps.MenuItem("Quit menu-bar app", callback=rumps.quit_application),
        ]
        self.refresh(None)

    # ---- opening links ----
    def _opener(self, url: str):
        def _cb(_):
            webbrowser.open(url)
        return _cb

    def open_log(self, _):
        subprocess.run(["open", str(LOG)]) if LOG.exists() else rumps.alert(
            "No log yet", f"{LOG} does not exist. Start the daemon first.")

    # ---- pause / resume (token-safe, instant) ----
    def toggle_pause(self, _):
        if PAUSE_FILE.exists():
            try:
                PAUSE_FILE.unlink()
            except Exception as e:  # noqa: BLE001
                rumps.alert("Resume failed", str(e))
        else:
            try:
                PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
                PAUSE_FILE.write_text(dt.datetime.now().isoformat())
            except Exception as e:  # noqa: BLE001
                rumps.alert("Pause failed", str(e))
        self.refresh(None)

    # ---- daemon start / stop (the nuclear option) ----
    def start_daemon(self, _):
        if not PLIST.exists():
            rumps.alert("No plist", f"{PLIST} not found.")
            return
        _launchctl("bootstrap", _domain(), str(PLIST))
        _launchctl("kickstart", f"{_domain()}/{LABEL}")
        self.refresh(None)

    def stop_daemon(self, _):
        _launchctl("bootout", f"{_domain()}/{LABEL}")
        self.refresh(None)

    # ---- periodic status refresh ----
    @rumps.timer(5)
    def refresh(self, _):
        paused = PAUSE_FILE.exists()
        loaded = _daemon_loaded()
        st = _log_stats()

        if not loaded:
            state = "stopped"
        elif paused:
            state = "paused"
        elif not st["fresh"]:
            state = "stale"
        else:
            state = "running"

        # Belt-and-suspenders: because the .app launcher execs the venv's Python, macOS
        # can briefly adopt Python.app's identity (dock icon + "Python" menu). Re-assert
        # accessory (menu-bar-only) each tick so it can't win the race after launch.
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        # Title carries a word, not just a dot, so it's findable among the system icons.
        self.title = f"{GLYPH[state]} Runner"
        self.pause_item.title = "▶︎  Resume runner" if paused else "⏸  Pause runner"

        pretty = {"running": "running", "paused": "PAUSED", "stopped": "stopped (daemon not loaded)",
                  "stale": "loaded but log is stale"}[state]
        age = f"{st['age_s']}s ago" if st["age_s"] is not None else "no log"
        self.status_item.title = f"Runner: {pretty}  ·  last log {age}"
        self.stats_item.title = f"Today: {st['created']} created · {st['reused']} reused"
        if st["last"]:
            self.stats_item.title += f"   |  {st['last']}"


def main() -> None:
    # Menu-bar-only: no dock icon, no "Python" app menu. Set before the run loop starts;
    # refresh() re-asserts it too (see note there).
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    RunnerApp().run()


if __name__ == "__main__":
    main()
