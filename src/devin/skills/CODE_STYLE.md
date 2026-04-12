# CODE_STYLE — Python Conventions Skill

## When to Use This Skill
Load whenever writing, reviewing, or refactoring Python code. These rules define what "correct" looks like for this user — follow them without being asked. When a convention is marked **[RECOMMENDED]**, it means the user hasn't established a preference yet and this is the suggested default to use consistently until overridden.

---

## 1. General Philosophy

- **Readable > clever.** If code needs a comment to explain what it does, rewrite it first. Comments should explain *why*, not *what*.
- **Explicit > implicit.** No magic, no hidden behavior, no surprising side effects.
- **Flat > nested.** Avoid deeply nested conditions. Use early returns (guard clauses) to reduce indentation.
- **Consistent > perfect.** Follow the conventions below even if you personally prefer something else.

---

## 2. Formatting

| Rule | Standard |
|------|----------|
| Indentation | 4 spaces (never tabs) |
| Max line length | 88 characters |
| Blank lines between functions | 2 |
| Blank lines between methods inside class | 1 |
| Trailing whitespace | Never |
| String quotes | Double quotes `"` preferred, consistent within a file |

**[RECOMMENDED]** Use `black` as auto-formatter. It enforces 88-char lines and double quotes automatically. Add to project:
```bash
pip install black
black .
```

---

## 3. Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Variables | `snake_case` | `user_input`, `file_path` |
| Functions | `snake_case` | `get_user_data()`, `parse_response()` |
| Classes | `PascalCase` | `DataProcessor`, `ApiClient` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `BASE_URL` |
| Private methods/vars | `_leading_underscore` | `_validate_input()` |
| Files/modules | `snake_case` | `data_pipeline.py`, `api_client.py` |
| Booleans | Start with `is_`, `has_`, `can_` | `is_valid`, `has_data`, `can_retry` |

**Hard rule:** Names must be descriptive. No single-letter variables outside of loop indices (`i`, `j`) or math operations. `data`, `result`, `temp`, `obj` are banned — name what the thing actually is.

---

## 4. Type Hints

**[RECOMMENDED]** Use type hints on all function signatures. You said you're not familiar yet — here's the rule to make it easy:

```python
# Always annotate: parameters + return type
def fetch_user(user_id: int) -> dict:
    ...

# For None returns
def save_to_file(data: str, path: str) -> None:
    ...

# For optional values
from typing import Optional
def find_item(item_id: int) -> Optional[dict]:
    ...

# For lists/dicts
from typing import list, dict  # Python 3.9+: use built-in list[str], dict[str, int]
def get_names() -> list[str]:
    ...
```

**Why:** Type hints make AI assistance much more accurate. They also serve as inline documentation. Start adding them — it takes 10 seconds per function and pays off immediately.

---

## 5. Docstrings

**[RECOMMENDED]** Use **Google style** docstrings. Simple, readable, works well with most tooling.

```python
def process_data(raw_data: list[dict], max_items: int = 100) -> list[dict]:
    """Process and filter raw data records.

    Args:
        raw_data: List of unprocessed data dictionaries.
        max_items: Maximum number of items to return.

    Returns:
        Filtered and processed list of data records.

    Raises:
        ValueError: If raw_data is empty.
    """
```

**Rules:**
- Every public function/method gets a docstring
- Private functions (`_name`) only need docstrings if the logic is non-obvious
- One-liners are fine for trivial functions: `"""Return the current timestamp."""`
- Never document the obvious: `"""This function gets a user."""` adds zero value

---

## 6. Error Handling

**[RECOMMENDED]** Adopt this pattern — specific exceptions, always log before raising or handling:

```python
import logging

logger = logging.getLogger(__name__)

# ✅ CORRECT — specific, logged, meaningful message
def load_config(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found: {path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config {path}: {e}")
        raise ValueError(f"Config file is malformed: {path}") from e

# ❌ WRONG — swallows the error silently
try:
    load_config(path)
except Exception:
    pass

# ❌ WRONG — too broad, hides real issues
except Exception as e:
    print(f"Something went wrong: {e}")
```

