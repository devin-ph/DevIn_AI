"""
DevIn Agent Graph — The core ReAct execution loop built with LangGraph.

This is the heart of DevIn. It implements the Perceive → Plan → Execute → Observe
cycle as a stateful graph. Every user message enters the graph, flows through
reasoning and tool-use nodes, and exits with a final response.

Architecture:
    ┌───────────┐
    │   START   │
    └─────┬─────┘
          │
          ▼
    ┌───────────┐     tool_call     ┌───────────┐
    │   reason  │ ───────────────▶  │    act    │
    │  (LLM)    │                   │  (tools)  │
    └─────┬─────┘                   └─────┬─────┘
          │ no tool_call                  │
          ▼                               │
    ┌───────────┐                         │
    │    END    │  ◀──────────────────────┘
    └───────────┘     (result fed back to reason)
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from devin.agent.llm_provider import create_llm
from devin.agent.prompts import get_system_prompt
from devin.agent.state import AgentState
from devin.settings import settings
from devin.tools.registry import ToolRegistry, create_default_registry

logger = logging.getLogger(__name__)


def should_continue(state: AgentState) -> Literal["act", "__end__"]:
    """
    Routing function: decide whether to call tools or finish.

    Returns "act" if the LLM wants to call a tool.
    Returns END if the LLM gave a final response (no tool calls).
    """
    messages = state["messages"]
    last_message = messages[-1]

    # Check iteration cap
    iteration = state.get("iteration_count", 0)
    if iteration >= settings.devin_max_iterations:
        logger.warning(f"Hit max iterations ({settings.devin_max_iterations}). Forcing stop.")
        return "__end__"

    # If the LLM decided to use a tool, route to the act node
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "act"

    # Otherwise, the LLM gave a final response
    return "__end__"


def reason_node(state: AgentState) -> dict[str, Any]:
    """
    The reasoning node — calls the LLM to think about the next step.

    The LLM sees the full conversation history (including previous tool results)
    and either decides to call a tool or gives a final answer.
    """
    messages = state["messages"]
    iteration = state.get("iteration_count", 0)

    logger.info(f"Reason node — iteration {iteration + 1}")

    # The LLM is bound to tools in build_graph(), so it can choose to call them
    response = _get_bound_llm(state).invoke(messages)

    return {
        "messages": [response],
        "iteration_count": iteration + 1,
    }


def _get_bound_llm(state: AgentState):
    """Get the LLM with tools bound. Cached on the state's metadata."""
    # This will be set by build_graph() and stored in the graph's config
    return state.get("_bound_llm")


def build_graph(
    registry: ToolRegistry | None = None,
    model: str | None = None,
) -> StateGraph:
    """
    Build the complete DevIn agent graph.

    Args:
        registry: Tool registry to use. Defaults to the full Phase 1 toolset.
        model: LLM model name. Defaults to settings.

    Returns:
        A compiled LangGraph ready to invoke.
    """
    if registry is None:
        registry = create_default_registry()

    tools = registry.get_tools()
    llm = create_llm(model=model)

    # Bind tools to the LLM so it knows what's available
    llm_with_tools = llm.bind_tools(tools)

    # Build the system message
    system_message = SystemMessage(content=get_system_prompt())

    # --- Define the graph nodes ---

    def reason(state: dict) -> dict:
        """Call the LLM with the conversation history."""
        messages = state["messages"]
        iteration = state.get("iteration_count", 0)

        # Ensure system message is always first
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [system_message] + list(messages)

        logger.info(f"🧠 Reasoning — iteration {iteration + 1}")

        response = llm_with_tools.invoke(messages)

        return {
            "messages": [response],
            "iteration_count": iteration + 1,
        }

    # ToolNode automatically executes tool calls from the LLM's response
    tool_node = ToolNode(tools)

    # --- Assemble the graph ---

    workflow = StateGraph(dict)

    workflow.add_node("reason", reason)
    workflow.add_node("act", tool_node)

    # Entry point
    workflow.set_entry_point("reason")

    # After reasoning, decide: use a tool or finish?
    workflow.add_conditional_edges(
        "reason",
        _should_continue_edge,
        {
            "act": "act",
            "__end__": END,
        },
    )

    # After acting (tool call), always go back to reasoning
    workflow.add_edge("act", "reason")

    compiled = workflow.compile()
    logger.info(f"✅ Agent graph compiled with {registry.count} tools")

    return compiled


def _should_continue_edge(state: dict) -> Literal["act", "__end__"]:
    """Edge routing function for the compiled graph."""
    messages = state.get("messages", [])
    if not messages:
        return "__end__"

    last_message = messages[-1]
    iteration = state.get("iteration_count", 0)

    if iteration >= settings.devin_max_iterations:
        logger.warning(f"⚠️  Max iterations ({settings.devin_max_iterations}) reached.")
        return "__end__"

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "act"

    return "__end__"


def create_agent(model: str | None = None) -> Any:
    """
    High-level factory: create a ready-to-use DevIn agent.

    Returns a compiled LangGraph that you can invoke with:
        result = agent.invoke({"messages": [HumanMessage(content="Hello")]})

    Or stream with:
        for event in agent.stream({"messages": [HumanMessage(content="Hello")]}):
            ...
    """
    registry = create_default_registry()
    graph = build_graph(registry=registry, model=model)

    logger.info("🚀 DevIn agent created and ready")
    return graph
