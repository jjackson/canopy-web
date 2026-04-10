from rest_framework import serializers
from .models import Project, ProjectContext


class ProjectContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectContext
        fields = ["id", "context_type", "content", "source", "created_at"]


class ProjectListSerializer(serializers.ModelSerializer):
    latest_context = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "name", "slug", "repo_url", "deploy_url",
            "visibility", "status", "latest_context",
            "created_at", "updated_at",
        ]

    def get_latest_context(self, obj):
        result = {}
        if hasattr(obj, "_prefetched_contexts"):
            contexts = obj._prefetched_contexts
        else:
            contexts = obj.contexts.all()
        seen = set()
        for ctx in contexts:
            if ctx.context_type not in seen:
                seen.add(ctx.context_type)
                result[ctx.context_type] = {
                    "content": ctx.content,
                    "source": ctx.source,
                    "created_at": ctx.created_at.isoformat(),
                }
        return result


class ProjectDetailSerializer(serializers.ModelSerializer):
    contexts = ProjectContextSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "slug", "repo_url", "deploy_url",
            "visibility", "status", "contexts",
            "created_at", "updated_at",
        ]


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["name", "slug", "repo_url", "deploy_url", "visibility", "status"]

    def validate_slug(self, value):
        if Project.objects.filter(slug=value).exists():
            raise serializers.ValidationError("A project with this slug already exists.")
        return value


class ProjectContextCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectContext
        fields = ["context_type", "content", "source"]

    def validate_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Content cannot be empty.")
        return value
