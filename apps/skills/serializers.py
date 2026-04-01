from rest_framework import serializers

from .models import Skill


class SkillSerializer(serializers.ModelSerializer):
    eval_score = serializers.SerializerMethodField()
    eval_trend = serializers.SerializerMethodField()
    last_eval_at = serializers.SerializerMethodField()

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
            "eval_trend",
            "last_eval_at",
            "created_at",
            "updated_at",
        ]

    def get_eval_score(self, obj):
        try:
            latest_run = obj.eval_suite.runs.order_by("-created_at").first()
            return latest_run.overall_score if latest_run else None
        except Exception:
            return None

    def get_eval_trend(self, obj):
        """Return 'improving', 'declining', or 'stable' from last 2 runs."""
        try:
            runs = list(
                obj.eval_suite.runs.order_by("-created_at").values_list(
                    "overall_score", flat=True
                )[:2]
            )
            if len(runs) < 2:
                return None
            current, previous = runs[0], runs[1]
            if current is None or previous is None:
                return None
            if current > previous:
                return "improving"
            elif current < previous:
                return "declining"
            return "stable"
        except Exception:
            return None

    def get_last_eval_at(self, obj):
        try:
            latest_run = obj.eval_suite.runs.order_by("-created_at").first()
            return latest_run.created_at.isoformat() if latest_run else None
        except Exception:
            return None
