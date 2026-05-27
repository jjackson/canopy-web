"""End-to-end smoke test against the deployed canopy-web.

Logs in via /api/auth/e2e-login/ as ace@dimagi-ai.com, injects the session
cookie into Playwright, then visits each primary page and screenshots it.
Asserts key UI markers per page; fails loud on any missing element or HTTP
4xx/5xx response.

Run:
    uv run python scripts/qa/smoke_deployed.py

Env:
    CANOPY_E2E_AUTH_TOKEN  required — shared secret for the e2e-login endpoint
    CANOPY_URL             default https://canopy-web-ujpz2cuyxq-uc.a.run.app

Output: screenshots/ directory + a printed pass/fail summary.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from playwright.sync_api import Browser, Page, sync_playwright

URL = os.environ.get("CANOPY_URL", "https://canopy-web-ujpz2cuyxq-uc.a.run.app")
TOKEN = os.environ.get("CANOPY_E2E_AUTH_TOKEN", "")
EMAIL = os.environ.get("CANOPY_E2E_EMAIL", "ace@dimagi-ai.com")
SCREENSHOTS = Path(__file__).parent / "screenshots"


def e2e_login_session_cookie() -> dict:
    """POST to /api/auth/e2e-login/ and return the sessionid cookie dict."""
    if not TOKEN:
        raise SystemExit("CANOPY_E2E_AUTH_TOKEN must be set")
    resp = requests.post(
        f"{URL}/api/auth/e2e-login/",
        json={"email": EMAIL, "token": TOKEN},
        timeout=20,
    )
    if resp.status_code != 200:
        raise SystemExit(f"e2e-login failed: {resp.status_code} {resp.text[:200]}")
    cookies = resp.cookies
    sessionid = cookies.get("sessionid")
    if not sessionid:
        raise SystemExit(f"e2e-login returned no sessionid cookie: {dict(cookies)}")
    host = urlparse(URL).hostname or "localhost"
    return {
        "name": "sessionid",
        "value": sessionid,
        "domain": host,
        "path": "/",
        "httpOnly": True,
        "secure": True,
        "sameSite": "Lax",
    }


def check_page(
    browser: Browser,
    cookie: dict,
    path: str,
    *,
    expect_text: list[str] | None = None,
    forbid_text: list[str] | None = None,
    name: str,
) -> tuple[bool, str]:
    """Navigate to URL+path, assert expect_text substrings appear and
    forbid_text substrings do NOT appear, screenshot, capture console errors.
    """
    context = browser.new_context()
    context.add_cookies([cookie])
    page: Page = context.new_page()
    console_errors: list[str] = []
    page.on(
        "console",
        lambda m: console_errors.append(f"{m.type}: {m.text[:200]}") if m.type == "error" else None,
    )
    try:
        response = page.goto(f"{URL}{path}", wait_until="networkidle", timeout=30000)
    except Exception as e:
        context.close()
        return False, f"goto failed: {e}"
    status = response.status if response else "unknown"
    if status >= 400:
        context.close()
        return False, f"HTTP {status}"

    SCREENSHOTS.mkdir(exist_ok=True)
    screenshot_path = SCREENSHOTS / f"{name}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)

    body_text = page.inner_text("body").lower()
    missing = [t for t in (expect_text or []) if t.lower() not in body_text]
    forbidden = [t for t in (forbid_text or []) if t.lower() in body_text]
    context.close()

    issues = []
    if missing:
        issues.append(f"missing={missing}")
    if forbidden:
        issues.append(f"FORBIDDEN={forbidden}")
    if console_errors:
        issues.append(f"console_errors={console_errors[:3]}")
    if issues:
        return False, f"{'; '.join(issues)}; screenshot={screenshot_path}"
    return True, f"OK; screenshot={screenshot_path}; status={status}"


PAGES = [
    # (path, screenshot_name, must-contain substrings, must-NOT-contain substrings)
    ("/", "dashboard", ["projects"], ["failed to load"]),
    ("/insights", "insights", ["insights"], ["failed to load"]),
    ("/skills", "skills", ["skills"], ["failed to load"]),
    ("/workspaces", "workspaces", ["workspace"], ["failed to load"]),
    ("/new", "new-collection", ["collection"], ["failed to load"]),
    ("/leaderboard", "leaderboard", ["leaderboard"], ["failed to load"]),
    ("/guide", "guide", ["guide"], ["failed to load"]),
    ("/settings", "settings", ["ai backend"], ["failed to load"]),
    ("/walkthroughs", "walkthroughs", ["walkthroughs"], ["failed to load"]),
]


def main() -> int:
    print(f"Smoke target: {URL}")
    print(f"Login as: {EMAIL}")
    cookie = e2e_login_session_cookie()
    print(f"  sessionid={cookie['value'][:12]}…")
    print()

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for path, name, expects, forbidden in PAGES:
            ok, msg = check_page(
                browser, cookie, path,
                expect_text=expects, forbid_text=forbidden, name=name,
            )
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {path:25s} → {msg}")
            results.append((path, ok, msg))
        browser.close()

    print()
    failed = [r for r in results if not r[1]]
    print(f"{len(results) - len(failed)}/{len(results)} pages passed")
    if failed:
        print()
        print("Failures:")
        for path, _, msg in failed:
            print(f"  {path}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
