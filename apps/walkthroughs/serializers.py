"""DRF serializers for the Walkthrough model."""
from rest_framework import serializers

from .models import Walkthrough


class WalkthroughListItemSerializer(serializers.ModelSerializer):
    owner_email = serializers.CharField(source="owner.email", read_only=True)

    class Meta:
        model = Walkthrough
        fields = [
            "id",
            "title",
            "description",
            "kind",
            "project_slug",
            "visibility",
            "owner_email",
            "size_bytes",
            "duration_sec",
            "created_at",
            "updated_at",
        ]


class WalkthroughDetailSerializer(WalkthroughListItemSerializer):
    """Same as list item, plus share_token (only included when caller
    is owner — view layer enforces that)."""
    share_token = serializers.CharField(read_only=True, allow_null=True)
    content_type = serializers.CharField(read_only=True)
    is_owner = serializers.BooleanField(read_only=True)

    class Meta(WalkthroughListItemSerializer.Meta):
        fields = WalkthroughListItemSerializer.Meta.fields + [
            "share_token",
            "content_type",
            "is_owner",
        ]


class WalkthroughUpdateSerializer(serializers.ModelSerializer):
    """PATCH-able fields only."""

    class Meta:
        model = Walkthrough
        fields = ["title", "description", "project_slug", "visibility"]

    def validate_visibility(self, value):
        if value not in (Walkthrough.VISIBILITY_PRIVATE, Walkthrough.VISIBILITY_LINK):
            raise serializers.ValidationError("invalid visibility")
        return value
