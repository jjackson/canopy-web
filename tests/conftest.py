import pytest

from apps.collections.models import Collection, Source


@pytest.fixture
def collection(db):
    return Collection.objects.create(
        name="Test Collection",
        description="A test collection of sources",
    )


@pytest.fixture
def source(db, collection):
    return Source.objects.create(
        collection=collection,
        source_type="slack",
        title="Test Slack Thread",
        content="This is a test slack thread content.",
        metadata={"channel": "#general", "thread_ts": "1234567890.123456"},
    )
