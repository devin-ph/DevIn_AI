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

    def mark_pattern_resolved(self, pattern: str, skill_name: str):
        """Mark a bug pattern as resolved so learning loop doesn't re-trigger."""
        bugs_path = self.memory_dir / "bugs.md"
        if not bugs_path.exists():
            return
        content = bugs_path.read_text(encoding="utf-8")
        resolved = f"\n[RESOLVED-{datetime.now().strftime('%Y-%m')}] {pattern} → skill: {skill_name}\n"
        bugs_path.write_text(content + resolved, encoding="utf-8")

    def count_unresolved_pattern(self, pattern: str) -> int:
        """Count occurrences of pattern, excluding resolved ones."""
        bugs_path = self.memory_dir / "bugs.md"
        if not bugs_path.exists():
            return 0
        content = bugs_path.read_text(encoding="utf-8")
        # If pattern is marked resolved, return 0
        if f"[RESOLVED" in content and pattern in content.split("[RESOLVED")[1]:
            return 0
        return content.count(pattern)

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

    def propose_save(self, messages: list) -> dict:
        tasks_done = []
        files_created = []
        files_modified = []
        
        from langchain_core.messages import HumanMessage, ToolMessage
        
        # Pair HumanMessage requests with their ToolMessage outcomes
        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                request = str(msg.content)[:80]
                # Find the outcome in subsequent messages
                for j in range(i+1, min(i+10, len(messages))):
                    m = messages[j]
                    if isinstance(m, ToolMessage):
                        name = getattr(m, 'name', '')
                        content = str(m.content)
                        if name == 'write_file' and 'Success' in content:
                            import re
                            match = re.search(r'to (.+?\.\w+)', content)
                            if match:
                                fname = match.group(1)
                                tasks_done.append(f"{request} → created {fname}")
                                files_created.append(fname)
                        elif name == 'edit_file_replace' and 'Success' in content:
                            fpath = ""
                            for tool_call_msg in messages[i:j]:
                                if hasattr(tool_call_msg, 'tool_calls'):
                                    for tc in getattr(tool_call_msg, 'tool_calls', []):
                                        if tc.get('name') == 'edit_file_replace':
                                            fpath = tc.get('args', {}).get('filepath', '')
                            if fpath:
                                tasks_done.append(f"{request} → edited {fpath}")
                                files_modified.append(fpath)
        
        result = {}
        if tasks_done:
            result['state'] = '; '.join(tasks_done[-3:])  # Last 3 tasks
        if files_created:
            result['files_created'] = ', '.join(set(files_created))
        if files_modified:
            result['files_modified'] = ', '.join(set(files_modified))
        
        return result

    def format_proposal(self, summary: dict) -> str:
        lines = ["\n🧠 Session Summary — Save to Memory?"]
        
        has_content = False
        if summary.get('state'):
            has_content = True
            lines.append(f"  PROJECT_STATE: {summary['state']}")
        if summary.get('prefs'):
            has_content = True
            lines.append(f"  PREFERENCES: {summary['prefs']}")
        if summary.get('decisions'):
            has_content = True
            lines.append(f"  DECISIONS: {summary['decisions']}")
        if summary.get('bugs'):
            has_content = True
            lines.append(f"  BUGS: {summary['bugs']}")
            
        if not has_content:
            lines.append("  Nothing significant to save from this session.")
            lines.append("  Skip? [Y/n]:")
        else:
            lines.append("  Save all / edit / skip?")
            
        return "\n".join(lines)

    def save(self, data: dict):
        """Write to appropriate files"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if "state" in data and data["state"] != "Skip":
            (self.memory_dir / "project_state.md").write_text(data["state"], encoding="utf-8")
            
        if "prefs" in data and data["prefs"] != "Skip" and data["prefs"] != "No new preferences detected":
            (self.memory_dir / "preferences.md").write_text(data["prefs"], encoding="utf-8")
            
        if "decisions" in data and data["decisions"] != "Skip" and data["decisions"] != "None":
            with open(self.memory_dir / "decisions.md", "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}] {data['decisions']}\n")
                
        if "bugs" in data and data["bugs"] != "Skip" and data["bugs"] != "None":
            with open(self.memory_dir / "bugs.md", "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}] {data['bugs']}\n")

    def detect_stale(self) -> list:
        """Find outdated entries"""
        # Placeholder for stale detection logic
        return []