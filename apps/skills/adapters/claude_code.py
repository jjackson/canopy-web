from .base import BaseAdapter


class ClaudeCodeAdapter(BaseAdapter):
    """Generates a Claude Code skill definition (markdown-based) from a skill definition."""

    def generate(self, skill_definition: dict) -> dict:
        name = skill_definition.get("name", "unnamed-skill")
        description = skill_definition.get("description", "")
        steps = skill_definition.get("steps", [])

        lines = [f"# {name}", ""]
        if description:
            lines.append(description)
            lines.append("")

        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"step_{i}")
            step_desc = step.get("description", "")
            tools = step.get("tools", [])
            inputs = step.get("inputs", [])
            outputs = step.get("outputs", [])

            lines.append(f"## Step {i}: {step_name}")
            if step_desc:
                lines.append(step_desc)
            if inputs:
                lines.append(f"Inputs: {', '.join(inputs)}")
            if outputs:
                lines.append(f"Outputs: {', '.join(outputs)}")
            if tools:
                lines.append(f"Tools: {', '.join(tools)}")
            lines.append("")

        content = "\n".join(lines)
        return {
            "type": "skill",
            "entry": f"/{name}",
            "content": content,
        }
