"""Read the canopy plugin's capability surface (skills / agents / commands).

The plugin file structure is the source of truth — nothing is hardcoded here.
At runtime this walks ``CANOPY_PLUGIN_PATH`` and parses the YAML frontmatter of
each ``skills/<name>/SKILL.md``, ``agents/<name>.md``, and ``commands/<name>.md``
into a flat catalog grouped by name-prefix "family".

No Django imports — pure functions over a path, so they're unit-testable.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter delimited by ``---``. Returns (meta, body)."""
    if not text:
        return {}, ""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw_yaml, body = m.group(1), m.group(2)
    try:
        meta = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        logger.warning("Invalid YAML frontmatter — treating as none")
        return {}, text
    return (meta if isinstance(meta, dict) else {}), body


def _display_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _first_paragraph(body: str) -> str:
    for block in re.split(r"\n\s*\n", body.strip()):
        block = block.strip()
        if block and not block.startswith("#"):
            return " ".join(block.split())
    return ""


def _clean_desc(raw) -> str:
    if not raw:
        return ""
    return " ".join(str(raw).split())


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _skill_items(plugin: Path) -> list[dict]:
    out: list[dict] = []
    skills_dir = plugin / "skills"
    if not skills_dir.is_dir():
        return out
    for sub in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        md = sub / "SKILL.md"
        if not md.is_file():
            continue
        meta, body = parse_frontmatter(_read(md))
        name = str(meta.get("name") or sub.name)
        out.append(
            {
                "name": name,
                "kind": "skill",
                "display_name": _display_name(name),
                "description": _clean_desc(meta.get("description")) or _first_paragraph(body),
                "body": body.strip(),
            }
        )
    return out


def _flat_md_items(plugin: Path, subdir: str, kind: str) -> list[dict]:
    out: list[dict] = []
    d = plugin / subdir
    if not d.is_dir():
        return out
    for md in sorted(d.glob("*.md")):
        meta, body = parse_frontmatter(_read(md))
        name = str(meta.get("name") or md.stem)
        out.append(
            {
                "name": name,
                "kind": kind,
                "display_name": _display_name(name),
                "description": _clean_desc(meta.get("description")) or _first_paragraph(body),
                "body": body.strip(),
            }
        )
    return out


def _assign_families(items: list[dict]) -> list[str]:
    """Family = first hyphen segment when shared by >= 2 skills, else 'general'.

    Computed only over skills (agents/commands get their own kind grouping in
    the UI), so the families list stays meaningful.
    """
    seg_counts = Counter(
        i["name"].split("-", 1)[0] for i in items if i["kind"] == "skill"
    )
    families: set[str] = set()
    for i in items:
        seg = i["name"].split("-", 1)[0]
        fam = seg if (i["kind"] == "skill" and seg_counts[seg] >= 2) else "general"
        i["family"] = fam
        if i["kind"] == "skill":
            families.add(fam)
    return sorted(families)


def _plugin_version(plugin: Path) -> str | None:
    pj = plugin / ".claude-plugin" / "plugin.json"
    if not pj.is_file():
        return None
    try:
        return json.loads(_read(pj)).get("version")
    except (json.JSONDecodeError, AttributeError):
        return None


@lru_cache(maxsize=8)
def load_catalog(plugin_path: str) -> dict:
    """Return the full capability catalog dict for a plugin path.

    Shape: ``{items, families, counts, plugin_version, warning}``. Never raises
    for a missing/empty path — returns an empty catalog with a ``warning`` so
    the surface degrades gracefully instead of 500ing.
    """
    plugin = Path(plugin_path)
    if not plugin.is_dir():
        return {
            "items": [],
            "families": [],
            "counts": {"skill": 0, "agent": 0, "command": 0},
            "plugin_version": None,
            "warning": f"Canopy plugin not found at {plugin_path}",
        }

    items = (
        _skill_items(plugin)
        + _flat_md_items(plugin, "agents", "agent")
        + _flat_md_items(plugin, "commands", "command")
    )
    families = _assign_families(items)
    counts = Counter(i["kind"] for i in items)
    return {
        "items": items,
        "families": families,
        "counts": {
            "skill": counts.get("skill", 0),
            "agent": counts.get("agent", 0),
            "command": counts.get("command", 0),
        },
        "plugin_version": _plugin_version(plugin),
        "warning": None if items else "Canopy plugin contained no skills/agents/commands",
    }


def get_item(plugin_path: str, kind: str, name: str) -> dict | None:
    for item in load_catalog(plugin_path)["items"]:
        if item["kind"] == kind and item["name"] == name:
            return item
    return None
