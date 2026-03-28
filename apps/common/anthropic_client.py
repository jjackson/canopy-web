"""
AI client abstraction — supports two backends:

  AI_BACKEND=api  → Direct Anthropic Python SDK (requires ANTHROPIC_API_KEY)
  AI_BACKEND=cli  → Claude Code CLI (uses local `claude` binary authentication)

Both backends expose the same interface: `call_ai()` for synchronous calls
and `stream_message()` for SSE streaming.
"""
import json
import logging
import os
import subprocess

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

_client = None
_consecutive_failures = 0
_CIRCUIT_BREAKER_THRESHOLD = 5


def _get_backend():
    return getattr(settings, "AI_BACKEND", "api")


# --- Circuit breaker (shared across backends) ---

def is_circuit_open():
    return _consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD


def record_success():
    global _consecutive_failures
    _consecutive_failures = 0


def record_failure():
    global _consecutive_failures
    _consecutive_failures += 1


# --- API backend (direct Anthropic SDK) ---

def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _api_call(system_prompt, user_message, model="claude-sonnet-4-20250514", max_tokens=4096):
    client = get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


async def _api_stream(system_prompt, user_message, model="claude-sonnet-4-20250514"):
    client = get_client()
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# --- CLI backend (claude code CLI) ---

def _cli_call(system_prompt, user_message, max_tokens=4096):
    """Call Claude Code CLI using subscription login (not API key).
    Runs without --bare so it uses OAuth/token auth from claude login."""
    combined_prompt = f"{system_prompt}\n\n{user_message}"

    # Strip ANTHROPIC_API_KEY from env so CLI uses subscription login, not API key
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=combined_prompt,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed (exit {result.returncode}): {result.stderr[:500]}")
        return result.stdout
    except FileNotFoundError:
        raise RuntimeError(
            "Claude Code CLI not found. Install it or set AI_BACKEND=api with an ANTHROPIC_API_KEY."
        )


async def _cli_stream(system_prompt, user_message):
    """Call Claude Code CLI and yield the full response as a single chunk.
    True streaming from the CLI would require reading stdout line-by-line,
    but for V1 this is simpler and still works with the SSE protocol."""
    text = _cli_call(system_prompt, user_message)
    yield text


# --- CLI auth helpers ---

def cli_auth_status():
    """Check if Claude CLI is authenticated. Returns dict with status info."""
    try:
        result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True, text=True, timeout=10,
            env={k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"},
        )
        output = (result.stdout + result.stderr).strip()
        logged_in = result.returncode == 0 and "not logged in" not in output.lower()
        return {
            "installed": True,
            "logged_in": logged_in,
            "output": output,
        }
    except FileNotFoundError:
        return {"installed": False, "logged_in": False, "output": "claude CLI not found"}
    except Exception as e:
        return {"installed": True, "logged_in": False, "output": str(e)}


def cli_start_login():
    """Start the Claude CLI login flow. Returns the auth URL for the user to visit."""
    try:
        # claude auth login prints a URL and waits for the user to complete OAuth
        # We run it with a short timeout to capture the URL, then let it run in background
        result = subprocess.run(
            ["claude", "auth", "login"],
            capture_output=True, text=True, timeout=10,
            env={k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"},
        )
        output = (result.stdout + result.stderr).strip()
        return {"output": output, "success": result.returncode == 0}
    except subprocess.TimeoutExpired as e:
        # Login is interactive — capture whatever URL was printed
        output = ""
        if e.stdout:
            output = e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout
        if e.stderr:
            output += e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
        return {"output": output.strip(), "success": False, "waiting": True}
    except FileNotFoundError:
        return {"output": "claude CLI not found", "success": False}


# --- Public interface ---

def call_ai(system_prompt, user_message, model="claude-sonnet-4-20250514", max_tokens=4096):
    """Synchronous AI call. Returns the response text."""
    if is_circuit_open():
        raise RuntimeError("AI circuit breaker open — too many consecutive failures")

    backend = _get_backend()
    try:
        if backend == "cli":
            result = _cli_call(system_prompt, user_message, max_tokens)
        else:
            result = _api_call(system_prompt, user_message, model, max_tokens)
        record_success()
        return result
    except Exception:
        record_failure()
        raise


async def stream_message(system_prompt, user_message, model="claude-sonnet-4-20250514"):
    """Async streaming AI call. Yields text chunks."""
    if is_circuit_open():
        raise RuntimeError("AI circuit breaker open — too many consecutive failures")

    backend = _get_backend()
    try:
        if backend == "cli":
            async for chunk in _cli_stream(system_prompt, user_message):
                yield chunk
        else:
            async for chunk in _api_stream(system_prompt, user_message, model):
                yield chunk
        record_success()
    except Exception:
        record_failure()
        raise
