# Tests for DevIn agent state and prompts.

from langchain_core.messages import AIMessage
from devin.agent.graph import architect_should_continue
from devin.agent.prompts import get_architect_prompt, get_editor_prompt
from devin.agent.state import AgentState


class TestAgentState:
    """Tests for the agent state definition."""

    def test_default_state(self):
        state = AgentState()
        assert state.messages == []
        assert state.current_goal == ""
        assert state.iteration_count == 0
        assert state.should_stop is False
        assert state.error is None

    def test_state_with_values(self):
        state = AgentState(
            current_goal="Find weather",
            iteration_count=3,
        )
        assert state.current_goal == "Find weather"
        assert state.iteration_count == 3


class TestPrompts:
    """Tests for the prompt generation."""

    def test_architect_prompt_contains_identity(self):
        prompt = get_architect_prompt()
        assert "DevIn" in prompt
        assert "Architect" in prompt

    def test_architect_prompt_contains_rules(self):
        prompt = get_architect_prompt()
        assert "RULES" in prompt
        assert "read-only tools" in prompt

    def test_architect_prompt_has_timestamp(self):
        prompt = get_architect_prompt()
        assert "Time" in prompt

    def test_editor_prompt_contains_identity(self):
        prompt = get_editor_prompt()
        assert "DevIn" in prompt
        assert "Editor" in prompt

    def test_editor_prompt_contains_rules(self):
        prompt = get_editor_prompt()
        assert "EXECUTE" in prompt
        assert "tools" in prompt

    def test_editor_prompt_has_timestamp(self):
        prompt = get_editor_prompt()
        assert "Time" in prompt
