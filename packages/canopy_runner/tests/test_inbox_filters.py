"""Framework inbox filters — idempotent apply via gog."""
from types import SimpleNamespace
from canopy_runner import inbox_filters


def test_filters_are_conservative_and_named():
    names = {f["name"] for f in inbox_filters.FILTERS}
    assert "automated-noreply" in names
    for f in inbox_filters.FILTERS:      # every rule must skip inbox + mark read, and have a query
        assert f["query"] and f["archive"] and f["mark_read"]


def _runner(list_json, create_rc=0):
    calls = []
    def run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        if "list" in cmd:
            return SimpleNamespace(returncode=0, stdout=list_json, stderr="")
        return SimpleNamespace(returncode=create_rc, stdout="", stderr="boom" if create_rc else "")
    run.calls = calls
    return run


def test_apply_creates_when_none_exist():
    r = _runner('{"filters": null}')
    res = inbox_filters.apply_filters("hal@x", "canopy", runner=r)
    assert res["applied"] == [f["name"] for f in inbox_filters.FILTERS] and res["skipped"] == []


def test_apply_is_idempotent():
    import json
    existing = json.dumps({"filters": [{"criteria": {"query": f["query"]}} for f in inbox_filters.FILTERS]})
    res = inbox_filters.apply_filters("hal@x", "canopy", runner=_runner(existing))
    assert res["applied"] == [] and len(res["skipped"]) == len(inbox_filters.FILTERS)


def test_apply_raises_on_gog_error():
    import pytest
    with pytest.raises(inbox_filters.FilterError):
        inbox_filters.apply_filters("hal@x", "canopy", runner=_runner('{"filters": null}', create_rc=1))
