"""
DevIn Agent State — Defines the shared state flowing through the LangGraph.

The AgentState is the single source of truth during each agent invocation.
Every node in the graph reads from and writes to this state.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Sequence

from langchain_core.messages import AnyMessage


# Using Annotated with operator.add tells LangGraph to *append* new messages
# to the existing list rather than overwriting it.
# This is critical — it preserves conversation history across graph cycles.
MessageList = Annotated[Sequence[AnyMessage], operator.add]

def _replace_or_add(old: list, new: list) -> list:
    # If new list is empty [], it means reset signal from validator
    if new == []:
        return []
    # Otherwise accumulate
    return old + [x for x in new if x not in old]

def _merge_token_usage(old: dict, new: dict) -> dict:
    """Accumulate token counts across all LLM calls."""
    if not old:
        old = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0}
    return {
        "input_tokens": old.get("input_tokens", 0) + new.get("input_tokens", 0),
        "output_tokens": old.get("output_tokens", 0) + new.get("output_tokens", 0),
        "total_tokens": old.get("total_tokens", 0) + new.get("total_tokens", 0),
        "llm_calls": old.get("llm_calls", 0) + new.get("llm_calls", 0),
    }

@dataclass
class AgentState:
    """
    The state object that flows through the entire LangGraph.

    Attributes:
        messages: Full conversation history (system + human + AI + tool messages).
                  Uses operator.add so new messages are appended, not replaced.
        current_goal: High-level description of what the agent is trying to achieve.
        iteration_count: How many reason→act→observe cycles have occurred.
                         Used to enforce the max-iterations safety cap.
        tool_outputs: Accumulated tool results from the current run.
        error: If the last step produced an error, it's stored here for recovery.
        should_stop: Flag to force-stop the agent loop (set when max iterations hit
                     or the agent decides it's done).
        metadata: Extensible dict for passing arbitrary data between nodes.
    """

    messages: MessageList = field(default_factory=list)
    current_goal: str = ""
    iteration_count: int = 0
    total_steps: int = 0
    project_tree: str = ""
    active_skills: str = ""
    project_rules: str = ""
    verification_feedback: str = ""
    modified_files: Annotated[list[str], _replace_or_add] = field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    should_stop: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    token_usage: Annotated[dict, _merge_token_usage] = field(default_factory=dict)
