import os
import json
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class MemoryEngine:
    def __init__(self, memory_dir: str = "./data/memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.files = {
            "memory.md": "pointer index",
            "decisions.md": "append + date",
            "bugs.md": "append + date",
            "project_state.md": "overwrite",
            "preferences.md": "overwrite per key"
        }
        # Ensure files exist empty
        for f in self.files.keys():
            path = self.memory_dir / f
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def load(self) -> str:
        """Read all files, format as MEMORY block for system prompt"""
        blocks = []
        for f in self.files:
            path = self.memory_dir / f
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    blocks.append(f"--- {f} ---\n{content}\n")
        if not blocks:
            return "No previous memory stored."
        return "[[ MEMORY BLOCK ]]\n" + "\n".join(blocks)

    def propose_save(self, session_data: list) -> dict:
        """Format end-of-session summary based on conversation"""
        # In a full implementation, we would use an LLM here to summarize `session_data`.
        # For now, we return a structured proposal.
        return {
            "PROJECT_STATE": "Updated project components",
            "PREFERENCES": "No new preferences detected",
            "DECISIONS": "Made architectural choices",
            "BUGS": "No non-trivial bugs tracked"
        }

    def format_proposal(self, proposal: dict) -> str:
        return (
            "\n🧠 Session Summary — Save to Memory?\n"
            f"  PROJECT_STATE: {proposal.get('PROJECT_STATE')}\n"
            f"  PREFERENCES: {proposal.get('PREFERENCES')}\n"
            f"  DECISIONS: {proposal.get('DECISIONS')}\n"
            f"  BUGS: {proposal.get('BUGS')}\n"
            "  Save all / edit / skip?"
        )

    def save(self, data: dict):
        """Write to appropriate files"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if "PROJECT_STATE" in data and data["PROJECT_STATE"] != "Skip":
            (self.memory_dir / "project_state.md").write_text(data["PROJECT_STATE"], encoding="utf-8")
            
        if "PREFERENCES" in data and data["PREFERENCES"] != "Skip" and data["PREFERENCES"] != "No new preferences detected":
            (self.memory_dir / "preferences.md").write_text(data["PREFERENCES"], encoding="utf-8")
            
        if "DECISIONS" in data and data["DECISIONS"] != "Skip" and data["DECISIONS"] != "None":
            with open(self.memory_dir / "decisions.md", "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}] {data['DECISIONS']}\n")
                
        if "BUGS" in data and data["BUGS"] != "Skip" and data["BUGS"] != "None":
            with open(self.memory_dir / "bugs.md", "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}] {data['BUGS']}\n")

    def detect_stale(self) -> list:
        """Find outdated entries"""
        # Placeholder for stale detection logic
        return []