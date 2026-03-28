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

_clean_env = None

def _get_clean_env():
    """Env dict without ANTHROPIC_API_KEY so CLI uses subscription login."""
    global _clean_env
    if _clean_env is None:
        _clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    return _clean_env


# Holds the in-progress login process between HTTP requests
_login_process = None


def cli_auth_status():
    """Check if Claude CLI is authenticated. Returns dict with status info."""
    try:
        result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True, text=True, timeout=10,
            env=_get_clean_env(),
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
    """Start the Claude CLI login flow.
    Launches `claude auth login` as a background process with stdin pipe.
    Returns the auth URL. The process stays alive waiting for the auth code on stdin.
    Call cli_submit_login_code() to complete the flow."""
    import re
    import threading
    global _login_process

    # Kill any existing login process
    if _login_process and _login_process.poll() is None:
        _login_process.kill()
        _login_process = None

    try:
        proc = subprocess.Popen(
            ["claude", "auth", "login"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_get_clean_env(),
        )
        _login_process = proc

        # Read stdout in a thread to capture the URL without blocking
        output_lines = []

        def reader(pipe, dest):
            for line in iter(pipe.readline, ''):
                dest.append(line)
            pipe.close()

        t_out = threading.Thread(target=reader, args=(proc.stdout, output_lines), daemon=True)
        t_out.start()

        # Wait briefly for the URL to appear
        t_out.join(timeout=8)

        output = "".join(output_lines)
        url_match = re.search(r'(https://claude\.com/[^\s]+)', output)

        return {
            "url": url_match.group(1) if url_match else None,
            "output": output.strip(),
            "waiting_for_code": True,
        }
    except FileNotFoundError:
        return {"url": None, "output": "claude CLI not found", "waiting_for_code": False}
    except Exception as e:
        return {"url": None, "output": str(e), "waiting_for_code": False}


def cli_submit_login_code(code):
    """Submit the OAuth code to the waiting `claude auth login` process.
    Returns success/failure after the process completes."""
    global _login_process

    if not _login_process or _login_process.poll() is not None:
        return {"success": False, "output": "No login process waiting. Start login first."}

    try:
        # Write the code to stdin and close it
        _login_process.stdin.write(code.strip() + "\n")
        _login_process.stdin.flush()
        _login_process.stdin.close()

        # Wait for the process to finish
        _login_process.wait(timeout=15)

        stderr = _login_process.stderr.read() if _login_process.stderr else ""
        success = _login_process.returncode == 0
        _login_process = None

        # Verify auth status
        status = cli_auth_status()

        return {
            "success": status["logged_in"],
            "output": stderr.strip() if stderr.strip() else ("Login successful" if status["logged_in"] else "Login may have failed"),
        }
    except subprocess.TimeoutExpired:
        _login_process.kill()
        _login_process = None
        return {"success": False, "output": "Login process timed out after submitting code."}
    except Exception as e:
        _login_process = None
        return {"success": False, "output": str(e)}


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
