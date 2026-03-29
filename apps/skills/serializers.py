from rest_framework import serializers

from .models import Skill


class SkillSerializer(serializers.ModelSerializer):
    eval_score = serializers.SerializerMethodField()

    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "description",
            "definition",
            "version",
            "usage_count",
            "eval_score",
            "created_at",
            "updated_at",
        ]

    def get_eval_score(self, obj):
        try:
            latest_run = obj.eval_suite.runs.order_by("-created_at").first()
            return latest_run.overall_score if latest_run else None
        except Exception:
            return None
