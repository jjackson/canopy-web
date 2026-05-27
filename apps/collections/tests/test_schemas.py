import pytest
from pydantic import ValidationError

from apps.collections.schemas import (
    CollectionCreateIn,
    CollectionOut,
    SourceCreateIn,
    SourceOut,
)


def test_collection_out_round_trip():
    raw = {
        "id": 1,
        "name": "Discovery call — ACME",
        "description": "Notes from 2026-05-20 call",
        "sources": [
            {
                "id": 5,
                "source_type": "transcript",
                "title": "session.jsonl",
                "content": "...",
                "metadata": {"messages": 12},
                "created_at": "2026-05-20T10:00:00Z",
            }
        ],
        "created_at": "2026-05-20T10:00:00Z",
        "updated_at": "2026-05-20T10:00:00Z",
    }
    parsed = CollectionOut.model_validate(raw)
    assert parsed.id == 1
    assert len(parsed.sources) == 1
    assert parsed.sources[0].source_type == "transcript"


def test_collection_create_validates_name():
    with pytest.raises(ValidationError):
        CollectionCreateIn(name="")
    obj = CollectionCreateIn(name="X")
    assert obj.name == "X"


def test_source_create_validates_content_size():
    obj = SourceCreateIn(source_type="text", content="hello")
    assert obj.content == "hello"
    with pytest.raises(ValidationError):
        SourceCreateIn(source_type="text", content="")
    with pytest.raises(ValidationError):
        SourceCreateIn(source_type="text", content="x" * 1_000_001)


def test_source_type_literal():
    with pytest.raises(ValidationError):
        SourceCreateIn(source_type="not-a-real-type", content="x")
