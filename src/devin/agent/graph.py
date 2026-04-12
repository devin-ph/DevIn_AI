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

import os
from pathlib import Path
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from devin.constants import SKILL_LOAD_RULES, MUTATION_TOOLS

def _load_relevant_skills(user_message: str, skills_dir: str) -> str:
    """Load only skills relevant to the current request."""
    logger = logging.getLogger("devin")
    msg_lower = user_message.lower()
    content = ""
    loaded = []
    
    # Static rules for known skills
    STATIC_RULES = {
        "WHO_YOU_ARE.md":        ["*"],
        "ESCALATION_POLICY.md":  ["*"],
        "CODE_STYLE.md":         ["write","create","edit","code","fix"],
        "TASK_DECOMPOSITION.md": ["create","build","implement","refactor"],
        "MEMORY_PROTOCOL.md":    [],
    }
    
    # Dynamic: auto-generated skills always load for Python tasks
    AUTO_GENERATED_TRIGGERS = ["write","create","edit","code",
                                "fix","def","class","python",".py"]
    
    for filename in os.listdir(skills_dir):
        if not filename.endswith(".md"):
            continue
        
        filepath = os.path.join(skills_dir, filename)
        
        # Check static rules first
        if filename in STATIC_RULES:
            triggers = STATIC_RULES[filename]
            should_load = (
                triggers == ["*"] or
                any(t in msg_lower for t in triggers)
            )
        else:
            # Auto-generated skill: load for Python-related tasks
            should_load = any(
                t in msg_lower for t in AUTO_GENERATED_TRIGGERS
            )
        
        if should_load:
            with open(filepath, "r", encoding="utf-8") as f:
                skill_content = f.read()
                if len(skill_content) > 2000:
                    skill_content = skill_content[:2000] + "\n...[truncated]"
                content += f"\n--- {filename} ---\n{skill_content}\n"
                loaded.append(filename)
    
    logger.info(f"Skills loaded: {loaded}")
    return content

def _build_smart_tree(root_path: str, max_depth: int = 2, max_files_per_dir: int = 8) -> str:
    """Build a concise project tree — depth-limited and file-count-limited using os.walk."""
    root_path = os.path.abspath(root_path)
    IGNORE = {'.git', '__pycache__', '.venv', 'node_modules', '.pytest_cache', 
              'dist', 'build', '.eggs', '.egg-info'}
    
    lines = []
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter directories mapped back to original dirnames to trim traversal
        dirnames[:] = sorted([d for d in dirnames if not any(d.endswith(ig.strip('*')) if ig.startswith('*') else d == ig for ig in IGNORE) and not d.startswith('.')])
        filenames = sorted([f for f in filenames if not f.startswith('.')])
        
        # Calculate depth
        rel_path = os.path.relpath(dirpath, root_path)
        depth = 0 if rel_path == '.' else len(rel_path.split(os.sep))
        
        if depth > max_depth:
            dirnames[:] = []  # Stop traversing deeper
            continue
            
        indent = "  " * depth
        if depth == 0:
            lines.append(f"📁 {os.path.basename(root_path)}/")
        else:
            lines.append(f"{indent}📁 {os.path.basename(dirpath)}/")
            
        # File listing with limit
        for f in filenames[:max_files_per_dir]:
            lines.append(f"{indent}  📄 {f}")
        if len(filenames) > max_files_per_dir:
            lines.append(f"{indent}    ... [{len(filenames) - max_files_per_dir} more files]")
            
    result = "\n".join(lines)
    if len(result) > 1500:
        result = result[:1500] + "\n... [tree truncated]"
    return result

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
    get_worker_prompt,
)
from devin.agent.state import AgentState
from devin.settings import settings
from devin.tools.registry import ToolRegistry, create_default_registry

logger = logging.getLogger(__name__)

import subprocess
import os

from dataclasses import dataclass

@dataclass
class WorkerBrief:
    task: str           # What to do
    files: list[str]    # Which files are involved  
    context: str        # Relevant snippets only
    constraints: str    # From active skills

