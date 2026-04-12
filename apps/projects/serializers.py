from rest_framework import serializers
from .models import Project, ProjectAction, ProjectContext, ProjectGuide


class ProjectContextSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectContext
        fields = ["id", "context_type", "content", "source", "created_at"]


class ProjectListSerializer(serializers.ModelSerializer):
    latest_context = serializers.SerializerMethodField()
    has_guide = serializers.SerializerMethodField()
    latest_actions = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "name", "slug", "repo_url", "deploy_url",
            "visibility", "status", "skills", "has_guide",
            "latest_context", "latest_actions",
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

    def get_has_guide(self, obj):
        return hasattr(obj, "guide")

    def get_latest_actions(self, obj):
        """Return the most recent action per skill_name."""
        if hasattr(obj, "_prefetched_actions"):
            actions = obj._prefetched_actions
        else:
            actions = obj.actions.all()
        result = {}
        seen = set()
        for action in actions:
            if action.skill_name not in seen:
                seen.add(action.skill_name)
                result[action.skill_name] = {
                    "status": action.status,
                    "started_at": action.started_at.isoformat(),
                    "completed_at": action.completed_at.isoformat() if action.completed_at else None,
                }
        return result


class ProjectDetailSerializer(serializers.ModelSerializer):
    contexts = ProjectContextSerializer(many=True, read_only=True)
    has_guide = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "name", "slug", "repo_url", "deploy_url",
            "visibility", "status", "skills", "has_guide", "contexts",
            "created_at", "updated_at",
        ]

    def get_has_guide(self, obj):
        return hasattr(obj, "guide")


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["name", "slug", "repo_url", "deploy_url", "visibility", "status", "skills"]

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


class ProjectGuideSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectGuide
        fields = ["content", "source", "created_at", "updated_at"]


class ProjectActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectAction
        fields = ["id", "skill_name", "session_id", "status", "started_at", "completed_at", "duration_ms", "notes", "created_at"]


class ProjectActionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectAction
        fields = ["skill_name", "session_id", "status", "started_at", "completed_at", "duration_ms", "notes"]

    def validate_skill_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Skill name cannot be empty.")
        return value
