"""
Shared Anthropic client with circuit breaker.

Provides a singleton client instance and a simple circuit breaker
that opens after consecutive failures to prevent cascading errors.
"""
import anthropic
from django.conf import settings

_client = None
_consecutive_failures = 0
_CIRCUIT_BREAKER_THRESHOLD = 5


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def is_circuit_open():
    return _consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD


def record_success():
    global _consecutive_failures
    _consecutive_failures = 0


def record_failure():
    global _consecutive_failures
    _consecutive_failures += 1


async def stream_message(system_prompt, user_message, model="claude-sonnet-4-20250514"):
    if is_circuit_open():
        raise RuntimeError("Anthropic API circuit breaker open")
    client = get_client()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                yield text
        record_success()
    except Exception:
        record_failure()
        raise
