"""Tests for apps.system.reader — the canopy plugin capability reader."""
from __future__ import annotations

import json

import pytest

from apps.system import reader


@pytest.fixture()
def plugin(tmp_path):
    """A minimal fake canopy plugin: 2 'foo-*' skills, 1 singleton, 1 agent, 1 command."""
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"version": "9.9.9"}), encoding="utf-8"
    )

    skills = tmp_path / "skills"
    (skills / "foo-alpha").mkdir(parents=True)
    (skills / "foo-alpha" / "SKILL.md").write_text(
        "---\nname: foo-alpha\ndescription: Does the alpha thing\n---\n\n# Foo Alpha\nBody A.",
        encoding="utf-8",
    )
    (skills / "foo-beta").mkdir(parents=True)
    (skills / "foo-beta" / "SKILL.md").write_text(
        "---\nname: foo-beta\ndescription: |\n  Does the beta\n  thing across lines\n---\n\nBody B.",
        encoding="utf-8",
    )
    (skills / "solo").mkdir(parents=True)
    (skills / "solo" / "SKILL.md").write_text(
        "---\nname: solo\ndescription: A one-off skill\n---\n\nBody S.",
        encoding="utf-8",
    )

    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "echo.md").write_text(
        "---\nname: echo\ndescription: An agent\n---\n\nAgent body.", encoding="utf-8"
    )

    commands = tmp_path / "commands"
    commands.mkdir()
    # Commands carry frontmatter without a name (name = filename).
    (commands / "do-thing.md").write_text(
        "---\ndescription: Run a thing\n---\n\nCommand body.", encoding="utf-8"
    )
    return str(tmp_path)


def test_load_catalog_counts_and_version(plugin):
    reader.load_catalog.cache_clear()
    cat = reader.load_catalog(plugin)
    assert cat["counts"] == {"skill": 3, "agent": 1, "command": 1}
    assert cat["plugin_version"] == "9.9.9"
    assert cat["warning"] is None


def test_family_grouping(plugin):
    reader.load_catalog.cache_clear()
    cat = reader.load_catalog(plugin)
    fam = {i["name"]: i["family"] for i in cat["items"] if i["kind"] == "skill"}
    assert fam["foo-alpha"] == "foo"  # shared prefix -> family
    assert fam["foo-beta"] == "foo"
    assert fam["solo"] == "general"  # singleton -> general
    assert "foo" in cat["families"] and "general" in cat["families"]


def test_multiline_description_is_flattened(plugin):
    reader.load_catalog.cache_clear()
    beta = reader.get_item(plugin, "skill", "foo-beta")
    assert beta is not None
    assert beta["description"] == "Does the beta thing across lines"
    assert beta["body"] == "Body B."


def test_command_name_falls_back_to_filename(plugin):
    reader.load_catalog.cache_clear()
    cmd = reader.get_item(plugin, "command", "do-thing")
    assert cmd is not None
    assert cmd["display_name"] == "Do Thing"
    assert cmd["description"] == "Run a thing"


def test_missing_plugin_degrades_gracefully(tmp_path):
    reader.load_catalog.cache_clear()
    cat = reader.load_catalog(str(tmp_path / "nope"))
    assert cat["items"] == []
    assert cat["warning"]
    assert cat["counts"] == {"skill": 0, "agent": 0, "command": 0}


def test_get_item_unknown_returns_none(plugin):
    reader.load_catalog.cache_clear()
    assert reader.get_item(plugin, "skill", "does-not-exist") is None
