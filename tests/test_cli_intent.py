"""Regression tests for CLI fast-path routing decisions."""

import pytest

from devin.cli.loop import _is_simple_intent


@pytest.mark.parametrize(
    ("message", "expected_simple"),
    [
        ("create greet.py", False),
        ("create greet.py that prints Good morning", False),
        ("you do it for me", False),
        ("do it", False),
        ("hi", True),
        ("thanks", True),
    ],
)
def test_is_simple_intent_routing(message, expected_simple):
    assert _is_simple_intent(message) is expected_simple
