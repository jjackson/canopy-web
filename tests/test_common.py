"""Tests for apps.common utilities (envelope + anthropic_client circuit breaker)."""
import pytest

from apps.common import anthropic_client, envelope


class TestSuccessResponse:
    def test_returns_correct_shape(self):
        envelope.start_timing()
        resp = envelope.success_response({"items": [1, 2, 3]})

        assert resp["success"] is True
        assert resp["data"] == {"items": [1, 2, 3]}
        assert "timing_ms" in resp
        assert isinstance(resp["timing_ms"], int)
        assert resp["timing_ms"] >= 0

    def test_includes_warnings_when_provided(self):
        envelope.start_timing()
        resp = envelope.success_response({"ok": True}, warnings=["Deprecation notice"])

        assert resp["warnings"] == ["Deprecation notice"]

    def test_omits_warnings_when_none(self):
        envelope.start_timing()
        resp = envelope.success_response({"ok": True})

        assert "warnings" not in resp


class TestErrorResponse:
    def test_returns_correct_shape(self):
        envelope.start_timing()
        resp = envelope.error_response("NOT_FOUND", "Resource not found", status=404)

        assert resp["success"] is False
        assert resp["error"]["code"] == "NOT_FOUND"
        assert resp["error"]["message"] == "Resource not found"
        assert "timing_ms" in resp
        assert isinstance(resp["timing_ms"], int)
        assert resp["timing_ms"] >= 0

    def test_default_status(self):
        envelope.start_timing()
        # status is accepted but not included in the envelope dict;
        # it's meant for the HTTP layer. Just verify no crash.
        resp = envelope.error_response("BAD_REQUEST", "Invalid input")
        assert resp["success"] is False


class TestCircuitBreaker:
    @pytest.fixture(autouse=True)
    def reset_circuit(self):
        """Reset circuit breaker state before each test."""
        anthropic_client._consecutive_failures = 0
        yield
        anthropic_client._consecutive_failures = 0

    def test_circuit_starts_closed(self):
        assert anthropic_client.is_circuit_open() is False

    def test_circuit_opens_after_threshold_failures(self):
        for _ in range(anthropic_client._CIRCUIT_BREAKER_THRESHOLD):
            anthropic_client.record_failure()

        assert anthropic_client.is_circuit_open() is True

    def test_circuit_stays_closed_below_threshold(self):
        for _ in range(anthropic_client._CIRCUIT_BREAKER_THRESHOLD - 1):
            anthropic_client.record_failure()

        assert anthropic_client.is_circuit_open() is False

    def test_record_success_resets_failures(self):
        for _ in range(anthropic_client._CIRCUIT_BREAKER_THRESHOLD - 1):
            anthropic_client.record_failure()

        anthropic_client.record_success()
        assert anthropic_client.is_circuit_open() is False

        # Even after more failures, need full threshold again
        for _ in range(anthropic_client._CIRCUIT_BREAKER_THRESHOLD - 1):
            anthropic_client.record_failure()
        assert anthropic_client.is_circuit_open() is False

    def test_record_success_resets_after_open(self):
        for _ in range(anthropic_client._CIRCUIT_BREAKER_THRESHOLD):
            anthropic_client.record_failure()
        assert anthropic_client.is_circuit_open() is True

        anthropic_client.record_success()
        assert anthropic_client.is_circuit_open() is False
