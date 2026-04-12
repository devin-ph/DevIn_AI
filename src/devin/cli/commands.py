"""
Handlers for DevIn slash commands.
"""

import logging
import re
from langchain_core.messages import AIMessage, HumanMessage

from devin.cli.renderer import console
from devin.constants import SLASH_COMMANDS

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
        from devin.agent.memory import MemoryEngine
        if conversation:
            memory = MemoryEngine()
            proposal = memory.propose_save(conversation)
            console.print(memory.format_proposal(proposal))
            try:
                ans = console.input("Choice ▶ ").strip().lower()
                if ans in ("save all", "save", "yes", "y", "all"):
                    memory.save(proposal)
                    console.print("  [devin.system]💾 Memory saved.[/]\n")
            except (EOFError, KeyboardInterrupt):
                pass
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