**Rules:**
- Never use bare `except:` — always specify the exception type
- Never swallow exceptions silently (empty `except` block)
- Catch the most specific exception possible
- Always log errors with enough context to debug later
- Re-raise or convert to a meaningful custom error

---

## 7. Logging

**[RECOMMENDED]** Use Python's stdlib `logging` — not `print()` in production code.

```python
# At the top of every module
import logging
logger = logging.getLogger(__name__)

# Usage
logger.debug("Processing item: %s", item_id)       # Dev detail
logger.info("Pipeline completed: %d records", n)   # Normal flow
logger.warning("Retry attempt %d of %d", n, max)   # Something off
logger.error("Failed to connect: %s", str(e))      # Recoverable error
logger.critical("Data corruption detected")         # Needs immediate attention
```

**Basic setup in your entry point (`main.py`):**
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
```

**Rules:**
- `print()` is only acceptable for CLI output explicitly meant for the user
- Never `print()` for debugging — use `logger.debug()` and filter by level
- Use `%s` style formatting in log calls, not f-strings (performance reason)

---

## 8. File & Folder Structure

Established pattern — **layer-based structure:**

```
project_root/
├── main.py               # Entry point only — minimal logic here
├── requirements.txt
├── .env                  # Secrets — never commit this
├── .env.example          # Template for .env — always commit this
├── README.md
│
├── models/               # Data structures, Pydantic models, dataclasses
│   └── user.py
│
├── services/             # Business logic — the "what the app does"
│   └── data_service.py
│
├── utils/                # Reusable helpers — no business logic here
│   └── file_utils.py
│
├── config/               # Configuration loading
│   └── settings.py
│
└── tests/                # Test files mirror the source structure
    ├── test_services.py
    └── test_utils.py
```

**Rules:**
- `main.py` is an entry point, not a dumping ground — max ~30 lines
- `utils/` has zero business logic — only pure helper functions
- `services/` never imports from each other circularly
- Config/secrets loaded once in `config/settings.py`, imported everywhere else
- Never hardcode secrets — always use `.env` + `python-dotenv`

---

## 9. Imports

```python
# Order (always group in this sequence, blank line between groups):
# 1. Standard library
import os
import json
from pathlib import Path

# 2. Third-party packages
import requests
from dotenv import load_dotenv

# 3. Local modules
from services.data_service import process
from utils.file_utils import read_json
```

**Rules:**
- No wildcard imports: `from module import *` is banned
- No unused imports — if it's not used, remove it
- Prefer `from x import y` over `import x` when only using one thing from a module
- Absolute imports only — no relative imports like `from ..utils import x`

---

## 10. Testing

**Current state:** Not yet writing tests — building familiarity first.

**[RECOMMENDED]** When you start, use `pytest` with this minimal pattern:

```python
# tests/test_data_service.py
import pytest
from services.data_service import process_data

def test_process_data_returns_list():
    result = process_data([{"id": 1, "name": "Alice"}])
    assert isinstance(result, list)

def test_process_data_empty_input_raises():
    with pytest.raises(ValueError):
        process_data([])
```

**AI behavior:** Do not auto-generate tests unless explicitly asked. When asked, write tests for the critical path only — not 100% coverage for its own sake.

---

## 11. Dependencies

- **Tool:** `pip` + `requirements.txt`
- **Rule:** Pin exact versions in production: `requests==2.31.0` not `requests>=2.0`
- **[RECOMMENDED]** Separate dev dependencies: `requirements-dev.txt` for tools like `black`, `pytest`
- **Rule:** Never add a new package without checking if stdlib can do the same job
- **Rule:** Every new dependency must be explicitly approved — do not silently add packages

---

## Quick Reference

```
Formatter    : black (88 chars, double quotes)
Naming       : snake_case vars/funcs, PascalCase classes, UPPER constants
Type hints   : Always on function signatures [RECOMMENDED]
Docstrings   : Google style on all public functions [RECOMMENDED]
Errors       : Specific exceptions, always log, never swallow
Logging      : stdlib logging, never print() in non-CLI code
Structure    : models/ services/ utils/ config/
Imports      : stdlib → third-party → local, no wildcards
Tests        : pytest when writing tests, not auto-generated
Dependencies : pip + requirements.txt, pinned versions
```
