from rest_framework import serializers

from .models import EvalCase, EvalRun, EvalSuite


class EvalCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalCase
        fields = ["id", "name", "input_data", "expected_output", "source_excerpt", "created_at"]


class EvalRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalRun
        fields = ["id", "status", "results", "overall_score", "runtime", "created_at"]


class EvalSuiteSerializer(serializers.ModelSerializer):
    cases = EvalCaseSerializer(many=True, read_only=True)
    runs = EvalRunSerializer(many=True, read_only=True)

    class Meta:
        model = EvalSuite
        fields = ["id", "cases", "runs", "created_at"]
