"""
DevIn CLI — Rich terminal interface for interacting with the agent.

This is the primary user interface for DevIn through Phases 1-4.
Features:
- Rich formatted output with colors and panels
- Real-time streaming of agent reasoning and tool calls
- Slash commands (/help, /clear, /debug, /exit)
- Full conversation history
- JSON logging of all interactions
"""

from __future__ import annotations

import json
import logging
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


# --- Display Helpers ---

def print_banner():
    """Print the DevIn startup banner."""
    banner = Text()
    banner.append("╔══════════════════════════════════════════════════════╗\n", style="cyan")
    banner.append("║", style="cyan")
    banner.append("   D e v I n - Your personal Developer Intelligence   ", style="bold white")
    banner.append("║\n", style="cyan")
    banner.append("║", style="cyan")
    banner.append("                 Autonomous AI Agent                  ", style="dim white")
    banner.append("║\n", style="cyan")
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
    if len(content) > 500:
        content = content[:500] + "\n  ... (truncated)"
    console.print(Panel(content, title="Tool Result", border_style="green", padding=(0, 1)))


def print_response(content: str):
    """Display the agent's final response as rendered markdown."""
    console.print()
    console.print(Panel(
        Markdown(content),
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


# --- Main Loop ---

def run_cli():
    """Run the DevIn interactive CLI."""
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
            # Get user input
            try:
                user_input = console.input("[bold white]You ▶ [/]").strip()
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

            # --- Stream the agent execution ---
            try:
                final_response = ""
                iteration = 0
                live_render = None

                import re

                def clean_thought_blocks(text: str) -> str:
                    # Remove anything inside <thought> tags (non-greedy)
                    return re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL).strip()

                from langchain_core.messages import AIMessageChunk
                for mode, payload in agent.stream(
                    {"messages": full_messages, "iteration_count": 0},
                    stream_mode=["messages", "updates"],
                ):
                    if mode == "messages":
                        chunk, metadata = payload
                        if metadata.get("langgraph_node") in ["architect", "editor", "validator"] and isinstance(chunk, AIMessageChunk):
                            if not chunk.tool_call_chunks and not chunk.tool_calls:
                                content = chunk.content
                                if isinstance(content, list):
                                    content = "".join(
                                        item.get("text", "") if isinstance(item, dict) else str(item)
                                        for item in content
                                    )
                                if content:
                                    final_response += content
                                    
                                    # Filter thoughts for display
                                    display_text = clean_thought_blocks(final_response)
                                    
                                    if live_render is None:
                                        console.print()
                                        live_render = Live(
                                            Panel(Markdown(display_text or "🧠 *Thinking...*"), title="[bold cyan]DevIn[/]", border_style="cyan", padding=(1, 2)),
                                            console=console,
                                            refresh_per_second=15,
                                            transient=False,
                                        )
                                        live_render.start()
                                    
                                    live_render.update(Panel(Markdown(display_text or "🧠 *Thinking...*"), title="[bold cyan]DevIn[/]", border_style="cyan", padding=(1, 2)))

                    elif mode == "updates":
                        if live_render is not None:
                            live_render.stop()
                            live_render = None

                        for node_name, state_update in payload.items():
                            if node_name in ["architect", "editor", "validator"]:
                                if node_name == "architect":
                                    # We don't necessarily increment iteration for architect if we track total across graph,
                                    # but let's just increment to show progress.
                                    iteration += 1
                                    
                                messages = state_update.get("messages", [])
                                for msg in messages:
                                    if isinstance(msg, AIMessage):
                                        if msg.tool_calls:
                                            # Differentiate node thinking phases
                                            if node_name == "architect":
                                                console.print(f"\n[cyan]🧠 Architect Planning (Iteration {iteration})...[/]")
                                            elif node_name == "validator":
                                                console.print(f"\n[green]🔍 Validator Reviewing...[/]")
                                            else:
                                                console.print(f"\n[magenta]⚡ Editor Executing...[/]")
                                                
                                            for tc in msg.tool_calls:
                                                print_tool_call(tc["name"], tc.get("args", {}))
                            
                            elif node_name in ["architect_tools", "editor_tools"]:
                                messages = state_update.get("messages", [])
                                for msg in messages:
                                    if isinstance(msg, ToolMessage):
                                        c = msg.content if isinstance(msg.content, str) else str(msg.content)
                                        print_tool_result(c)

                if live_render is not None:
                    live_render.stop()

                if final_response:
                    conversation.append(AIMessage(content=final_response))
                    interaction_logger.log("assistant", final_response, {"iterations": iteration})
                else:
                    print_error("Agent did not produce a response.")

            except KeyboardInterrupt:
                console.print("\n  [devin.system]⚡ Interrupted. Ready for next input.[/]\n")
                continue
            except Exception as e:
                print_error(f"Agent error: {e}")
                if debug_mode:
                    console.print_exception()
                continue

        except KeyboardInterrupt:
            console.print("\n  [devin.system]👋 Goodbye![/]\n")
            break


def main():
    """Entry point for the `devin` command."""
    run_cli()


if __name__ == "__main__":
    main()
