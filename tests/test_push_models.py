"""A push subscription is one browser we can reach. One user has many (phone,
laptop, a reinstall), and the browser's endpoint URL is the natural identity."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError

from apps.push.models import PushSubscription

pytestmark = pytest.mark.django_db


@pytest.fixture()
def user():
    return User.objects.create_user("jj", "jj@dimagi.com", "pw")


def test_a_user_can_have_several_subscriptions(user):
    PushSubscription.objects.create(
        user=user, endpoint="https://fcm.googleapis.com/fcm/send/AAA", p256dh="k1", auth="a1"
    )
    PushSubscription.objects.create(
        user=user, endpoint="https://fcm.googleapis.com/fcm/send/BBB", p256dh="k2", auth="a2"
    )
    assert user.push_subscriptions.count() == 2


def test_the_same_endpoint_cannot_be_registered_twice(user):
    """The browser re-sends the same endpoint on every subscribe() call, so the
    endpoint is the identity — a second insert must not create a duplicate that
    would double-push the same device."""
    PushSubscription.objects.create(
        user=user, endpoint="https://fcm.googleapis.com/fcm/send/AAA", p256dh="k1", auth="a1"
    )
    with pytest.raises(IntegrityError):
        PushSubscription.objects.create(
            user=user, endpoint="https://fcm.googleapis.com/fcm/send/AAA", p256dh="k2", auth="a2"
        )
