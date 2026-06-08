"""Regression tests for memory task extraction filtering and deduplication."""

from langchain_core.messages import HumanMessage, ToolMessage

from devin.agent.memory import MemoryEngine


def test_propose_save_filters_frustration_and_deduplicates_same_file(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))
    messages = [
        HumanMessage(content="create greet.py that prints Good morning"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_1", name="write_file"),
        HumanMessage(content="write greet.py with print('Good morning')"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_2", name="write_file"),
        HumanMessage(content="no, you create it"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_3", name="write_file"),
        HumanMessage(content="do it for me"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_4", name="write_file"),
        HumanMessage(content="you do it"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_5", name="write_file"),
    ]

    summary = memory.propose_save(messages)

    assert "state" in summary
    state = summary["state"].lower()
    assert "created greet.py" in state
    assert state.count("created greet.py") == 1
    assert "no, you create it" not in state
    assert "do it for me" not in state
    assert "you do it" not in state
    assert summary["files_created"] == "greet.py"


def test_propose_save_ignores_short_imperative_without_specifics(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))
    messages = [
        HumanMessage(content="do it"),
        ToolMessage(content="Success: wrote file to throwaway.py", tool_call_id="call_1", name="write_file"),
    ]

    summary = memory.propose_save(messages)

    assert "state" not in summary
    assert "files_created" not in summary
