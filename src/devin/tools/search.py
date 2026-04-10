"""
DevIn Search Tool — Web search using DuckDuckGo (FREE, no API key needed).

DuckDuckGo is the default search provider — completely free with no rate limits.
Tavily is an optional upgrade if the user has a key configured.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SearchInput(BaseModel):
    """Input schema for the web search tool."""

    query: str = Field(description="The search query to look up on the web.")
    max_results: int = Field(
        default=5,
        description="Maximum number of results to return (1-10).",
        ge=1,
        le=10,
    )


@tool("web_search", args_schema=SearchInput)
def web_search_tool(query: str, max_results: int = 5) -> str:
    """Search the web for current information. Use this when you need to find
    up-to-date facts, news, documentation, or any information you don't already know.
    Returns a summary of the top search results with source URLs."""

    # Try Tavily first if configured (optional upgrade)
    try:
        from devin.settings import settings

        if settings.tavily_api_key and settings.tavily_api_key != "tvly-your-tavily-key-here":
            return _search_tavily(query, max_results)
    except Exception as e:
        logger.debug(f"Tavily not available ({e}), using DuckDuckGo")

    # Default: DuckDuckGo (free, no key needed)
    try:
        return _search_duckduckgo(query, max_results)
    except Exception as e:
        return f"Search failed. Error: {e}"


def _search_duckduckgo(query: str, max_results: int) -> str:
    """Primary search using DuckDuckGo (FREE, no API key needed)."""
    from ddgs import DDGS

    results = []
    with DDGS() as ddgs:
        for i, result in enumerate(ddgs.text(query, max_results=max_results), 1):
            title = result.get("title", "No title")
            url = result.get("href", "")
            body = result.get("body", "No content")
            if len(body) > 500:
                body = body[:500] + "..."
            results.append(f"**[{i}] {title}**\n{body}\nSource: {url}")

    return "\n\n".join(results) if results else "No results found."


def _search_tavily(query: str, max_results: int) -> str:
    """Optional search using Tavily API (paid, better quality)."""
    from tavily import TavilyClient

    from devin.settings import settings

    client = TavilyClient(api_key=settings.tavily_api_key)
    response = client.search(query=query, max_results=max_results, include_answer=True)

    results = []

    # Include the AI-generated answer if available
    if response.get("answer"):
        results.append(f"**Summary:** {response['answer']}\n")

    # Include individual results
    for i, result in enumerate(response.get("results", []), 1):
        title = result.get("title", "No title")
        url = result.get("url", "")
        content = result.get("content", "No content")
        if len(content) > 500:
            content = content[:500] + "..."
        results.append(f"**[{i}] {title}**\n{content}\nSource: {url}")

    return "\n\n".join(results) if results else "No results found."
