from .base import BaseAdapter


class WebAdapter(BaseAdapter):
    """Generates a guided workflow UI representation from a skill definition."""

    def generate(self, skill_definition: dict) -> dict:
        steps = skill_definition.get("steps", [])
        ui_steps = []
        for step in steps:
            ui_steps.append({
                "name": step.get("name", ""),
                "label": step.get("description", ""),
                "inputs": step.get("inputs", []),
                "outputs": step.get("outputs", []),
                "tools": step.get("tools", []),
            })
        return {
            "type": "guided_workflow",
            "ui_steps": ui_steps,
        }
