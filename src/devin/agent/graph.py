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

def _summarize_history(messages: list, keep_recent: int = 4) -> list:
    """
    Compress old messages into a structured summary when history is too long.
    Zero LLM calls — extracts structured data from existing messages.
    Keeps the last `keep_recent` message pairs intact for immediate context.
    """
    if len(messages) <= (keep_recent * 2 + 1):  # +1 for system prompt
        return messages  # Not long enough to summarize
    
    # Separate system prompt, old messages, recent messages
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]
    
    if len(non_system) <= keep_recent * 2:
        return messages
    
    old_messages = non_system[:-keep_recent * 2]
    recent_messages = non_system[-keep_recent * 2:]
    
    # Extract structured data from old messages
    goals_achieved = []
    files_modified = []
    decisions_made = []
    errors_encountered = []
    
    import re
    for msg in old_messages:
        if isinstance(msg, HumanMessage):
            content = str(msg.content)[:100]
            goals_achieved.append(f"User requested: {content}")
        elif isinstance(msg, ToolMessage):
            content = str(msg.content)
            tool_name = getattr(msg, 'name', '')
            if tool_name in ('write_file', 'edit_file_replace') and 'Success' in content:
                match = re.search(r'to (.+?\.\w+)', content)
                if match:
                    files_modified.append(match.group(1))
            elif tool_name == 'execute_command':
                if 'Exit code: 0' in content:
                    cmd_match = re.search(r'command: (.+)', content)
                    if cmd_match:
                        decisions_made.append(f"Ran: {cmd_match.group(1)[:60]}")
                elif 'Exit code:' in content and 'Exit code: 0' not in content:
                    errors_encountered.append(content[:100].replace('\n', ' '))
    
    # Build structured summary
    summary_parts = ["=== CONVERSATION HISTORY SUMMARY ==="]
    if goals_achieved:
        summary_parts.append(f"Goals completed: {'; '.join(goals_achieved[-3:])}")
    if files_modified:
        unique_files = list(dict.fromkeys(files_modified))  # deduplicate, preserve order
        summary_parts.append(f"Files modified: {', '.join(unique_files)}")
    if decisions_made:
        summary_parts.append(f"Commands run: {'; '.join(decisions_made[-3:])}")
    if errors_encountered:
        summary_parts.append(f"Errors seen: {'; '.join(errors_encountered[-2:])}")
    summary_parts.append("=== END SUMMARY — RECENT CONTEXT FOLLOWS ===")
    
    summary_message = HumanMessage(
        content="\n".join(summary_parts)
    )
    
    return system_msgs + [summary_message] + recent_messages

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool

