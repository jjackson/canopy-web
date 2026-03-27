from rest_framework import serializers

from .models import Collection, Source

MAX_SOURCE_SIZE = 1_000_000  # 1MB


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ["id", "source_type", "title", "content", "metadata", "created_at"]

    def validate_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Source content cannot be empty.")
        if len(value) > MAX_SOURCE_SIZE:
            raise serializers.ValidationError(f"Source content exceeds maximum size ({MAX_SOURCE_SIZE} bytes).")
        return value


class CollectionSerializer(serializers.ModelSerializer):
    sources = SourceSerializer(many=True, read_only=True)

    class Meta:
        model = Collection
        fields = ["id", "name", "description", "sources", "created_at", "updated_at"]
