"""
DevIn Calculator Tool — Safe mathematical expression evaluation.

Uses numexpr for safe evaluation (no arbitrary code execution).
Supports standard math operations, functions like sqrt/sin/cos, and constants.
"""

from __future__ import annotations

import logging
import math

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CalculatorInput(BaseModel):
    """Input schema for the calculator tool."""

    expression: str = Field(
        description=(
            "A mathematical expression to evaluate. "
            "Supports: +, -, *, /, **, sqrt(), sin(), cos(), tan(), log(), abs(), pi, e. "
            "Examples: '2 + 2', 'sqrt(144)', '3.14 * (5 ** 2)'"
        )
    )


# Safe list of allowed names for evaluation
_SAFE_MATH_NAMES: dict = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "abs": abs,
    "round": round,
    "pow": pow,
    "pi": math.pi,
    "e": math.e,
    "inf": math.inf,
    "ceil": math.ceil,
    "floor": math.floor,
}


@tool("calculator", args_schema=CalculatorInput)
def calculator_tool(expression: str) -> str:
    """Evaluate a mathematical expression safely. Use this for any calculations,
    unit conversions, or mathematical computations. Returns the computed result."""
    try:
        # First try numexpr for optimized evaluation
        return _eval_numexpr(expression)
    except Exception:
        # Fallback to safe eval
        return _eval_safe(expression)


def _eval_numexpr(expression: str) -> str:
    """Evaluate using numexpr (safe, no code execution)."""
    import numexpr

    result = numexpr.evaluate(expression)
    return f"{expression} = {result}"


def _eval_safe(expression: str) -> str:
    """Fallback: evaluate using Python eval with restricted namespace."""
    # Block dangerous builtins
    sanitized = expression.strip()

    # Quick safety check — reject anything with dunder or import
    if any(kw in sanitized for kw in ["__", "import", "exec", "eval", "open", "os.", "sys."]):
        return f"Error: Expression '{sanitized}' contains disallowed operations."

    try:
        result = eval(sanitized, {"__builtins__": {}}, _SAFE_MATH_NAMES)  # noqa: S307
        return f"{sanitized} = {result}"
    except Exception as e:
        return f"Error evaluating '{sanitized}': {e}"
