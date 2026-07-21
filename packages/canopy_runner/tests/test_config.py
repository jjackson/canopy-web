import json
from pathlib import Path

from canopy_runner.config import Config


def test_load_config_with_token_file(tmp_path: Path):
    token_file = tmp_path / "tok"
    token_file.write_text("sekret\n")
    cfg_file = tmp_path / "runner.json"
    cfg_file.write_text(json.dumps({
        "base_url": "https://labs.example.com/canopy",
        "token": f"@{token_file}",
        "runner_id": "r-1",
        "emdash_db": str(tmp_path / "emdash4.db"),
        "automation_ids": {"echo": "auto-1"},
        "expected_migration_id": 19,
    }))
    cfg = Config.load(cfg_file)
    assert cfg.token == "sekret"
    assert cfg.base_url == "https://labs.example.com/canopy"
    assert cfg.automation_ids["echo"] == "auto-1"
    assert cfg.poll_seconds == 5  # default (low, for snappy turn claims)
