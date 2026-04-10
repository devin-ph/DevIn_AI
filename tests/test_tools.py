"""Tests for DevIn tools."""

from devin.tools.calculator import calculator_tool
from devin.tools.time_tool import current_time_tool
from devin.tools.registry import ToolRegistry


class TestCalculator:
    """Tests for the calculator tool."""

    def test_basic_addition(self):
        result = calculator_tool.invoke({"expression": "2 + 2"})
        assert "4" in result

    def test_multiplication(self):
        result = calculator_tool.invoke({"expression": "7 * 8"})
        assert "56" in result

    def test_complex_expression(self):
        result = calculator_tool.invoke({"expression": "3.14 * (5 ** 2)"})
        assert "78.5" in result

    def test_sqrt(self):
        result = calculator_tool.invoke({"expression": "sqrt(144)"})
        assert "12" in result

    def test_blocks_dangerous_input(self):
        result = calculator_tool.invoke({"expression": "__import__('os').system('ls')"})
        assert "Error" in result or "disallowed" in result

    def test_blocks_exec(self):
        result = calculator_tool.invoke({"expression": "exec('print(1)')"})
        assert "Error" in result or "disallowed" in result


class TestTimeTool:
    """Tests for the time tool."""

    def test_returns_utc_by_default(self):
        result = current_time_tool.invoke({"timezone_name": "UTC"})
        assert "UTC" in result
        assert "Date:" in result
        assert "Time:" in result

    def test_handles_invalid_timezone(self):
        result = current_time_tool.invoke({"timezone_name": "Invalid/Zone"})
        assert "fallback" in result or "UTC" in result


class TestToolRegistry:
    """Tests for the tool registry."""

    def test_register_and_retrieve(self):
        registry = ToolRegistry()
        registry.register(calculator_tool, category="math")
        assert registry.count == 1
        assert "calculator" in registry.get_tool_names()

    def test_duplicate_registration_fails(self):
        registry = ToolRegistry()
        registry.register(calculator_tool, category="math")
        try:
            registry.register(calculator_tool, category="math")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_category_filtering(self):
        registry = ToolRegistry()
        registry.register(calculator_tool, category="math")
        registry.register(current_time_tool, category="utility")

        math_tools = registry.get_tools(category="math")
        assert len(math_tools) == 1
        assert math_tools[0].name == "calculator"

        utility_tools = registry.get_tools(category="utility")
        assert len(utility_tools) == 1

    def test_get_all_tools(self):
        registry = ToolRegistry()
        registry.register(calculator_tool, category="math")
        registry.register(current_time_tool, category="utility")
        assert len(registry.get_tools()) == 2

    def test_get_descriptions(self):
        registry = ToolRegistry()
        registry.register(calculator_tool, category="math")
        desc = registry.get_tool_descriptions()
        assert "calculator" in desc
