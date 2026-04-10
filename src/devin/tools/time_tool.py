"""
DevIn Time Tool — Gives the agent temporal awareness.

Knowing the current time and date is essential for:
- Answering time-sensitive questions
- Understanding relative dates ("yesterday", "last week")
- Scheduling and calendar awareness (Phase 5)
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class TimeInput(BaseModel):
    """Input schema for the time tool."""

    timezone_name: str = Field(
        default="UTC",
        description=(
            "Timezone name (e.g., 'UTC', 'US/Eastern', 'Asia/Tokyo', 'Europe/London'). "
            "Defaults to UTC."
        ),
    )


@tool("get_current_time", args_schema=TimeInput)
def current_time_tool(timezone_name: str = "UTC") -> str:
    """Get the current date and time. Use this when users ask about the current time,
    date, day of the week, or when you need temporal context for your reasoning."""
    try:
        import zoneinfo

        tz = zoneinfo.ZoneInfo(timezone_name)
    except (ImportError, KeyError):
        tz = timezone.utc
        timezone_name = "UTC (fallback — invalid timezone requested)"

    now = datetime.now(tz)

    return (
        f"**Current Time ({timezone_name}):**\n"
        f"- Date: {now.strftime('%A, %B %d, %Y')}\n"
        f"- Time: {now.strftime('%I:%M:%S %p')}\n"
        f"- ISO: {now.isoformat()}\n"
        f"- Unix timestamp: {int(now.timestamp())}"
    )
