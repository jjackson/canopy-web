"""Architecture boundary test — enforces the framework→product one-way rule.

The dependency arrow is one-way: FRAMEWORK code (the generic, agent-agnostic
substrate any agent could reuse) never imports PRODUCT code (canopy's own domain
features). PRODUCT may freely import FRAMEWORK. This is the invariant that keeps
the blend "cuttable" — see ARCHITECTURE.md for tier definitions and the rationale
behind every carve-out below.

This test is the machine-checkable shadow of ARCHITECTURE.md (Wave 0 of the
framework harvest). Pure stdlib `ast` — no Django setup, no new dependency.

If it fails you have two honest options:
  (a) you put product code in a framework app  → move it to a product app, or
  (b) you added a genuinely new allowed seam   → document it in ARCHITECTURE.md
      and add it to COMPOSITION_ROOT / ALLOWED_FILES below WITH a reason.
Never silence a violation by reclassifying an app just to make this pass.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"

# ── The tiers (canonical copy lives in ARCHITECTURE.md; keep them in sync) ──────
FRAMEWORK = {"agents", "agent_runs", "workspaces", "api", "common", "timeline", "tokens", "session_sharing", "issues", "mcp", "system", "harness"}
PRODUCT = {"projects",
           "walkthroughs", "reviews", "shareouts", "runs"}

# The ONE composition root allowed to import every app — it wires each app's
# router into the single NinjaAPI (analogous to a Django URLconf). A framework
# needs exactly one such seam; this is it. Not subject to the one-way rule.
COMPOSITION_ROOT = {"api"}

# File-level carve-outs: framework files that legitimately import product, each
# with a documented reason. Keep this list SHORT and justified — every entry is a
# known, accepted seam, not a TODO.
ALLOWED_FILES = {
    # The insights MCP tool is a PRODUCT tool (canopy portfolio insights) that
    # registers on the FRAMEWORK MCP server — apps/mcp/server.py imports
    # apps.mcp.tools as a registration side effect. Same composition-root shape
    # as the api router hub. Candidate for inversion (product registers its own
    # tool via AppConfig.ready) in a later wave.
    "apps/mcp/tools/insights.py",
}


def _imported_apps(path: pathlib.Path) -> set[str]:
    """The set of local app names this module imports (via `apps.<name>`)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("apps."):
            targets.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("apps."):
                    targets.add(alias.name.split(".")[1])
    return targets


def _is_excluded(rel: str, name: str) -> bool:
    return "/migrations/" in rel or "/tests/" in rel or name.startswith("test_")


def test_framework_apps_do_not_import_product() -> None:
    violations: list[str] = []
    for app in sorted(FRAMEWORK - COMPOSITION_ROOT):
        base = APPS / app
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if _is_excluded(rel, path.name) or rel in ALLOWED_FILES:
                continue
            leaked = _imported_apps(path) & PRODUCT
            if leaked:
                violations.append(f"{rel} imports product app(s) {sorted(leaked)}")
    assert not violations, (
        "FRAMEWORK code must not import PRODUCT code (see ARCHITECTURE.md):\n  "
        + "\n  ".join(violations)
    )


def test_every_app_is_classified() -> None:
    """A new app can't silently dodge the boundary — it must be tiered explicitly."""
    on_disk = {
        p.name for p in APPS.iterdir()
        if p.is_dir() and (p / "__init__.py").exists()
    }
    assert FRAMEWORK.isdisjoint(PRODUCT), "an app is in both tiers"
    unclassified = on_disk - (FRAMEWORK | PRODUCT)
    assert not unclassified, (
        f"unclassified app(s) {sorted(unclassified)} — add each to FRAMEWORK or "
        "PRODUCT here and in ARCHITECTURE.md"
    )
