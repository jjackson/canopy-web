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

def _get_clean_env():
    """Env dict without ANTHROPIC_API_KEY so CLI uses subscription login."""
    return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}


# Holds the pty master fd and process for the in-progress login
_login_master_fd = None
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
    """Start the Claude CLI login flow using a pseudo-TTY.
    `claude setup-token` needs a TTY to render its TUI.
    We use pty to provide one, read the OAuth URL, and keep the process alive
    so we can feed the auth code back later via cli_submit_login_code()."""
    import pty
    import re
    import select
    import time
    global _login_process, _login_master_fd

    # Kill any existing login process
    if _login_process is not None:
        try:
            _login_process.kill()
        except Exception:
            pass
        _login_process = None
    if _login_master_fd is not None:
        try:
            os.close(_login_master_fd)
        except Exception:
            pass
        _login_master_fd = None

    try:
        master, slave = pty.openpty()
        proc = subprocess.Popen(
            ["claude", "setup-token"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
            env=_get_clean_env(),
        )
        os.close(slave)

        _login_process = proc
        _login_master_fd = master

        # Read output for up to 12 seconds to capture the OAuth URL
        output = b""
        for _ in range(120):
            if select.select([master], [], [], 0.1)[0]:
                try:
                    output += os.read(master, 4096)
                except OSError:
                    break
            time.sleep(0.1)

        # Strip ANSI escape codes and control characters
        clean = re.sub(rb'\x1b\[[0-9;]*[a-zA-Z]|\x1b\[\?[0-9]*[hl]', b'', output)
        text = clean.decode(errors="replace")
        # Remove control chars but keep newlines/spaces for line-by-line search
        text = re.sub(r'[^\x20-\x7E\n]', '', text)
        # Find URL fragments across lines and reconstruct
        lines = text.split('\n')
        url = None
        url_building = False
        url_parts = []
        for line in lines:
            stripped = line.strip()
            if 'https://claude.com/' in stripped:
                url_building = True
                url_parts = [stripped[stripped.index('https://'):]]
            elif url_building and stripped and not any(c in stripped for c in ['>', '<', ' ']):
                url_parts.append(stripped)
            elif url_building:
                # Line has spaces or other chars — URL ended on previous line
                break
        if url_parts:
            raw_url = ''.join(url_parts)
            # Trim any trailing text that's not part of the URL
            # The state param value is base64url: [A-Za-z0-9_-]
            m = re.match(r'(https://claude\.com/cai/oauth/authorize\?.*?&state=[A-Za-z0-9_\-]+)', raw_url)
            url = m.group(1) if m else raw_url
        url_match = url

        return {
            "url": url_match if url_match else None,
            "output": "Login started. Visit the URL, authenticate, and paste the code back.",
            "waiting_for_code": True,
        }
    except FileNotFoundError:
        return {"url": None, "output": "claude CLI not found", "waiting_for_code": False}
    except Exception as e:
        logger.exception("Failed to start login")
        return {"url": None, "output": str(e), "waiting_for_code": False}


def cli_submit_login_code(code):
    """Submit the OAuth code to the waiting `claude setup-token` process via its PTY."""
    import select
    import time
    global _login_process, _login_master_fd

    if _login_process is None or _login_master_fd is None:
        return {"success": False, "output": "No login process waiting. Click Login first."}

    if _login_process.poll() is not None:
        _login_process = None
        _login_master_fd = None
        return {"success": False, "output": "Login process exited. Click Login to restart."}

    try:
        # Write the code to the PTY (simulates keyboard input)
        os.write(_login_master_fd, (code.strip() + "\n").encode())

        # Wait for the process to finish (up to 15 seconds)
        for _ in range(150):
            # Drain any output
            if select.select([_login_master_fd], [], [], 0.1)[0]:
                try:
                    os.read(_login_master_fd, 4096)
                except OSError:
                    break

            if _login_process.poll() is not None:
                break
            time.sleep(0.1)

        # Clean up
        try:
            os.close(_login_master_fd)
        except OSError:
            pass
        _login_master_fd = None

        exited = _login_process.poll() is not None
        _login_process = None

        # Check if we're now logged in
        status = cli_auth_status()
        return {
            "success": status["logged_in"],
            "output": "Login successful!" if status["logged_in"] else "Code submitted but login didn't complete. Try again.",
        }
    except Exception as e:
        # Clean up on error
        try:
            if _login_master_fd is not None:
                os.close(_login_master_fd)
        except OSError:
            pass
        if _login_process is not None:
            try:
                _login_process.kill()
            except Exception:
                pass
        _login_process = None
        _login_master_fd = None
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