from devin.agent.llm_provider import create_llm
from devin.agent.prompts import (
    get_architect_prompt,
    get_editor_prompt,
    get_validator_prompt,
)
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
    
    from devin.tools.system import git_diff, git_status, self_check_file
    all_tools.extend([git_diff, git_status, self_check_file])
    
    # Categorize tools
    architect_tool_names = ["read_file", "list_directory", "web_search", "get_current_time", "file_search", "grep_search", "analyze_python_ast", "git_diff", "git_status"]
    editor_tool_names = ["write_file", "edit_file_replace", "execute_command", "calculator", "get_current_time", "read_file", "file_search", "grep_search", "analyze_python_ast", "git_diff", "git_status", "self_check_file"]
    
    a_tools = [t for t in all_tools if t.name in architect_tool_names]
    a_tools.append(delegate_to_editor)
    
    e_tools = [t for t in all_tools if t.name in editor_tool_names]

    # Shared LLM backend
    # Adding .with_retry() to transparently handle OpenRouter 'Provider returned error' api drops
    architect_llm = create_llm(model=model).bind_tools(a_tools).with_retry(stop_after_attempt=4)
    editor_llm = create_llm(model=model).bind_tools(e_tools).with_retry(stop_after_attempt=4)

    def _truncate_tool_messages(msgs: list) -> list:
        """
        Scan messages and proactively truncate extremely long ToolMessages
        to prevent 'Provider returned error' from bursting model context limits.
        """
        processed = []
        max_length = 20000  # Leave room for system prompt and reasoning

        for m in msgs:
            if isinstance(m, ToolMessage) and isinstance(m.content, str):
                if len(m.content) > max_length:
                    truncated = m.content[:max_length] + f"\n\n... [TRUNCATED {len(m.content) - max_length} chars to save context]"
                    
                    new_m = ToolMessage(
                        content=truncated,
                        name=m.name,
                        tool_call_id=m.tool_call_id,
                        status=m.status
                    )
                    processed.append(new_m)
                    continue
            processed.append(m)
        return processed

    def _compress_history(msgs: list) -> list:
        """
        Compresses long history preserving System Prompt, first Human message (goal), 
        and last few turns. Replaces middle with a structured summary to save tokens.
        """
        if len(msgs) <= 10:
            return msgs
            
        system_msgs = [m for m in msgs if isinstance(m, SystemMessage)]
        other_msgs = [m for m in msgs if not isinstance(m, SystemMessage)]
        
        if len(other_msgs) <= 6:
            return msgs
            
        first_human = other_msgs[0]
        recent_msgs = other_msgs[-5:]
        
        # Count tool calls in omitted
        omitted = other_msgs[1:-5]
        tools_used = []
        for m in omitted:
            if isinstance(m, AIMessage) and m.tool_calls:
                tools_used.extend([tc["name"] for tc in m.tool_calls])
                
        from collections import Counter
        tool_counts = dict(Counter(tools_used))
        
        summary_text = f"[[CONTEXT COMPRESSED]]\n"
        summary_text += f"{len(omitted)} intermediate messages were removed to save tokens.\n"
        if tool_counts:
            summary_text += f"Tools utilized in omitted history: {tool_counts}\n"
            
        summary_msg = SystemMessage(content=summary_text)
        
        return system_msgs + [first_human, summary_msg] + recent_msgs

    # --- Node Configurations ---

    def initialize_node(state: AgentState) -> dict:
        """One-time environment discovery."""
        if state.project_tree:
            return {"total_steps": state.total_steps + 1}
        
        logger.info("🔍 Initializing Environment Context...")
        
        active_skills_content = ""
        skills_dir = os.path.join(os.path.dirname(__file__), "..", "skills")
        if os.path.exists(skills_dir):
            priority_files = ["WHO_YOU_ARE.md", "ESCALATION_POLICY.md"]
            files = [f for f in os.listdir(skills_dir) if f.endswith(".md")]
            files.sort(key=lambda x: (0 if x in priority_files else 1, x))
            
            for filename in files:
                with open(os.path.join(skills_dir, filename), "r", encoding="utf-8") as f:
                    content = f"\n--- {filename} ---\n{f.read()}\n"
                    if len(active_skills_content) + len(content) > 12000 and filename not in priority_files:
                        active_skills_content += f"\n--- {filename} ---\n... [SKILLS TRUNCATED TO FIT FREE TIER CONTEXT]\n"
                        break
                    active_skills_content += content
        
        project_rules_content = ""
        devin_md_path = os.path.join(os.getcwd(), "DEVIN.md")
        if os.path.exists(devin_md_path):
            with open(devin_md_path, "r", encoding="utf-8") as f:
                project_rules_content = f.read()
                
        # Truncate rules just in case DEVIN.md is large
        if len(project_rules_content) > 3000:
            project_rules_content = project_rules_content[:3000] + "\n\n... [RULES TRUNCATED]"

        try:
            tree_lines = []
            for root, dirs, files in os.walk(os.getcwd()):
                dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', '.venv', 'node_modules', 'dist', 'build', '.pytest_cache')]
                rel_dir = os.path.relpath(root, os.getcwd())
                
                # Append files as relative paths
                for f in files:
                    if f.endswith(('.exe', '.dll', '.so', '.pyc')): continue
                    path = f if rel_dir == '.' else os.path.join(rel_dir, f)
                    tree_lines.append(path.replace('\\', '/'))
                    
                if len(tree_lines) > 200:
                    tree_lines.append("... [MORE FILES TRUNCATED]")
                    break
            tree = "\n".join(tree_lines)
            if len(tree) > 3000:
                tree = tree[:3000] + "\n... [TRUNCATED]"
        except Exception:
            tree = "Could not generate tree view."
            
        return {
            "project_tree": tree, 
            "active_skills": active_skills_content,
            "project_rules": project_rules_content,
            "total_steps": state.total_steps + 1
        }
        
    def _extract_token_usage(response) -> dict:
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 1}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            if isinstance(meta, dict):
                usage["input_tokens"] = meta.get("input_tokens", 0)
                usage["output_tokens"] = meta.get("output_tokens", 0)
                usage["total_tokens"] = meta.get("total_tokens", 0)
            else:
                usage["input_tokens"] = getattr(meta, "input_tokens", 0)
                usage["output_tokens"] = getattr(meta, "output_tokens", 0)
                usage["total_tokens"] = getattr(meta, "total_tokens", 0)
        return usage

    def architect_node(state: AgentState) -> dict:
        messages = state.messages
        SUMMARIZE_AFTER_TURNS = 10
        non_system_count = sum(1 for m in messages if not isinstance(m, SystemMessage))
        if non_system_count > SUMMARIZE_AFTER_TURNS:
            logger.info(f"Summarizing history: {non_system_count} messages → compressed")
            messages = _summarize_history(list(messages), keep_recent=4)
            
        iteration = state.iteration_count
        total_steps = state.total_steps
        tree = state.project_tree

        prompt = get_architect_prompt(
            project_tree=tree, 
            total_steps=total_steps,
            active_skills=state.active_skills,
            project_rules=state.project_rules
        )

        # Inject Architect System Prompt
        if messages and isinstance(messages[0], SystemMessage):
            msgs = [SystemMessage(content=prompt)] + list(messages[1:])
        else:
            msgs = [SystemMessage(content=prompt)] + list(messages)

        msgs = _truncate_tool_messages(msgs)
        msgs = _compress_history(msgs)

        logger.info(f"🧠 Architect Reasoning — step {total_steps + 1}")
        response = architect_llm.invoke(msgs)
        usage = _extract_token_usage(response)
        return {"messages": [response], "iteration_count": iteration + 1, "total_steps": total_steps + 1, "token_usage": usage}

    def editor_node(state: AgentState) -> dict:
        logger.info(f'⚡ EDITOR NODE CALLED — messages count: {len(state.messages)}')
        messages = state.messages
        SUMMARIZE_AFTER_TURNS = 10
        non_system_count = sum(1 for m in messages if not isinstance(m, SystemMessage))
        if non_system_count > SUMMARIZE_AFTER_TURNS:
            logger.info(f"Summarizing history: {non_system_count} messages → compressed")
            messages = _summarize_history(list(messages), keep_recent=4)
            
        iteration = state.iteration_count
        total_steps = state.total_steps
        feedback = state.verification_feedback

        # Look for the last delegation instructions
        instructions = ""
        for m in reversed(messages):
            if isinstance(m, ToolMessage) and m.name == "delegate_to_editor":
                instructions = m.content
                break

        prompt = get_editor_prompt(
            instructions=instructions, 
            feedback=feedback, 
            total_steps=total_steps,
            active_skills=state.active_skills,
            project_rules=state.project_rules
        )

        if messages and isinstance(messages[0], SystemMessage):
            msgs = [SystemMessage(content=prompt)] + list(messages[1:])
        else:
            msgs = [SystemMessage(content=prompt)] + list(messages)

        # Remove the delegate_to_editor tool call so the LLM does not think it is the Architect
        cleaned_msgs = []
        from langchain_core.messages import AIMessage, HumanMessage

        for m in msgs:
            if isinstance(m, AIMessage) and m.tool_calls:
                new_tcs = [tc for tc in m.tool_calls if tc["name"] != "delegate_to_editor"]
                if len(new_tcs) != len(m.tool_calls):
                    cleaned_msgs.append(AIMessage(content=m.content, tool_calls=new_tcs))
                    continue
            if isinstance(m, ToolMessage) and m.name == "delegate_to_editor":
                cleaned_msgs.append(HumanMessage(content=f"ARCHITECT DELEGATION INSTRUCTIONS:\n{m.content}"))
                continue
            cleaned_msgs.append(m)

        msgs = _truncate_tool_messages(cleaned_msgs)
        msgs = _compress_history(msgs)

        logger.info(f"⚡ Editor Executing — step {total_steps + 1}")
        response = editor_llm.invoke(msgs)
        usage = _extract_token_usage(response)
        return {"messages": [response], "iteration_count": iteration + 1, "total_steps": total_steps + 1, "token_usage": usage}

    def validator_node(state: AgentState) -> dict:
        messages = state.messages
        SUMMARIZE_AFTER_TURNS = 10
        non_system_count = sum(1 for m in messages if not isinstance(m, SystemMessage))
        if non_system_count > SUMMARIZE_AFTER_TURNS:
            logger.info(f"Summarizing history: {non_system_count} messages → compressed")
            messages = _summarize_history(list(messages), keep_recent=4)
            
        total_steps = state.total_steps
        tree = state.project_tree
        modified_files = getattr(state, "modified_files", []) or []

        prompt = get_validator_prompt(
            project_tree=tree, 
            total_steps=total_steps,
            active_skills=state.active_skills,
            project_rules=state.project_rules
        )

        if messages and isinstance(messages[0], SystemMessage):
            msgs = [SystemMessage(content=prompt)] + list(messages[1:])
        else:
            msgs = [SystemMessage(content=prompt)] + list(messages)

        msgs = _truncate_tool_messages(msgs)
        msgs = _compress_history(msgs)

        logger.info(f"🔍 Validator Reviewing — step {total_steps + 1}")
        response = architect_llm.invoke(msgs) # Validator uses Architect LLM for better reasoning
        usage = _extract_token_usage(response)
        
        # Hard Validation block
        import subprocess
        hard_feedback = []
        if modified_files:
            for filepath in modified_files:
                if filepath.endswith(".py"):
                    try:
                        res = subprocess.run(["python", "-m", "flake8", filepath, "--max-line-length=120"], capture_output=True, text=True, timeout=5)
                        if res.stdout:
                            hard_feedback.append(f"flake8 ({filepath}):\n{res.stdout[:500]}")
                        
                        res2 = subprocess.run(["python", "-m", "py_compile", filepath], capture_output=True, text=True, timeout=5)
                        if res2.returncode != 0:
                            hard_feedback.append(f"py_compile ({filepath}):\n{res2.stderr[:500]}")
                    except Exception:
                        pass
        
        feedback = ""
        content = getattr(response, "content", "").upper()
        
        is_fail = "FAIL" in content or len(hard_feedback) > 0
        
        if is_fail:
            feedback = response.content
            if hard_feedback:
                feedback += "\n\n" + "\n".join(hard_feedback)
                if "FAIL" not in content:
                    response = AIMessage(
                        content="FAIL:\n" + response.content + "\n\n" + "\n".join(hard_feedback),
                        id=response.id,
                        name=response.name,
                        tool_calls=response.tool_calls,
                        response_metadata=response.response_metadata
                    )
                    
        return {
            "messages": [response], 
            "total_steps": total_steps + 1,
            "verification_feedback": feedback,
            "modified_files": [],
            "token_usage": usage
        }

    # --- Assemble Graph ---

    workflow = StateGraph(AgentState)

    workflow.add_node("initialize", initialize_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("architect_tools", ToolNode(a_tools))
    
    workflow.add_node("editor", editor_node)
    
    def editor_tools_wrapper(state: AgentState):
        last_msg = state.messages[-1]
        
        def _get_modified(tool_calls, result_state):
            new_files = getattr(state, "modified_files", []) or []
            new_files = list(new_files)
            for tc in tool_calls:
                if tc["name"] in ("write_file", "edit_file_replace"):
                    filepath = tc["args"].get("filepath")
                    if filepath and filepath not in new_files:
                        new_files.append(filepath)
            result_state["modified_files"] = new_files
            return result_state
            
        tool_calls = getattr(last_msg, "tool_calls", [])
        
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("DEVIN_AUTO_APPROVE") == "1":
            return _get_modified(tool_calls, ToolNode(e_tools).invoke(state))
            
        mutation_tools = ["execute_command", "write_file", "edit_file_replace"]
        
        if not tool_calls:
            return ToolNode(e_tools).invoke(state)
            
        import json
        from pathlib import Path
        for tc in tool_calls:
            if tc["name"] in mutation_tools:
                filepath = tc["args"].get("filepath", "")
                
                # Show git diff if file exists (before showing consent)
                if filepath and Path(filepath).exists() and tc["name"] in ("write_file", "edit_file_replace"):
                    diff_result = subprocess.run(
                        ["git", "diff", "HEAD", filepath],
                        capture_output=True, text=True, timeout=5
                    )
                    if diff_result.stdout.strip():
                        print(f"\n📄 Current diff for {filepath}:")
                        # Print first 30 lines of diff
                        diff_lines = diff_result.stdout.strip().splitlines()[:30]
                        for line in diff_lines:
                            if line.startswith("+"):
                                print(f"  \033[32m{line}\033[0m")  # green
                            elif line.startswith("-"):
                                print(f"  \033[31m{line}\033[0m")  # red
                            else:
                                print(f"  {line}")
                
                args_str = json.dumps(tc["args"], indent=2, ensure_ascii=False)
                print(f"\n⚠️  DevIn wants to run: {tc['name']}")
                print(f"   Args:\n{args_str}")
                try:
                    answer = input("Allow? [Y/n]: ").strip().lower()
                    approved = answer in ("", "y", "yes")
                except (EOFError, KeyboardInterrupt):
                    approved = False  # Deny if cannot get input
                except Exception as e:
                    logger.error(f"Consent prompt failed: {e}")
                    approved = False
                
                if not approved:
                    tool_messages = []
                    for t in tool_calls:
                        tool_messages.append(ToolMessage(
                            content=f"User DENIED {t['name']}. Revise plan or ask user.",
                            name=t["name"],
                            tool_call_id=t["id"]
                        ))
                    return {"messages": tool_messages}
                
        return _get_modified(tool_calls, ToolNode(e_tools).invoke({"messages": state.messages}))

    workflow.add_node("editor_tools", editor_tools_wrapper)
    workflow.add_node("validator", validator_node)

    workflow.set_entry_point("initialize")
    
    workflow.add_edge("initialize", "architect")

    workflow.add_conditional_edges("architect", architect_should_continue, {"architect_tools": "architect_tools", "__end__": END})
    workflow.add_conditional_edges("architect_tools", edge_after_architect_tools, {"editor": "editor", "architect": "architect"})
    
    workflow.add_conditional_edges("editor", editor_should_continue, {"editor_tools": "editor_tools", "validator": "validator", "architect": "architect"})
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
    if total_steps >= 15: # Increased for verification loops
        logger.warning(f"CIRCUIT BREAKER: Max total steps ({total_steps}) hit. Stopping.")
        return "__end__"
        
    if isinstance(last, AIMessage) and last.tool_calls:
        return "architect_tools"
    return "__end__"

def edge_after_architect_tools(state: AgentState) -> Literal["editor", "architect"]:
    messages = state.messages
    if not messages: return "architect"
    last = messages[-1]
    
    if isinstance(last, ToolMessage) and getattr(last, "name", "") == "delegate_to_editor":
        return "editor"
    return "architect"

def editor_should_continue(state: AgentState) -> Literal["editor_tools", "validator", "architect"]:
    messages = state.messages
    if not messages: return "validator"
    last = messages[-1]
    
    total_steps = state.total_steps
    if total_steps >= 30:
        return "validator"
        
    if isinstance(last, AIMessage) and last.tool_calls:
        return "editor_tools"
    
    if not getattr(state, "modified_files", []):
        return "architect"
        
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
