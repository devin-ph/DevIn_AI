"""
Global constants and hardcoded configurations for DevIn.
"""

SLASH_COMMANDS = {
    "/think": "reason through any decision with personal context",
    "/help": "Show available commands",
    "/clear": "Clear the conversation history and start fresh",
    "/history": "Show conversation history summary",
    "/debug": "Toggle debug mode (shows full state transitions)",
    "/model": "Show or change the current LLM model",
    "/tools": "List all available tools",
    "/exit": "Exit DevIn",
    "/quit": "Exit DevIn",
}

TECHNICAL_KEYWORDS = [
    "create", "write", "edit", "fix", "run", "build",
    "debug", "refactor", "test", "deploy", "analyze", "find",
    "add", "delete", "remove", "update", "install", "make",
    "show me", "open", "read", "search", "check",
    ".py", ".js", ".ts", ".json", ".md", ".txt", ".csv",
    "you create", "you write", "you do", "you make", "you build",
    "you run", "you fix", "do it", "do this",
    "preference", "preferences", "sở thích",
    "nhớ", "remember", "memory",
    "biết gì về", "know about",
]

SIMPLE_INTENTS = [
    "hi", "hello", "hey", "thanks", "bye", "who are you",
    "what can you do", "how are you", "what time", "good morning", "good night",
]

LIFE_SHARING_PATTERNS = [
    "hôm nay có môn", "học môn", "thi", "deadline trường",
    "buổi sáng", "buổi chiều", "hôm nay mệt",
    "exam", "lecture", "class", "school", "campus", "deadline",
    "mệt", "stress", "vui", "chán", "hứng", "inspired",
    "tired", "burned out", "drained", "anxious", "excited",
    "tớ đang nghĩ", "tớ muốn", "tớ thấy", "tớ tò mò",
    "i'm thinking", "i want", "i feel", "i'm curious",
    "đang nghe", "đang xem", "đang chơi",
    "listening to", "watching", "playing",
]

MUTATION_TOOLS = ["execute_command", "write_file", "edit_file_replace"]

SKILL_LOAD_RULES = {
    "WHO_YOU_ARE.md":        ["*"],
    "ESCALATION_POLICY.md":  ["*"],
    "CODE_STYLE.md":         ["write", "create", "edit", "code", "fix", "class", "def"],
    "TASK_DECOMPOSITION.md": ["create", "build", "implement", "refactor", "fix"],
    "MEMORY_PROTOCOL.md":    [],
}

TOKEN_BUDGET = 200000
