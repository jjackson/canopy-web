"""
SSE streaming functions for workspace analysis.

Provides server-sent event formatting and async generators
for streaming AI analysis results to the client.
"""
import json
import logging

from apps.common.anthropic_client import stream_message

from .prompts import RE_PROPOSAL_SYSTEM_PROMPT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def sse_event(data: dict) -> str:
    """Format a dict as a server-sent event string."""
    return f"data: {json.dumps(data)}\n\n"


async def stream_workspace_analysis(engine, session):
    """
    Stream the initial workspace analysis as SSE events.

    Yields SSE events in order:
    1. status - analysis has started
    2. text_delta - chunks of text as they arrive from the LLM
    3. proposal - the parsed JSON proposal (approach + eval_cases)
    4. done - analysis is complete

    On error, resets session status and yields an error event.
    """
    try:
        session.status = "analyzing"
        session.save(update_fields=["status"])

        yield sse_event({"type": "status", "status": "analyzing"})

        user_message = engine.build_analysis_prompt()
        full_text = ""

        async for chunk in stream_message(SYSTEM_PROMPT, user_message):
            full_text += chunk
            yield sse_event({"type": "text_delta", "delta": chunk})

        parsed = engine.parse_ai_response(full_text)

        session.proposed_approach = parsed.get("approach", {})
        session.proposed_eval_cases = parsed.get("eval_cases", [])
        session.status = "proposed"
        session.save(update_fields=["status", "proposed_approach", "proposed_eval_cases"])

        yield sse_event({"type": "proposal", "data": parsed})
        yield sse_event({"type": "done"})

    except Exception as e:
        logger.exception("Error during workspace analysis")
        session.status = "created"
        session.save(update_fields=["status"])
        yield sse_event({"type": "error", "message": str(e)})


async def stream_re_proposal(engine, session, user_edit):
    """
    Stream a re-proposal after a structural edit as SSE events.

    Similar to stream_workspace_analysis but uses the re-proposal prompt
    with the current skill definition and user's edit.
    """
    try:
        session.status = "analyzing"
        session.save(update_fields=["status"])

        yield sse_event({"type": "status", "status": "analyzing"})

        current_skill = {
            "approach": session.proposed_approach,
            "eval_cases": session.proposed_eval_cases,
        }
        user_message = engine.build_re_proposal_prompt(current_skill, user_edit)
        full_text = ""

        async for chunk in stream_message(RE_PROPOSAL_SYSTEM_PROMPT, user_message):
            full_text += chunk
            yield sse_event({"type": "text_delta", "delta": chunk})

        parsed = engine.parse_ai_response(full_text)

        session.proposed_approach = parsed.get("approach", {})
        session.proposed_eval_cases = parsed.get("eval_cases", [])
        session.edit_history.append(user_edit)
        session.status = "proposed"
        session.save(update_fields=["status", "proposed_approach", "proposed_eval_cases", "edit_history"])

        yield sse_event({"type": "proposal", "data": parsed})
        yield sse_event({"type": "done"})

    except Exception as e:
        logger.exception("Error during re-proposal")
        session.status = "proposed"
        session.save(update_fields=["status"])
        yield sse_event({"type": "error", "message": str(e)})
