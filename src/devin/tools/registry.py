"""
DevIn Tool Registry — Central manager for all agent tools.

The registry is the single point of contact for tool discovery, registration,
and retrieval. It ensures each tool has a validated schema and provides
the tool list to LangGraph for binding to the LLM.

Design principles:
- Every tool is a LangChain BaseTool (or @tool decorated function)
- Tools are grouped by category for future multi-agent routing
- The registry validates that no two tools share the same name
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry that manages all tools available to DevIn.

    Usage:
        registry = ToolRegistry()
        registry.register(my_tool, category="search")
        tools = registry.get_tools()                   # all tools
        tools = registry.get_tools(category="search")  # filtered
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = {}

    def register(self, tool: BaseTool, category: str = "general") -> None:
        """Register a tool. Raises ValueError if name already exists."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")

        self._tools[tool.name] = tool

        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(tool.name)

        logger.info(f"Registered tool: {tool.name} (category: {category})")

    def get_tool(self, name: str) -> BaseTool:
        """Get a tool by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found. Available: {list(self._tools.keys())}")
        return self._tools[name]

    def get_tools(self, category: str | None = None) -> list[BaseTool]:
        """Get all tools, optionally filtered by category."""
        if category is None:
            return list(self._tools.values())

        if category not in self._categories:
            return []

        return [self._tools[name] for name in self._categories[category]]

    def get_tool_names(self) -> list[str]:
        """Get all registered tool names."""
        return list(self._tools.keys())

    def get_categories(self) -> dict[str, list[str]]:
        """Get category → tool name mapping."""
        return dict(self._categories)

    @property
    def count(self) -> int:
        return len(self._tools)

    def get_tool_descriptions(self) -> str:
        """Format all tool descriptions for prompt injection."""
        lines = []
        for name, tool in self._tools.items():
            lines.append(f"- **{name}**: {tool.description}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"ToolRegistry({self.count} tools: {self.get_tool_names()})"


def create_default_registry() -> ToolRegistry:
    """Create a registry pre-loaded with all Phase 1 tools."""
    from devin.tools.calculator import calculator_tool
    from devin.tools.search import web_search_tool
    from devin.tools.time_tool import current_time_tool
    from devin.tools.system import (
        read_file, write_file, list_directory, execute_command,
        grep_search, file_search, edit_file_replace, analyze_python_ast,
        search_code_bm25, read_function_only
    )

    registry = ToolRegistry()
    registry.register(calculator_tool, category="math")
    registry.register(current_time_tool, category="utility")
    registry.register(web_search_tool, category="search")
    
    # Phase 2/3/4: System Tools
    registry.register(read_file, category="system")
    registry.register(write_file, category="system")
    registry.register(list_directory, category="system")
    registry.register(execute_command, category="system")
    registry.register(grep_search, category="system")
    registry.register(file_search, category="system")
    registry.register(edit_file_replace, category="system")
    registry.register(analyze_python_ast, category="system")
    registry.register(search_code_bm25, category="system")
    registry.register(read_function_only, category="system")

    return registry