@tool
def delegate_to_worker(task: str, files: list[str], context: str, constraints: str) -> str:
    """
    Delegate the execution of tasks to the Worker sub-agent.
    You MUST provide task (what to do), files (which are involved), context (relevant snippets only), and constraints (from active skills).
    """
    return f"Delegated to Worker successfully. The worker has started."

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
    worker_tool_names = ["write_file", "edit_file_replace", "execute_command", "calculator", "get_current_time", "read_file", "file_search", "grep_search", "analyze_python_ast", "git_diff", "git_status", "self_check_file"]
    
    a_tools = [t for t in all_tools if t.name in architect_tool_names]
    a_tools.append(delegate_to_worker)
    
    w_tools = [t for t in all_tools if t.name in worker_tool_names]

    from devin.agent.query import QueryEngine

    architect_llm = create_llm(model=model).bind_tools(a_tools)
    worker_llm = create_llm(model=model).bind_tools(w_tools)
    
    a_query_engine = QueryEngine(architect_llm)
    w_query_engine = QueryEngine(worker_llm)

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
        
        # Get the original user message from state to determine relevant skills
        original_message = ""
        for msg in state.messages:
            if hasattr(msg, 'content') and isinstance(msg.content, str):
                original_message = msg.content
                break

        # Load real session memory
        from devin.agent.memory import MemoryEngine
        memory_engine = MemoryEngine()
        memory_content = memory_engine.load()

        skills_dir = os.path.join(os.path.dirname(__file__), "..", "skills")
        active_skills_content = _load_relevant_skills(original_message, skills_dir)
        
        project_rules_content = memory_content + "\n\n"
        devin_md_path = os.path.join(os.getcwd(), "DEVIN.md")
        if os.path.exists(devin_md_path):
            with open(devin_md_path, "r", encoding="utf-8") as f:
                project_rules_content += f.read()
                
        # Truncate rules just in case DEVIN.md is large
        if len(project_rules_content) > 3000:
            project_rules_content = project_rules_content[:3000] + "\n\n... [RULES TRUNCATED]"

        try:
            tree = _build_smart_tree(os.getcwd(), max_depth=2)
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

    async def architect_node(state: AgentState) -> dict:
        messages = state.messages

        # FILTER WORKER CONTEXT: Hides Worker's intermediate tools, only exposes summary.
        filtered_msgs = []
        in_worker_phase = False
        from langchain_core.messages import SystemMessage, ToolMessage, AIMessage, HumanMessage
        
        for m in messages:
            if getattr(m, "name", "") == "delegate_to_worker" and isinstance(m, ToolMessage):
                filtered_msgs.append(m)
                in_worker_phase = True
                continue
                
            if in_worker_phase:
                if isinstance(m, AIMessage) and not m.tool_calls:
                    # Worker finished, returning summary
                    filtered_msgs.append(HumanMessage(content=f"Worker Execution Completed:\n{m.content}"))
                    in_worker_phase = False
                # Skip ALL other worker messages (tools, etc.)
                continue
                
            filtered_msgs.append(m)
            
        messages = filtered_msgs

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
        response = await a_query_engine.query(msgs)
        usage = _extract_token_usage(response)
        return {"messages": [response], "iteration_count": iteration + 1, "total_steps": total_steps + 1, "token_usage": usage}

    async def worker_node(state: AgentState) -> dict:
        msgs_all = state.messages
        # ISOLATE WORKER CONTEXT
        # Find the last delegate_to_worker tool call in Architect's history
        
        args = {}
        for m in reversed(msgs_all):
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    if tc["name"] == "delegate_to_worker":
                        args = tc.get("args", {})
                        break
            if args: break
            
        t = args.get("task", "")
        f = args.get("files", "")
        c = args.get("context", "")
        cs = args.get("constraints", "")
        instructions = f"TASK:\n{t}\n\nFILES:\n{f}\n\nCONTEXT:\n{c}\n\nCONSTRAINTS:\n{cs}"

        # Get all Worker messages (everything AFTER the delegate_to_worker ToolMessage)
        worker_recent_msgs = []
        found = False
        for m in msgs_all:
            if found:
                worker_recent_msgs.append(m)
            elif getattr(m, "name", "") == "delegate_to_worker" and isinstance(m, ToolMessage):
                found = True

        iteration = state.iteration_count
        total_steps = state.total_steps
        tree = state.project_tree

        # Load bugs for Worker
        import os
        bugs_content = ""
        bugs_path = os.path.join("data", "memory", "bugs.md")
        if os.path.exists(bugs_path):
            with open(bugs_path, "r", encoding="utf-8") as f:
                bugs_content = f.read()

        prompt = get_worker_prompt(
            instructions=instructions, 
            project_tree=tree,
            total_steps=total_steps,
            active_skills=state.active_skills,
            project_rules=state.project_rules,
            bugs_content=bugs_content,
        )
        
        # Worker gets isolated context!
        msgs = [SystemMessage(content=prompt)] + worker_recent_msgs
        
        msgs = _truncate_tool_messages(msgs)

        logger.info(f"⚡ Worker Executing (Isolated context: {len(msgs)} msgs) — step {total_steps + 1}")
        response = await w_query_engine.query(msgs)
        usage = _extract_token_usage(response)

        modified_files = getattr(state, "modified_files", []) or []
        hard_feedback = []
        if modified_files:
            import subprocess
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
        
        is_fail = len(hard_feedback) > 0
        if is_fail:
            error_details = "\n".join(hard_feedback)
            _track_learning_loop("worker_validation", error_details[:100], "")
            from langchain_core.messages import AIMessage
            
            # Instead of replacing the AI's content, we simulate a SystemMessage giving it feedback, 
            # or in this simple loop, we append it so the next iteration fixes it.
            # To keep it simple, we wrap it into the response.
            response = AIMessage(
                content="VULNERABILITY DETECTED:\n" + error_details + "\n\n" + str(getattr(response, "content", "")),
                id=getattr(response, "id", None),
                name=getattr(response, "name", None),
                tool_calls=getattr(response, "tool_calls", []),
                response_metadata=getattr(response, "response_metadata", {})
            )

        return {"messages": [response], "iteration_count": iteration + 1, "total_steps": total_steps + 1, "token_usage": usage, "modified_files": []}

    def _track_learning_loop(tool_name: str, error_msg: str, args: str, root_cause: str = "Pending", fix: str = "Pending"):
        import os
        from datetime import datetime
        from pathlib import Path
        pattern = error_msg.split('\n')[0][:80] if error_msg else "Unknown error"
        entry_str = f"[{datetime.now().strftime('%Y-%m')}] {tool_name}: {pattern} → Root cause: {root_cause} → Fix: {fix}"
        
        bugs_path = os.path.join("data", "memory", "bugs.md")
        os.makedirs(os.path.dirname(bugs_path), exist_ok=True)
        count = 0
        content = ""
        resolved_marker = f"[RESOLVED] {pattern[:40]}"
        if os.path.exists(bugs_path):
            with open(bugs_path, "r", encoding="utf-8") as f:
                content = f.read()
                if resolved_marker in content:
                    return # Already resolved with a skill
                count = content.count(pattern[:40])
                
        # Deduplication check: only write if NOT pending AND it's not a duplicate
        if root_cause != "Pending":
            if entry_str not in content:
                with open(bugs_path, "a", encoding="utf-8") as f:
                    f.write(f"\n{entry_str}\n")
        else:
            # We don't write pending entries, but we still track count for learning loop
            pass
            
        if count >= 2: # 3rd time
            print(f"\n[devin.system]⚠️ DevIn Learning Loop: I've encountered '{pattern[:40]}...' {count+1} times.[/]")
            try:
                ans = input("   Create a skill to prevent this? [Y/n]: ").strip().lower()
                if ans in ("y", "yes", ""):
                    # Extract the actual flake8 error pattern from bug history
                    skill_name = "FLAKE8_COMMON_ERRORS.md"
                    skill_path = Path("src/devin/skills") / skill_name
                    
                    # Read bugs.md to get the actual pattern
                    bugs_path = Path("data/memory/bugs.md")
                    bug_context = ""
                    if bugs_path.exists():
                        bug_context = bugs_path.read_text(encoding="utf-8")[-500:]
                    
                    skill_content = f"""# FLAKE8_COMMON_ERRORS — Auto-generated Skill

## When to Use This Skill
Load when writing or editing any Python file.

## Pattern That Triggered This Skill
This skill was auto-generated after encountering the same flake8
issue 3+ times:
{bug_context or "flake8 style warnings on Python files"}

## Rules to Follow
- Always add a newline at end of file
- Maximum line length: 100 characters
- No unused imports
- No trailing whitespace
- Use double quotes for strings consistently

## Examples
✅ Correct:
def add(a: int, b: int) -> int:
    return a + b

❌ Wrong:
def add(a,b):
  return a+b

## Auto-generated
Date: {datetime.now().strftime("%Y-%m-%d")}
Trigger: flake8 warnings encountered 3+ times
"""
                    
                    skill_path.parent.mkdir(parents=True, exist_ok=True)
                    skill_path.write_text(skill_content, encoding="utf-8")
                    
                    from devin.agent.memory import MemoryEngine
                    memory_engine = MemoryEngine()
                    memory_engine.mark_pattern_resolved("flake8", skill_name)
                    
                    with open(bugs_path, "a", encoding="utf-8") as f:
                        f.write(f"\n{resolved_marker} → skill created: {skill_name}\n")
                        
                    from devin.cli.renderer import console
                    console.print(f"  [green]✅ Skill created: {skill_name}[/]")
                    console.print(f"  [dim]Location: {skill_path}[/]")
                    console.print(f"  [dim]This skill will auto-load for future Python tasks.[/]")
            except (EOFError, KeyboardInterrupt):
                pass

    workflow = StateGraph(AgentState)

    workflow.add_node("initialize", initialize_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("architect_tools", ToolNode(a_tools))
    
    def worker_tools_wrapper(state: AgentState):
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
            
            if "messages" in result_state:
                msgs = result_state["messages"]
                if not isinstance(msgs, list): msgs = [msgs]
                for msg in msgs:
                    if hasattr(msg, "content"):
                        cont = str(msg.content)
                        if "Error:" in cont or "FAIL" in cont or "Traceback" in cont:
                            _track_learning_loop(getattr(msg, "name", "tool"), cont, "")
                            
            return result_state
            
        tool_calls = getattr(last_msg, "tool_calls", [])
        
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("DEVIN_AUTO_APPROVE") == "1":
            return _get_modified(tool_calls, ToolNode(w_tools).invoke(state))
            
        if not tool_calls:
            return ToolNode(w_tools).invoke(state)
            
        import json
        from pathlib import Path
        for tc in tool_calls:
            if tc["name"] in MUTATION_TOOLS:
                filepath = tc["args"].get("filepath", "")
                
                # Show git diff if file exists (before showing consent)
                if tc["name"] == "edit_file_replace":
                    filepath = tc["args"].get("filepath", "")
                    if filepath and Path(filepath).exists():
                        diff = subprocess.run(
                            ["git", "diff", "HEAD", filepath],
                            capture_output=True, text=True, timeout=5
                        )
                        if diff.stdout.strip():
                            print(f"\n📄 Changes to {filepath}:")
                            for line in diff.stdout.strip().splitlines()[:30]:
                                if line.startswith("+") and not line.startswith("+++"):
                                    print(f"  \033[32m{line}\033[0m")
                                elif line.startswith("-") and not line.startswith("---"):
                                    print(f"  \033[31m{line}\033[0m")
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
                
        return _get_modified(tool_calls, ToolNode(w_tools).invoke({"messages": state.messages}))

    workflow.add_node("worker", worker_node)
    workflow.add_node("worker_tools", worker_tools_wrapper)

    workflow.set_entry_point("initialize")
    
    workflow.add_edge("initialize", "architect")

    workflow.add_conditional_edges("architect", architect_should_continue, {"architect_tools": "architect_tools", "__end__": END})
    workflow.add_conditional_edges("architect_tools", edge_after_architect_tools, {"worker": "worker", "architect": "architect"})
    
    workflow.add_conditional_edges("worker", worker_should_continue, {"worker_tools": "worker_tools", "architect": "architect"})
    workflow.add_edge("worker_tools", "worker")

    compiled = workflow.compile()
    logger.info("✅ Multi-Agent Graph Compiled (Architect + Worker)")

    return compiled

def architect_should_continue(state: AgentState) -> Literal["architect_tools", "__end__"]:
    messages = state.messages
    if not messages: return "__end__"
    last = messages[-1]
    
    total_steps = state.total_steps
    if total_steps >= 20: 
        logger.warning(f"CIRCUIT BREAKER: Max total steps ({total_steps}) hit. Stopping.")
        return "__end__"
        
    if isinstance(last, AIMessage) and last.tool_calls:
        return "architect_tools"
    return "__end__"

def edge_after_architect_tools(state: AgentState) -> Literal["worker", "architect"]:
    messages = state.messages
    if not messages: return "architect"
    last = messages[-1]
    
    if isinstance(last, ToolMessage) and getattr(last, "name", "") == "delegate_to_worker":
        return "worker"
    return "architect"

def worker_should_continue(state: AgentState) -> Literal["worker_tools", "architect"]:
    messages = state.messages
    if not messages: return "architect"
    last = messages[-1]
    
    total_steps = state.total_steps
    if total_steps >= 35:
        return "architect"
        
    if isinstance(last, AIMessage) and last.tool_calls:
        return "worker_tools"
    
    return "architect"

def create_agent(model: str | None = None) -> Any:
    registry = create_default_registry()
    graph = build_graph(registry=registry, model=model)
    logger.info("🚀 DevIn Brain V1.5 ready")
    return graph
