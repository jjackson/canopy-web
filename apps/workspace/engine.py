"""
Workspace engine: turn-based session manager.

Handles session creation, prompt building from collection sources,
and AI response parsing for skill extraction.
"""
import json
import re

from apps.collections.models import Source

from .models import WorkspaceSession


class WorkspaceEngine:
    """Core engine for workspace analysis sessions."""

    def __init__(self, collection):
        self.collection = collection

    def create_session(self) -> WorkspaceSession:
        """Create a new workspace session for this collection."""
        return WorkspaceSession.objects.create(collection=self.collection)

    def build_analysis_prompt(self) -> str:
        """
        Build the user-message prompt by concatenating all sources.

        Raises ValueError if the collection has no sources.
        """
        sources = Source.objects.filter(collection=self.collection).order_by("created_at")
        if not sources.exists():
            raise ValueError("Collection has no sources to analyze.")

        parts = []
        for source in sources:
            header = f"--- Source: {source.title or source.get_source_type_display()} ---"
            parts.append(f"{header}\n{source.content}")

        return "\n\n".join(parts)

    def build_re_proposal_prompt(self, current_skill: dict, user_edit: dict) -> str:
        """Build a prompt for re-proposing a skill after a structural edit."""
        return (
            f"Current skill definition:\n{json.dumps(current_skill, indent=2)}\n\n"
            f"User edit:\n{json.dumps(user_edit, indent=2)}"
        )

    @staticmethod
    def parse_ai_response(raw_text: str) -> dict:
        """
        Parse the AI response text into a structured dict.

        Strips markdown code fences if present, parses JSON,
        and validates the required 'approach' key exists.

        Raises ValueError if the response cannot be parsed or is missing
        required keys.
        """
        text = raw_text.strip()

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        fence_pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)
        match = fence_pattern.match(text)
        if match:
            text = match.group(1).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse AI response as JSON: {e}") from e

        if not isinstance(parsed, dict):
            raise ValueError("AI response must be a JSON object.")

        if "approach" not in parsed:
            raise ValueError("AI response missing required 'approach' key.")

        return parsed
