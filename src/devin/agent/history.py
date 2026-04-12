"""
Logger for user interactions.
Records full conversations to JSONL files for memory parsing and analytical purposes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


class InteractionLogger:
    """Logs all conversations to a JSON file for analysis and memory training."""

    def __init__(self, log_dir: str = "./data/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.log_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.entries: list[dict] = []

    def log(self, role: str, content: str, metadata: dict | None = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "content": content,
            "metadata": metadata or {},
        }
        self.entries.append(entry)
        # Append to file
        with open(self.session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
