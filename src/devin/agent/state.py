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
    verification_feedback: str = ""
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    should_stop: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
