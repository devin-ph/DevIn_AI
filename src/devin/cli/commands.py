"""
Handlers for DevIn slash commands.
"""

import logging
import re
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from devin.cli.renderer import console
from devin.constants import SLASH_COMMANDS

logger = logging.getLogger(__name__)


THINK_SYSTEM_PROMPT = """You are DevIn — a brilliant, direct friend who helps think through hard decisions.

When given a question or dilemma, you reason like this:

1. RESTATE: Say back what the real question actually is (often different from what was asked).
2. TRADEOFFS: Name the 2-3 actual stakes. Not surface-level — what's really at risk.
3. OPINION: Give a clear recommendation. Not "it depends." Pick a side and say why. CRITICAL: If memory context shows the person already uses a related tool, call that out immediately. Don't pretend you don't know.
4. ONE QUESTION: Ask one sharp follow-up that would change your recommendation if answered differently.

Rules:
- ZERO hedging. No "có thể", "maybe", "it depends". Pick a side.
- If you're unsure, say "tớ không biết" — that's honest. Hedging is not.
- If something is a bad idea, say it once clearly. Then respect the decision.
- Use the personal memory context below to make the advice specific to this person.
- Keep it under 200 words. Dense > verbose.
- Talk like a friend, not a consultant.
- If memory context is empty or template-like, still give a real take — just more general.
"""


def _run_think(query: str, memory_engine) -> str:
    """
    Core /think logic.
    Loads personal memory, injects into companion LLM, returns structured reasoning.
    """
    memory_context = ""
    if memory_engine is not None:
        try:
            memory_context = memory_engine.load_companion_context()
        except Exception as e:
            logger.debug(f"Could not load companion context: {e}")

    system_content = THINK_SYSTEM_PROMPT
    if memory_context and "[[ PERSONAL MEMORY ]]" in memory_context:
        system_content += f"\n\n{memory_context}"

    try:
        from devin.agent.graph import create_companion_chain
        llm = create_companion_chain()
    except Exception:
        try:
            from devin.agent.llm_provider import create_llm
            llm = create_llm()
        except Exception as e:
            return f"[devin.error] Could not load LLM: {e}"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=f"/think {query}"),
    ]

    try:
        response = llm.invoke(messages)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        return f"[devin.error] /think failed: {e}"


def handle_slash_command(
    command: str,
    conversation: list,
    debug_mode: bool,
    agent,
    registry,
    memory_engine=None,
) -> tuple[list, bool, bool]:
    """
    Handle slash commands.

    Returns (updated_conversation, updated_debug_mode, should_continue_loop).
    """
    raw = command.strip()
    cmd_parts = raw.split(maxsplit=1)
    cmd = cmd_parts[0].lower()
    rest = cmd_parts[1] if len(cmd_parts) > 1 else ""

    if cmd in ("/exit", "/quit"):
        from devin.agent.memory import MemoryEngine
        if conversation:
            memory = memory_engine or MemoryEngine()
            summary = memory.propose_save(conversation)
            
            if not any(summary.values()):
                pass
            else:
                console.print(memory.format_proposal(summary))
                try:
                    choice = console.input("Choice ▶ ").strip().lower()
                    if choice in ('', 'y', 'yes', 'save all', 'save', 'all'):
                        memory.save(summary)
                        console.print("  [devin.system]💾 Memory saved.[/]\n")
                    
                    elif choice == 'skip':
                        console.print("  [dim]Memory not saved.[/]")
                    
                    elif choice == 'edit':
                        console.print("  [dim]Edit each section. Press Enter to keep current value.[/]")
                        
                        edited = {}
                        if summary.get('_life_struct'):
                            edited['_life_struct'] = summary['_life_struct']
                        
                        if summary.get('state'):
                            current = summary['state']
                            console.print(f"  PROJECT_STATE (current): {current}")
                            new_val = console.input("  New value (Enter to keep): ").strip()
                            edited['state'] = new_val if new_val else current
                        
                        if summary.get('decisions'):
                            current = summary['decisions']
                            console.print(f"  DECISIONS (current): {current}")
                            new_val = console.input("  New value (Enter to keep): ").strip()
                            edited['decisions'] = new_val if new_val else current
                            
                        if summary.get('prefs'):
                            current = summary['prefs']
                            console.print(f"  PREFERENCES (current): {current}")
                            new_val = console.input("  New value (Enter to keep): ").strip()
                            edited['prefs'] = new_val if new_val else current
                            
                        if summary.get('bugs'):
                            current = summary['bugs']
                            console.print(f"  BUGS (current): {current}")
                            new_val = console.input("  New value (Enter to keep): ").strip()
                            edited['bugs'] = new_val if new_val else current

                        if summary.get('life'):
                            current = summary['life']
                            console.print(f"  LIFE (current): {current}")
                            new_val = console.input("  New value (Enter to keep): ").strip()
                            edited['life'] = new_val if new_val else current
                            if new_val:
                                edited.pop('_life_struct', None)
                        
                        console.print("\n  Save edited memory? [Y/n]: ")
                        confirm = console.input().strip().lower()
                        if confirm in ('', 'y', 'yes'):
                            memory.save(edited)
                            console.print("  [green]✅ Edited memory saved.[/]")
                        else:
                            console.print("  [dim]Memory not saved.[/]")
                            
                    else:
                        console.print("  [dim]Unrecognized choice. Memory not saved.[/]")
                except (EOFError, KeyboardInterrupt):
                    pass
        console.print("\n  [devin.system]👋 Goodbye! DevIn signing off.[/]\n")
        return conversation, debug_mode, False

    elif cmd == "/think":
        if not rest.strip():
            console.print("  [dim]Usage: /think <question or decision>[/]")
            console.print("  [dim]Example: /think should I drop this course this semester?[/]\n")
            return conversation, debug_mode, True

        console.print()
        status = console.status("  [cyan]🧠 Thinking...[/]", spinner="dots")
        status.start()

        try:
            result = _run_think(rest.strip(), memory_engine)
        finally:
            status.stop()

        from devin.cli.renderer import print_response
        print_response(result)

        conversation.append(HumanMessage(content=f"/think {rest.strip()}"))
        conversation.append(AIMessage(content=result))
        return conversation, debug_mode, True

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

    elif cmd == "/model":
        if not rest:
            from devin.settings import settings
            console.print(f"  [devin.system]Current model: {settings.devin_default_model}[/]\n")
        else:
            console.print(f"  [devin.system]Model switching not yet implemented.[/]\n")

    else:
        console.print(f"  [devin.error]Unknown command: {cmd}. Type /help for options.[/]\n")

    return conversation, debug_mode, True