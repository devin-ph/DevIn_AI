"""
DevIn CLI — Entry point.
"""

import sys
import asyncio
import logging
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from devin.cli.renderer import (
    console,
    print_banner,
    print_error,
    print_response,
    print_tool_call,
    print_tool_result,
    print_token_summary,
    print_task_summary,
    ThoughtBuffer,
)
from devin.cli.commands import handle_slash_command
from devin.agent.history import InteractionLogger
from devin.constants import TECHNICAL_KEYWORDS, SIMPLE_INTENTS

# Force UTF-8 rendering on Windows terminals to prevent rich crashes
if hasattr(sys.stdout, 'reconfigure'):
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.WARNING, format="%(name)s | %(message)s")
logger = logging.getLogger("devin")


def _is_simple_intent(message: str) -> bool:
    msg = message.lower().strip()
    words = msg.split()
    if len(words) <= 4:
        return not any(kw in msg for kw in TECHNICAL_KEYWORDS)
    return any(p in msg for p in SIMPLE_INTENTS)


async def run_cli_async():
    """Run the DevIn interactive CLI with async streaming."""
    from devin.agent.graph import build_graph
    from devin.tools.registry import create_default_registry
    import re

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

            if user_input.startswith("/"):
                conversation, debug_mode, should_continue = handle_slash_command(
                    user_input, conversation, debug_mode, agent, registry
                )
                if not should_continue:
                    break
                continue

            interaction_logger.log("user", user_input)
            user_message = HumanMessage(content=user_input)
            conversation.append(user_message)
            full_messages = conversation

            console.print()

            if _is_simple_intent(user_input):
                try:
                    from devin.agent.llm_provider import create_llm
                    quick_llm = create_llm()
                    quick_response = quick_llm.invoke([
                        SystemMessage(content=(
                            "You are DevIn, a personal AI coding assistant. "
                            "You do not run code autonomously unless requested. "
                            "You chat casually in the language the user speaks."
                        )),
                        HumanMessage(content=user_input)
                    ])
                    response_text = quick_response.content if hasattr(quick_response, 'content') else str(quick_response)
                    interaction_logger.log("assistant", response_text, {"fast_path": True})
                    conversation.append(AIMessage(content=response_text))
                    print_response(response_text)
                    if hasattr(quick_response, 'usage_metadata'): print_token_summary(quick_response.usage_metadata)
                    continue
                except Exception as e:
                    logger.debug(f"Fast path failed, falling back to full graph: {e}")

            try:
                from devin.cli.stream import _process_stream
                
                executed_tasks = []
                agent_status = console.status("  [cyan]🧠 Thinking...[/]", spinner="dots")
                agent_status.start()

                try:
                    stream_res = await _process_stream(agent, agent_status, full_messages, executed_tasks)
                    
                    final_response = stream_res["final_response"]
                    final_response_str = stream_res["final_response_str"]
                    already_rendered = stream_res["already_rendered"]
                    iteration = stream_res["iteration"]
                    total_token_usage = stream_res["total_token_usage"]
                    
                    if stream_res.get("updated_conversation") is not None:
                        conversation = stream_res["updated_conversation"]

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

                print_task_summary(executed_tasks)

                if already_rendered and final_response_str:
                    interaction_logger.log("assistant", final_response_str, {"iterations": iteration})
                    print_response(final_response_str)
                elif not already_rendered and final_response:
                    interaction_logger.log("assistant", final_response, {"iterations": iteration})
                    print_response(final_response)
                elif not already_rendered and not final_response:
                    print_error("Agent did not produce a response.")
                    
                print_token_summary(total_token_usage)

            except KeyboardInterrupt:
                console.print("\n  [devin.system]⚡ Interrupted. Ready for next input.[/]\n")
                continue
        except KeyboardInterrupt:
            console.print("\n  [devin.system]👋 Goodbye![/]\n")
            break

def main():
    """Entry point for the devin command."""
    try:
        asyncio.run(run_cli_async())
    except KeyboardInterrupt:
        console.print("\n  [devin.system]👋 Goodbye![/]\n")

if __name__ == "__main__":
    main()