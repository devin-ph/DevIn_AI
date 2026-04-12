"""
Rich terminal rendering for DevIn.
Handles formatted output, themes, panels, and streaming thought tags.
"""
from __future__ import annotations

import json
import re
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
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

# --- Thought Buffer ---
class ThoughtBuffer:
    """
    Accumulates text chunks to cleanly parse <thought> XML tags.
    Prevents broken tags (e.g., '<thou' + 'ght>') from rendering.
    """

    def __init__(self):
        self.buffer = ""
        self.complete_blocks: list[str] = []
        self.display_text = ""

    def add_chunk(self, chunk: str) -> str:
        """Add a chunk and return displayable text (without <thought> tags)."""
        self.buffer += chunk
        self._process_buffer()
        return self.display_text

    def _process_buffer(self):
        """Extract complete <thought> blocks and update display text."""
        self.complete_blocks = []
        self.display_text = ""

        thought_pattern = r'<thought>.*?</thought>'
        for match in re.finditer(thought_pattern, self.buffer, re.DOTALL):
            self.complete_blocks.append(match.group())

        self.display_text = re.sub(thought_pattern, '', self.buffer, flags=re.DOTALL).strip()

    def get_display_text(self) -> str:
        return self.display_text

    def get_complete_thoughts(self) -> list[str]:
        return self.complete_blocks

    def finalize(self) -> tuple[str, list[str]]:
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

def print_token_summary(total_token_usage: dict):
    if total_token_usage and total_token_usage.get("total_tokens", 0) > 0:
        in_t = total_token_usage.get("input_tokens", 0)
        out_t = total_token_usage.get("output_tokens", 0)
        tot_t = total_token_usage.get("total_tokens", 0)
        calls = total_token_usage.get("llm_calls", 0)
        console.print(f"  [dim]📊 {tot_t:,} tokens ({in_t:,} in / {out_t:,} out) · {calls} LLM calls[/]")

def print_task_summary(executed_tasks: list):
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
