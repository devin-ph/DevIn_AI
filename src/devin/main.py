"""
DevIn CLI — Rich terminal interface for interacting with the agent.

This is the primary user interface for DevIn through Phases 1-4.
Features:
- Rich formatted output with colors and panels
- Real-time streaming of agent reasoning and tool calls with astream_events
- Slash commands (/help, /clear, /debug, /exit)
- Full conversation history
- JSON logging of all interactions
- Buffered <thought> tag parsing for clean visual rendering
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys

# Force UTF-8 rendering on Windows terminals to prevent rich crashes
if hasattr(sys.stdout, 'reconfigure'):
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

logger = logging.getLogger("devin")

from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.theme import Theme

# --- Theme ---
DEVIN_THEME = Theme(
    {
        "devin.name": "bold cyan",
        "devin.thinking": "dim italic yellow",
        "devin.tool_name": "bold magenta",
        "devin.tool_input": "dim white",
        "devin.tool_output": "green",
        "devin.error": "bold red",
        "devin.system": "dim cyan",
        "devin.user": "bold white",
        "devin.iteration": "dim yellow",
    }
)

console = Console(theme=DEVIN_THEME)

# --- Logging setup ---
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s | %(message)s",
)
logger = logging.getLogger("devin")


# --- Slash Commands ---
SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/clear": "Clear the conversation history and start fresh",
    "/history": "Show conversation history summary",
    "/debug": "Toggle debug mode (shows full state transitions)",
    "/model": "Show or change the current LLM model",
    "/tools": "List all available tools",
    "/exit": "Exit DevIn",
    "/quit": "Exit DevIn",
}

# --- Interaction Logger ---
class InteractionLogger:
    """Logs all conversations to a JSON file for analysis and memory training."""

    def __init__(self, log_dir: str = "./data/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.log_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.entries: list[dict] = []

    def log(self, role: str, content: str, metadata: dict | None = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "content": content,
            "metadata": metadata or {},
        }
        self.entries.append(entry)
        # Append to file
        with open(self.session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


# --- Thought Buffer ---
class ThoughtBuffer:
    """
    Accumulates text chunks to cleanly parse <thought> XML tags.
    Prevents broken tags (e.g., '<thou' + 'ght>') from rendering.
    """

    def __init__(self):
        self.buffer = ""
        self.complete_blocks: list[str] = []  # Complete <thought>...</thought> blocks
        self.display_text = ""  # Text with thoughts removed

    def add_chunk(self, chunk: str) -> str:
        """
        Add a chunk and return displayable text (without <thought> tags).
        Accumulates chunks until <thought> tags are complete.
        """
        self.buffer += chunk
        self._process_buffer()
        return self.display_text

    def _process_buffer(self):
        """Extract complete <thought> blocks and update display text."""
        self.complete_blocks = []
        self.display_text = ""

        # Find all complete <thought>...</thought> blocks
        thought_pattern = r'<thought>.*?</thought>'
        for match in re.finditer(thought_pattern, self.buffer, re.DOTALL):
            self.complete_blocks.append(match.group())

        # Remove all complete thought blocks from display
        self.display_text = re.sub(thought_pattern, '', self.buffer, flags=re.DOTALL).strip()

    def get_display_text(self) -> str:
        """Get the current text without thought tags."""
        return self.display_text

    def get_complete_thoughts(self) -> list[str]:
        """Get all complete thought blocks extracted so far."""
        return self.complete_blocks

    def finalize(self) -> tuple[str, list[str]]:
        """
        Get final display text and complete thoughts.
        Handles any remaining partial content in buffer.
        """
        return self.get_display_text(), self.get_complete_thoughts()


# --- Display Helpers ---

def print_banner():
    """Print the DevIn startup banner."""
    banner = Text()
    banner.append("╔══════════════════════════════════════════════════════╗\n", style="cyan")
    banner.append("║                                                      ║\n", style="cyan")
    banner.append("║", style="cyan")
    banner.append("     DevIn - Your personal Developer Intelligence     ", style="bold white")
    banner.append("║\n", style="cyan")
    banner.append("║", style="cyan")
    banner.append("                 Autonomous AI Agent                  ", style="dim white")
    banner.append("║\n", style="cyan")
    banner.append("║                                                      ║\n", style="cyan")
    banner.append("╚══════════════════════════════════════════════════════╝", style="cyan")
    console.print(banner)
    console.print(
        '  Type your message to chat. Type [bold cyan]/help[/] for commands.\n',
        style="dim",
    )


def print_thinking(iteration: int):
    """Display thinking indicator."""
    console.print(f"  [devin.iteration]🧠 Thinking (step {iteration})...[/]")


def print_tool_call(name: str, args: dict):
    """Display a tool call."""
    args_str = json.dumps(args, indent=2) if args else "{}"
    console.print(f"  [devin.tool_name]🔧 Using tool: {name}[/]")
    if args_str != "{}":
        # Truncate long args for display
        display_args = args_str if len(args_str) < 300 else args_str[:300] + "\n  ..."
        console.print(f"  [devin.tool_input]{display_args}[/]")


def print_tool_result(content: str):
    """Display tool result (truncated)."""
    if len(content) > 800:
        content = content[:800] + "\n  ... (truncated)"
    console.print(Panel(
        Text(content, style="green"),
        title="[bold]Tool Result[/]",
        border_style="dim green",
        padding=(0, 1),
    ))


def strip_thoughts(content: str) -> str:
    # Remove <thought>...</thought> blocks entirely from user-facing output
    clean = re.sub(r'<thought>.*?</thought>', '', content, flags=re.DOTALL)
    return clean.strip()

def print_response(content: str):
    """Display the agent's final response as rendered markdown."""
    clean_content = strip_thoughts(content)
    if not clean_content:
        return
    console.print()
    console.print(Panel(
        Markdown(clean_content),
        title="[bold cyan]DevIn[/]",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()


def print_error(message: str):
    """Display an error message."""
    console.print(f"  [devin.error]❌ Error: {message}[/]")


def handle_slash_command(
    command: str,
    conversation: list,
    debug_mode: bool,
    agent,
    registry,
) -> tuple[list, bool, bool]:
    """
    Handle slash commands.

    Returns (updated_conversation, updated_debug_mode, should_continue_loop).
    """
    cmd = command.strip().lower()

    if cmd in ("/exit", "/quit"):
        console.print("\n  [devin.system]👋 Goodbye! DevIn signing off.[/]\n")
        return conversation, debug_mode, False

    elif cmd == "/help":
        console.print("\n  [bold]Available Commands:[/]")
        for slash, desc in SLASH_COMMANDS.items():
            console.print(f"    [cyan]{slash:12}[/] — {desc}")
        console.print()

    elif cmd == "/clear":
        console.print("  [devin.system]🗑️  Conversation cleared.[/]\n")
        return [], debug_mode, True

    elif cmd == "/history":
        if not conversation:
            console.print("  [dim]No conversation history yet.[/]\n")
        else:
            console.print(f"\n  [bold]Conversation History ({len(conversation)} messages):[/]")
            for msg in conversation:
                if isinstance(msg, HumanMessage):
                    content = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
                    console.print(f"    [devin.user]You:[/] {content}")
                elif isinstance(msg, AIMessage) and not msg.tool_calls:
                    # Filter thoughts from history view
                    clean_content = re.sub(r'<thought>.*?</thought>', '', msg.content, flags=re.DOTALL).strip()
                    content = clean_content[:80] + "..." if len(clean_content) > 80 else clean_content
                    console.print(f"    [cyan]DevIn:[/] {content}")
            console.print()

    elif cmd == "/debug":
        debug_mode = not debug_mode
        state = "ON" if debug_mode else "OFF"
        console.print(f"  [devin.system]🔍 Debug mode: {state}[/]\n")
        if debug_mode:
            logging.getLogger("devin").setLevel(logging.DEBUG)
            logging.getLogger("langgraph").setLevel(logging.DEBUG)
        else:
            logging.getLogger("devin").setLevel(logging.WARNING)
            logging.getLogger("langgraph").setLevel(logging.WARNING)

    elif cmd == "/tools":
        console.print("\n  [bold]Registered Tools:[/]")
        for cat, tool_names in registry.get_categories().items():
            console.print(f"    [magenta]{cat}:[/]")
            for name in tool_names:
                tool = registry.get_tool(name)
                console.print(f"      • [bold]{name}[/] — {tool.description[:80]}")
        console.print()

    elif cmd.startswith("/model"):
        parts = command.strip().split(maxsplit=1)
        if len(parts) == 1:
            from devin.settings import settings
            console.print(f"  [devin.system]Current model: {settings.devin_default_model}[/]\n")
        else:
            console.print(f"  [devin.system]Model switching not yet implemented.[/]\n")

    else:
        console.print(f"  [devin.error]Unknown command: {cmd}. Type /help for options.[/]\n")

    return conversation, debug_mode, True


SIMPLE_INTENTS = [
    "hi", "hello", "hey", "thanks", "thank you", "bye", "goodbye",
    "what can you do", "help", "who are you", "what are you",
    "good morning", "good evening", "how are you"
]

def _is_simple_intent(message: str) -> bool:
    """Detect casual/greeting messages that don't need full agent graph."""
    msg = message.lower().strip()
    # Short messages (4 words or less) that match known intents
    if len(msg.split()) <= 5:
        return any(intent in msg for intent in SIMPLE_INTENTS)
    return False

# --- Main Loop (Async) ---

async def run_cli_async():
    """Run the DevIn interactive CLI with async streaming."""
    from devin.agent.graph import build_graph
    from devin.tools.registry import create_default_registry

    # Initialize
    print_banner()

    try:
        registry = create_default_registry()
    except Exception as e:
        print_error(f"Failed to load tools: {e}")
        return

    try:
        agent = build_graph(registry=registry)
    except Exception as e:
        print_error(f"Failed to create agent: {e}")
        console.print("  [dim]Make sure your API keys are set in .env[/]")
        return

    console.print()

    interaction_logger = InteractionLogger()
    conversation: list = []
    debug_mode = False

    while True:
        try:
            # Get user input (blocking call in separate thread to remain responsive)
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: console.input("[bold white]You ▶ [/]").strip()
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n  [devin.system]👋 Goodbye![/]\n")
                break

            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                conversation, debug_mode, should_continue = handle_slash_command(
                    user_input, conversation, debug_mode, agent, registry
                )
                if not should_continue:
                    break
                continue

            # Log the user message
            interaction_logger.log("user", user_input)

            # Add to conversation
            user_message = HumanMessage(content=user_input)
            conversation.append(user_message)

            full_messages = conversation

            console.print()  # spacing

            # --- Fast path for simple intents (saves ~5,000 tokens per greeting) ---
            if _is_simple_intent(user_input):
                try:
                    from devin.agent.llm_provider import create_llm
                    quick_llm = create_llm()
                    quick_response = quick_llm.invoke([
                        SystemMessage(content=(
                            "You are DevIn, an autonomous AI coding assistant. "
                            "Respond naturally and concisely to casual messages. "
                            "If asked what you can do, mention: writing code, editing files, "
                            "running commands, debugging, and researching."
                        )),
                        HumanMessage(content=user_input)
                    ])
                    response_text = quick_response.content if hasattr(quick_response, 'content') else str(quick_response)
                    interaction_logger.log("assistant", response_text, {"fast_path": True})
                    # We appended user_message earlier
                    conversation.append(AIMessage(content=response_text))
                    print_response(response_text)
                    continue  # Skip full graph execution entirely
                except Exception as e:
                    logger.debug(f"Fast path failed, falling back to full graph: {e}")
                    # Fall through to full graph if fast path fails

            # --- Stream the agent execution with astream_events(version="v2") ---
            try:
                final_response = ""
                final_response_str = ""
                already_rendered = False
                iteration = 0
                thought_buffer = ThoughtBuffer()
                printed_thoughts = 0
                executed_tasks = []
                total_token_usage = {}

                agent_status = console.status("  [cyan]🧠 Thinking...[/]", spinner="dots")
                agent_status.start()

                # Stream events from the agent using v2 format
                try:
                    async for event in agent.astream_events(
                        {"messages": full_messages, "iteration_count": 0},
                        version="v2",
                    ):
                        event_type = event.get("event")
                        
                        if event_type == "on_chain_start":
                            name = event.get("name", "")
                            if name == "editor_tools":
                                agent_status.stop()

                        elif event_type == "on_chain_end":
                            name = event.get("name", "")
                            if name == "editor_tools":
                                agent_status.start()
                                agent_status.update("  [cyan]🧠 Thinking...[/]")
                            
                            if name == "LangGraph":
                                final_state = event.get("data", {}).get("output", {})
                                if isinstance(final_state, dict):
                                    if "messages" in final_state:
                                        conversation = list(final_state["messages"])
                                        if conversation:
                                            last_msg = conversation[-1]
                                            if hasattr(last_msg, "content") and last_msg.content:
                                                already_rendered = True
                                                final_response_str = str(last_msg.content)
                                    if "token_usage" in final_state:
                                        total_token_usage = final_state["token_usage"]

                        elif event_type in ["on_chat_model_stream", "on_llm_stream"]:
                            data = event.get("data", {})
                            chunk = data.get("chunk")
                            chunk_content = ""
                            if chunk:
                                if hasattr(chunk, "content"):
                                    c = chunk.content
                                    if isinstance(c, str):
                                        chunk_content = c
                                    elif isinstance(c, list):
                                        for item in c:
                                            if isinstance(item, dict) and "text" in item:
                                                chunk_content += item["text"]
                                            elif isinstance(item, str):
                                                chunk_content += item
                                elif isinstance(chunk, dict):
                                    c = chunk.get("content", "")
                                    if isinstance(c, str):
                                        chunk_content = c
                                    elif isinstance(c, list):
                                        for item in c:
                                            if isinstance(item, dict) and "text" in item:
                                                chunk_content += item["text"]
                                elif isinstance(chunk, str):
                                    chunk_content = chunk
                            if chunk_content:
                                final_response += chunk_content
                                thought_buffer.add_chunk(chunk_content)
                                
                                complete_thoughts = thought_buffer.get_complete_thoughts()
                                if len(complete_thoughts) > printed_thoughts:
                                    agent_status.stop()
                                    for t in complete_thoughts[printed_thoughts:]:
                                        inner = re.sub(r'<thought>|</thought>', '', t).strip()
                                        if inner:
                                            # Using the user's styling request
                                            console.print(f"  [dim italic]💭 {inner[:200]}...[/]" if len(inner) > 200 else f"  [dim italic]💭 {inner}[/]")
                                    agent_status.start()
                                    printed_thoughts = len(complete_thoughts)

                        elif event_type == "on_tool_start":
                            data = event.get("data", {})
                            name = event.get("name", "")
                            input_data = data.get("input", {})
                            if name and name not in ["RunnableSequence", "ToolNode", "editor_tools", "architect_tools"]:
                                iteration += 1
                                agent_status.stop()
                                print_tool_call(name, input_data)
                                agent_status.start()
                                agent_status.update(f"  [magenta]🔧 Using tool: {name}...[/]")
                                task_entry = {"tool": name, "input": input_data, "result": None, "run_id": event.get("run_id")}
                                executed_tasks.append(task_entry)

                        elif event_type == "on_tool_end":
                            name = event.get("name", "")
                            if name in ["RunnableSequence", "ToolNode", "editor_tools", "architect_tools"]:
                                continue
                            
                            data = event.get("data", {})
                            run_id = event.get("run_id")
                            if "output" in data:
                                output = data["output"]
                                res = ""
                                if isinstance(output, dict) and "messages" in output:
                                    messages_out = output["messages"]
                                    if messages_out and hasattr(messages_out[-1], 'content'):
                                        res = str(messages_out[-1].content)
                                elif hasattr(output, 'content'):
                                    res = str(output.content)
                                else:
                                    res = str(output)
                                    
                                res = res.strip()
                                # Update the correct task by tracking run_id or fallback to name
                                for task in reversed(executed_tasks):
                                    if (task.get("run_id") == run_id or task["tool"] == name) and task["result"] is None:
                                        task["result"] = res
                                        break
                                
                                agent_status.stop()
                                print_tool_result(res)
                                agent_status.start()
                                    
                            agent_status.update("  [cyan]🧠 Thinking...[/]")

                except Exception as e:
                    agent_status.stop()
                    print_error(f"Execution failed: {e}")
                    logger.exception("Graph execution failed.")
                    if conversation and isinstance(conversation[-1], HumanMessage):
                        conversation.pop()
                    console.print("\n  [devin.system]⚠️ Graph execution crashed. State has been reset. Ready for next input.[/]\n")
                    continue
                finally:
                    agent_status.stop()

                if executed_tasks:
                    summary_text = ""
                    for idx, task in enumerate(executed_tasks, 1):
                        tool_name = task["tool"]
                        res = task["result"] or "Done"
                        res_str = res if len(res) < 150 else res[:150] + "..."
                        res_str = res_str.replace("[", "\\[").replace("]", "\\]")
                        summary_text += f"[bold magenta]{idx}. {tool_name}[/] → [dim green]{res_str}[/]\n"

                    console.print()
                    console.print(Panel(summary_text.strip(), title="[bold green]📋 Task Summary[/]", border_style="green", padding=(1, 2)))

                if already_rendered and final_response_str:
                    interaction_logger.log("assistant", final_response_str, {"iterations": iteration})
                    print_response(final_response_str)
                elif not already_rendered and final_response:
                    interaction_logger.log("assistant", final_response, {"iterations": iteration})
                    print_response(final_response)
                elif not already_rendered and not final_response:
                    print_error("Agent did not produce a response.")
                    
                if total_token_usage and total_token_usage.get("total_tokens", 0) > 0:
                    in_t = total_token_usage.get("input_tokens", 0)
                    out_t = total_token_usage.get("output_tokens", 0)
                    tot_t = total_token_usage.get("total_tokens", 0)
                    calls = total_token_usage.get("llm_calls", 0)
                    console.print(f"  [dim]📊 {tot_t:,} tokens ({in_t:,} in / {out_t:,} out) · {calls} LLM calls[/]")

            except KeyboardInterrupt:
                console.print("\n  [devin.system]⚡ Interrupted. Ready for next input.[/]\n")
                continue
        except KeyboardInterrupt:
            console.print("\n  [devin.system]👋 Goodbye![/]\n")
            break


def main():
    """Entry point for the `devin` command."""
    try:
        asyncio.run(run_cli_async())
    except KeyboardInterrupt:
        console.print("\n  [devin.system]👋 Goodbye![/]\n")


if __name__ == "__main__":
    main()

