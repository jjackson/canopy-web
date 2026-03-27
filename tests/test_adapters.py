import pytest

from apps.skills.adapters import get_adapter
from apps.skills.adapters.claude_code import ClaudeCodeAdapter
from apps.skills.adapters.open_claw import OpenClawAdapter
from apps.skills.adapters.web import WebAdapter

SAMPLE_SKILL = {
    "name": "crispr-analysis",
    "description": "Analyze CRISPR data using evidence synthesis",
    "steps": [
        {
            "name": "gather_evidence",
            "description": "Collect relevant studies",
            "tools": ["web_search"],
            "inputs": ["topic"],
            "outputs": ["evidence_set"],
        },
        {
            "name": "synthesize",
            "description": "Produce analysis",
            "tools": ["llm_reasoning"],
            "inputs": ["evidence_set"],
            "outputs": ["draft"],
        },
        {
            "name": "review",
            "description": "Adversarial review",
            "tools": ["llm_reasoning"],
            "inputs": ["draft"],
            "outputs": ["final"],
        },
    ],
}


class TestWebAdapter:
    def test_generates_ui_steps_matching_skill_steps(self):
        adapter = WebAdapter()
        result = adapter.generate(SAMPLE_SKILL)

        assert result["type"] == "guided_workflow"
        assert len(result["ui_steps"]) == 3

        step = result["ui_steps"][0]
        assert step["name"] == "gather_evidence"
        assert step["label"] == "Collect relevant studies"
        assert step["inputs"] == ["topic"]
        assert step["outputs"] == ["evidence_set"]
        assert step["tools"] == ["web_search"]

    def test_ui_steps_preserve_order(self):
        adapter = WebAdapter()
        result = adapter.generate(SAMPLE_SKILL)
        names = [s["name"] for s in result["ui_steps"]]
        assert names == ["gather_evidence", "synthesize", "review"]

    def test_empty_steps(self):
        adapter = WebAdapter()
        result = adapter.generate({"name": "empty", "steps": []})
        assert result["type"] == "guided_workflow"
        assert result["ui_steps"] == []


class TestClaudeCodeAdapter:
    def test_generates_markdown_with_skill_name_and_steps(self):
        adapter = ClaudeCodeAdapter()
        result = adapter.generate(SAMPLE_SKILL)

        assert result["type"] == "skill"
        assert result["entry"] == "/crispr-analysis"
        assert "# crispr-analysis" in result["content"]
        assert "gather_evidence" in result["content"]
        assert "synthesize" in result["content"]
        assert "review" in result["content"]

    def test_content_includes_description(self):
        adapter = ClaudeCodeAdapter()
        result = adapter.generate(SAMPLE_SKILL)
        assert "Analyze CRISPR data using evidence synthesis" in result["content"]

    def test_content_includes_tools_and_io(self):
        adapter = ClaudeCodeAdapter()
        result = adapter.generate(SAMPLE_SKILL)
        assert "web_search" in result["content"]
        assert "topic" in result["content"]
        assert "evidence_set" in result["content"]


class TestOpenClawAdapter:
    def test_generates_system_prompt_referencing_skill_name(self):
        adapter = OpenClawAdapter()
        result = adapter.generate(SAMPLE_SKILL)

        assert result["type"] == "prompt_chain"
        assert "crispr-analysis" in result["system_prompt"]
        assert "autonomous agent" in result["system_prompt"]

    def test_system_prompt_includes_steps(self):
        adapter = OpenClawAdapter()
        result = adapter.generate(SAMPLE_SKILL)
        assert "gather_evidence" in result["system_prompt"]
        assert "synthesize" in result["system_prompt"]
        assert "review" in result["system_prompt"]

    def test_system_prompt_includes_description(self):
        adapter = OpenClawAdapter()
        result = adapter.generate(SAMPLE_SKILL)
        assert "Analyze CRISPR data using evidence synthesis" in result["system_prompt"]


class TestGetAdapter:
    def test_get_web_adapter(self):
        adapter = get_adapter("web")
        assert isinstance(adapter, WebAdapter)

    def test_get_claude_code_adapter(self):
        adapter = get_adapter("claude_code")
        assert isinstance(adapter, ClaudeCodeAdapter)

    def test_get_open_claw_adapter(self):
        adapter = get_adapter("open_claw")
        assert isinstance(adapter, OpenClawAdapter)

    def test_unknown_runtime_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown runtime"):
            get_adapter("unknown_runtime")
