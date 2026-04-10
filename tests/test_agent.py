# Tests for DevIn agent state and prompts.

from devin.agent.state import AgentState
from devin.agent.prompts import get_system_prompt


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

    def test_system_prompt_contains_identity(self):
        prompt = get_system_prompt()
        assert "DevIn" in prompt
        assert "ReAct" in prompt

    def test_system_prompt_contains_rules(self):
        prompt = get_system_prompt()
        assert "Safety" in prompt
        assert "confirmation" in prompt.lower()

    def test_system_prompt_has_timestamp(self):
        prompt = get_system_prompt()
        assert "Current Time:" in prompt
