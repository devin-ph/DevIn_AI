"""
Global constants and hardcoded configurations for DevIn.
"""

# Slash commands available in the CLI
SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/clear": "Clear the conversation history and start fresh",
    "/history": "Show conversation history summary",
    "/debug": "Toggle debug mode (shows full state transitions)",
    "/model": "Show or change the current LLM model",
    "/tools": "List all available tools",
    "/exit": "Exit DevIn",
    "/quit": "Exit DevIn",
}

# Technical keywords for simple intent detection
TECHNICAL_KEYWORDS = [
    "create", "write", "edit", "fix", "run", "build",
    "debug", "refactor", "test", "deploy", "analyze", "find"
]

# Simple casual intents that skip the full agent graph
SIMPLE_INTENTS = [
    "hi", "hello", "hey", "thanks", "bye", "who are you",
    "what can you do", "how are you", "good morning"
]

# Tools that mutate state
MUTATION_TOOLS = ["execute_command", "write_file", "edit_file_replace"]

# Rule mapping for lazy-loading skills
SKILL_LOAD_RULES = {
    "WHO_YOU_ARE.md":        ["*"],
    "ESCALATION_POLICY.md":  ["*"],
    "CODE_STYLE.md":         ["write", "create", "edit", "code", "fix", "class", "def"],
    "TASK_DECOMPOSITION.md": ["create", "build", "implement", "refactor", "fix"],
    "MEMORY_PROTOCOL.md":    [],
}

# General token limits or budgets (if applied later)
TOKEN_BUDGET = 200000
