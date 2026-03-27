from .base import BaseAdapter


class OpenClawAdapter(BaseAdapter):
    """Generates an autonomous agent prompt chain from a skill definition."""

    def generate(self, skill_definition: dict) -> dict:
        name = skill_definition.get("name", "unnamed-skill")
        description = skill_definition.get("description", "")
        steps = skill_definition.get("steps", [])

        lines = [
            f"You are an autonomous agent executing the skill: {name}.",
        ]
        if description:
            lines.append(f"Goal: {description}")
        lines.append("")
        lines.append("Follow these steps in order:")

        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"step_{i}")
            step_desc = step.get("description", "")
            tools = step.get("tools", [])
            inputs = step.get("inputs", [])
            outputs = step.get("outputs", [])

            parts = [f"{i}. {step_name}"]
            if step_desc:
                parts.append(f"   - {step_desc}")
            if inputs:
                parts.append(f"   - Inputs: {', '.join(inputs)}")
            if outputs:
                parts.append(f"   - Outputs: {', '.join(outputs)}")
            if tools:
                parts.append(f"   - Tools: {', '.join(tools)}")
            lines.extend(parts)

        system_prompt = "\n".join(lines)
        return {
            "type": "prompt_chain",
            "system_prompt": system_prompt,
        }
