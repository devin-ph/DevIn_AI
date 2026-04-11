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
    if len(content) > 500:
        content = content[:500] + "\n  ... (truncated)"
    console.print(Panel(content, title="Tool Result", border_style="green", padding=(0, 1)))


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

            # --- Stream the agent execution with astream_events(version="v2") ---
            try:
                final_response = ""
                already_rendered = False
                iteration = 0
                live_render = None
                thought_buffer = ThoughtBuffer()

                # Stream events from the agent using v2 format
                try:
                    async for event in agent.astream_events(
                        {"messages": full_messages, "iteration_count": 0},
                        version="v2",
                    ):
                        # Handle interruption during streaming
                        event_type = event.get("event")
                        
                        # Process on_chain_start events (tool initialization)
                        if event_type == "on_chain_start":
                            metadata = event.get("metadata", {})
                            name = event.get("name", "")
                            if name and name not in ["RunnableSequence"]:
                                # Tool started
                                pass

                        # Process on_chain_end events (tool termination and final state)
                        elif event_type == "on_chain_end":
                            name = event.get("name", "")
                            
                            # Capture final conversation state explicitly
                            if name == "LangGraph":
                                final_state = event.get("data", {}).get("output", {})
                                if isinstance(final_state, dict) and "messages" in final_state:
                                    conversation = list(final_state["messages"])
                                    if conversation:
                                        last_msg = conversation[-1]
                                        if hasattr(last_msg, "content") and last_msg.content:
                                            # We found the final response directly in the final state
                                            already_rendered = True
                                            interaction_logger.log("assistant", str(last_msg.content), {"iterations": iteration})
                                            print_response(str(last_msg.content))
                            
                            if name and name not in ["RunnableSequence"]:
                                # Other chain ends
                                pass

# Process on_chat_model_stream / on_llm_stream events
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
                                # Buffer the chunk to handle partial <thought> tags
                                display_text = thought_buffer.add_chunk(chunk_content)
                                
                                if live_render is None and display_text:
                                    console.print()
                                    live_render = Live(
                                        Panel(
                                            Markdown(display_text or "🧠 *Thinking...*"),
                                            title="[bold cyan]DevIn[/]",
                                            border_style="cyan",
                                            padding=(1, 2)
                                        ),
                                        console=console,
                                        refresh_per_second=15,
                                        transient=True,
                                    )
                                    live_render.start()
                                elif live_render is not None:
                                    current_display = thought_buffer.get_display_text()
                                    live_render.update(Panel(
                                        Markdown(current_display or "🧠 *Thinking...*"),
                                        title="[bold cyan]DevIn[/]",
                                        border_style="cyan",
                                        padding=(1, 2)
                                    ))

                        # Process on_tool_start events (tool execution started)
                        elif event_type == "on_tool_start":
                            data = event.get("data", {})
                            name = event.get("name", "")
                            input_data = data.get("input", {})
                            if name:
                                if live_render is not None:
                                    live_render.stop()
                                    live_render = None
                                    thought_buffer = ThoughtBuffer()
                                iteration += 1
                                print_tool_call(name, input_data)

                        # Process on_tool_end events (tool execution completed)
                        elif event_type == "on_tool_end":
                            name = event.get("name", "")
                            # Skip printing wrapper LangGraph nodes 
                            if name in ["RunnableSequence", "ToolNode", "editor_tools", "architect_tools"]:
                                continue
                            
                            data = event.get("data", {})
                            if "output" in data:
                                output = data["output"]
                                # Safely unwrap dicts with nested messages
                                if isinstance(output, dict) and "messages" in output:
                                    messages = output["messages"]
                                    if messages and hasattr(messages[-1], 'content'):
                                        print_tool_result(str(messages[-1].content))
                                        continue
                                        
                                if hasattr(output, 'content'):
                                    print_tool_result(str(output.content))
                                elif isinstance(output, str):
                                    print_tool_result(output)
                                else:
                                    print_tool_result(str(output))

                except KeyboardInterrupt:
                    if live_render is not None:
                        live_render.stop()
                    console.print("\n  [devin.system]⚡ Interrupted. Ready for next input.[/]\n")
                    continue

                # Finalize thought buffer
                if live_render is not None:
                    live_render.stop()
                    live_render = None

                if not already_rendered and final_response:
                    interaction_logger.log("assistant", final_response, {"iterations": iteration})
                    print_response(final_response)
                elif not already_rendered and not final_response:
                    print_error("Agent did not produce a response.")

            except KeyboardInterrupt:
                console.print("\n  [devin.system]⚡ Interrupted. Ready for next input.[/]\n")
                continue
            except Exception as e:
                print_error(f"Agent error: {e}")
                if debug_mode:
                    console.print_exception()
                
                # Cleanup broken state to avoid indefinite hang
                if live_render is not None:
                    try:
                        live_render.stop()
                    except:
                        pass
                
                # Pop the broken human message from conversation so it can be retried cleanly
                if conversation and isinstance(conversation[-1], HumanMessage):
                    conversation.pop()
                    
                console.print("\n  [devin.system]⚠️ Graph execution crashed. State has been reset. Ready for next input.[/]\n")
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

