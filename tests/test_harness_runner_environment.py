import pytest

from apps.harness.models import Runner

pytestmark = pytest.mark.django_db


def test_runner_defaults_local_emdash():
    r = Runner.objects.create(name="laptop")
    assert r.location == Runner.LOCAL
    assert r.engine == Runner.ENGINE_EMDASH


def test_runner_can_be_cloud():
    r = Runner.objects.create(name="cloud-1", location=Runner.CLOUD)
    assert r.location == Runner.CLOUD
