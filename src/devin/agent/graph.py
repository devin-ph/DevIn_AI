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
from langchain_core.tools import tool

from devin.agent.llm_provider import create_llm
from devin.agent.prompts import get_architect_prompt, get_editor_prompt
from devin.agent.state import AgentState
from devin.settings import settings
from devin.tools.registry import ToolRegistry, create_default_registry

logger = logging.getLogger(__name__)

import subprocess
import os

@tool
def delegate_to_editor(instructions: str) -> str:
    """
    Delegate the execution of tasks to the Editor sub-agent.
    Provide highly detailed, step-by-step instructions for what the Editor needs to do.
    """
    return f"Delegated to Editor successfully. THE EDITOR IS NOW EXECUTING: {instructions}"

def build_graph(
    registry: ToolRegistry | None = None,
    model: str | None = None,
) -> StateGraph:
    """
    Build the DevIn Multi-Agent graph (Architect-Editor Pattern) with Brain V1.5.
    """
    if registry is None:
        registry = create_default_registry()

    all_tools = registry.get_tools()
    
    # Categorize tools
    architect_tool_names = ["read_file", "list_directory", "web_search", "get_current_time"]
    editor_tool_names = ["write_file", "execute_command", "calculator", "get_current_time"]
    
    a_tools = [t for t in all_tools if t.name in architect_tool_names]
    a_tools.append(delegate_to_editor)
    
    e_tools = [t for t in all_tools if t.name in editor_tool_names]

    # Shared LLM backend
    architect_llm = create_llm(model=model).bind_tools(a_tools)
    editor_llm = create_llm(model=model).bind_tools(e_tools)

    # --- Node Configurations ---

    def initialize_node(state: AgentState) -> dict:
        """One-time environment discovery."""
        if state.project_tree:
            return {"total_steps": state.total_steps + 1}
        
        logger.info("🔍 Initializing Environment Context...")
        try:
            # Run a fast recursive directory listing (Windows)
            result = subprocess.run(
                ["dir", "/b", "/s"], shell=True, capture_output=True, text=True, timeout=5
            )
            tree = result.stdout.strip()
            # truncate if too huge
            if len(tree) > 2000:
                tree = tree[:2000] + "\n... [TRUNCATED]"
        except Exception:
            tree = "Could not generate tree view."
            
        return {"project_tree": tree, "total_steps": state.total_steps + 1}

    def architect_node(state: AgentState) -> dict:
        messages = state.messages
        iteration = state.iteration_count
        total_steps = state.total_steps
        tree = state.project_tree

        prompt = get_architect_prompt(project_tree=tree, total_steps=total_steps)

        # Inject Architect System Prompt
        if messages and isinstance(messages[0], SystemMessage):
            msgs = [SystemMessage(content=prompt)] + list(messages[1:])
        else:
            msgs = [SystemMessage(content=prompt)] + list(messages)

        logger.info(f"🧠 Architect Reasoning — step {total_steps + 1}")
        response = architect_llm.invoke(msgs)
        return {"messages": [response], "iteration_count": iteration + 1, "total_steps": total_steps + 1}

    def editor_node(state: AgentState) -> dict:
        messages = state.messages
        iteration = state.iteration_count
        total_steps = state.total_steps
        feedback = state.verification_feedback

        # Look for the last delegation instructions
        instructions = ""
        for m in reversed(messages):
            if isinstance(m, ToolMessage) and m.name == "delegate_to_editor":
                instructions = m.content
                break

        prompt = get_editor_prompt(instructions=instructions, feedback=feedback, total_steps=total_steps)

        if messages and isinstance(messages[0], SystemMessage):
            msgs = [SystemMessage(content=prompt)] + list(messages[1:])
        else:
            msgs = [SystemMessage(content=prompt)] + list(messages)

        logger.info(f"⚡ Editor Executing — step {total_steps + 1}")
        response = editor_llm.invoke(msgs)
        return {"messages": [response], "iteration_count": iteration + 1, "total_steps": total_steps + 1}

    def validator_node(state: AgentState) -> dict:
        messages = state.messages
        total_steps = state.total_steps
        tree = state.project_tree

        prompt = get_validator_prompt(project_tree=tree, total_steps=total_steps)

        if messages and isinstance(messages[0], SystemMessage):
            msgs = [SystemMessage(content=prompt)] + list(messages[1:])
        else:
            msgs = [SystemMessage(content=prompt)] + list(messages)

        logger.info(f"🔍 Validator Reviewing — step {total_steps + 1}")
        response = architect_llm.invoke(msgs) # Validator uses Architect LLM for better reasoning
        return {"messages": [response], "total_steps": total_steps + 1}

    # --- Assemble Graph ---

    workflow = StateGraph(AgentState)

    workflow.add_node("initialize", initialize_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("architect_tools", ToolNode(a_tools))
    
    workflow.add_node("editor", editor_node)
    workflow.add_node("editor_tools", ToolNode(e_tools))
    workflow.add_node("validator", validator_node)

    workflow.set_entry_point("initialize")
    
    workflow.add_edge("initialize", "architect")

    workflow.add_conditional_edges("architect", architect_should_continue, {"architect_tools": "architect_tools", "__end__": END})
    workflow.add_conditional_edges("architect_tools", edge_after_architect_tools, {"editor": "editor", "architect": "architect"})
    
    workflow.add_conditional_edges("editor", editor_should_continue, {"editor_tools": "editor_tools", "validator": "validator"})
    workflow.add_edge("editor_tools", "editor")

    workflow.add_conditional_edges("validator", validator_should_continue, {"architect_tools": "architect_tools", "editor": "editor", "architect": "architect"})

    compiled = workflow.compile()
    logger.info("✅ Multi-Agent Graph Compiled (Verifying Architect)")

    return compiled

def architect_should_continue(state: AgentState) -> Literal["architect_tools", "__end__"]:
    messages = state.messages
    if not messages: return "__end__"
    last = messages[-1]
    
    total_steps = state.total_steps
    if total_steps >= 30: # Increased for verification loops
        logger.warning(f"CIRCUIT BREAKER: Max total steps ({total_steps}) hit. Stopping.")
        return "__end__"
        
    if isinstance(last, AIMessage) and last.tool_calls:
        return "architect_tools"
    return "__end__"

def edge_after_architect_tools(state: AgentState) -> Literal["editor", "architect"]:
    messages = state.messages
    if not messages: return "architect"
    last = messages[-1]
    
    if isinstance(last, ToolMessage) and (getattr(last, "name", "") == "delegate_to_editor" or last.tool_call_id == "delegate_to_editor"):
        return "editor"
    return "architect"

def editor_should_continue(state: AgentState) -> Literal["editor_tools", "validator"]:
    messages = state.messages
    if not messages: return "validator"
    last = messages[-1]
    
    total_steps = state.total_steps
    if total_steps >= 30:
        return "validator"
        
    if isinstance(last, AIMessage) and last.tool_calls:
        return "editor_tools"
    
    return "validator"

def validator_should_continue(state: AgentState) -> Literal["architect_tools", "editor", "architect"]:
    messages = state.messages
    if not messages: return "architect"
    last = messages[-1]

    if not isinstance(last, AIMessage):
        return "architect"

    content = last.content.upper()
    if last.tool_calls:
        return "architect_tools"
    
    if "FAIL" in content:
        # Pass feedback to editor
        # Note: In a real graph we might use a dedicated state update, 
        # but for now we'll rely on the LLM seeing it in history
        return "editor"
    
    return "architect"

def create_agent(model: str | None = None) -> Any:
    registry = create_default_registry()
    graph = build_graph(registry=registry, model=model)
    logger.info("🚀 DevIn Brain V1.5 ready")
    return graph
