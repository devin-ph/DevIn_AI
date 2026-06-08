from pathlib import Path
from datetime import datetime, timedelta
import logging
import re

logger = logging.getLogger(__name__)


class MemoryEngine:
    DOMAINS = {
        "memory": {
            "filename": "memory.md",
            "description": "pointer index",
            "strategy": "index",
        },
        "decisions": {
            "filename": "decisions.md",
            "description": "technical decisions",
            "strategy": "append + date",
        },
        "bugs": {
            "filename": "bugs.md",
            "description": "known issues",
            "strategy": "append + date",
        },
        "project_state": {
            "filename": "project_state.md",
            "description": "what we were building",
            "strategy": "overwrite",
        },
        "preferences": {
            "filename": "preferences.md",
            "description": "coding preferences",
            "strategy": "overwrite per key",
        },
        "life": {
            "filename": "life.md",
            "description": "personal context",
            "strategy": "merge by section",
        },
        "patterns": {
            "filename": "patterns.md",
            "description": "behavioral patterns",
            "strategy": "append",
        },
        "daily": {
            "filename": "daily.md",
            "description": "daily rhythm state",
            "strategy": "overwrite by section",
        },
    }

    POINTER_INDEX_TEMPLATE = """# Memory Index

data/memory/
- memory.md         <- pointer index
- project_state.md  <- what we were building
- decisions.md      <- technical decisions
- bugs.md           <- known issues
- preferences.md    <- coding preferences
- life.md           <- personal context
- patterns.md       <- behavioral patterns
- daily.md          <- daily rhythm context
"""

    LIFE_TEMPLATE = """# Life Context

## About Me
- Name: Devin
- Major: Computer Science, Technology, AI Engineering

## Current Goals
- Build DevIn to production quality
- Get job-ready portfolio
- Learn by building, not just studying

## Active Goals
- build devin | set: 2026-04-10 | last mentioned: 2026-04-10 | status: active

## Schedule
- University schedule: [days/subjects as DevIn learns them]
- Known busy periods: [exams, deadlines]

## Current Mood Patterns
- [observations DevIn makes over time]

## Goals Being Tracked
- Short term: [what was mentioned this week]
- Long term: [career or life goals mentioned]

## Shared Interests
- Music: [genres, artists mentioned]
- Films/shows: [mentioned titles]
- Games: [if any]

## Things That Matter to Them
- Casual and direct conversation, not formal
- Vietnamese or English both fine
- Real opinions are appreciated
- Hates when people dance around bad news

## Last Known State
- [empty for now, DevIn will fill this]
"""

    PATTERNS_TEMPLATE = """# Behavioral Patterns

## Observed Patterns
[DevIn fills these over time]

## Energy Patterns
[when user is most productive based on conversation]

## Common Tendencies
[e.g., "plans big, often adjusts down same day"]
"""

    DAILY_TEMPLATE = """# Daily Context

## Schedule (weekly recurring)
Monday: [subjects/activities]
Tuesday: [subjects/activities]
Wednesday: [subjects/activities]
Thursday: [subjects/activities]
Friday: [subjects/activities]
Saturday: [free / part-time / etc]
Sunday: [free / study / etc]

## Tomorrow's Plan
Date: [auto-updated each night]
- [ ] [task 1]
- [ ] [task 2]
- [ ] [task 3]
Notes: [anything DevIn flagged as sub-optimal]

## Today's Review (most recent)
Date: [auto-updated]
Done: [what was accomplished]
Learned: [new insights or knowledge]
Mood: [energy level, emotional state]
Time spent: [where time went]
DevIn's note: [observation DevIn made]

## Patterns Observed (DevIn fills over time)
- [e.g., "Thuong met vao thu 4 sau mon X"]
- [e.g., "Productive nhat luc 9-11pm"]
- [e.g., "Hay bi distract khi co deadline gan"]

## Current Focus (rolling goal)
[What the user is working toward this week/month]

## Rituals Done Today
morning: (not yet)
evening: (not yet)
late_night: (not yet)
"""

    _PREF_PATTERNS = [
        (r"(?:thích|prefer)\s+(\w[\w\s/-]+?)\s+(?:hơn|over)\s+(\w[\w\s/-]+)", "prefer {0} over {1}"),
        (r"dùng\s+(\w[\w\s/-]+?)\s+thay vì\s+(\w[\w\s/-]+)", "use {0} instead of {1}"),
        (r"(?:không thích|tránh|never use|avoid)\s+(\w[\w\s/-]+)", "avoid {0}"),
        (r"(?:always use|luôn dùng)\s+(\w[\w\s/-]+)", "always use {0}"),
    ]

    def __init__(self, memory_dir: str = "./data/memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.files = {
            cfg["filename"]: cfg["description"]
            for cfg in self.DOMAINS.values()
        }
        self._ensure_domain_files()

    def _ensure_domain_files(self):
        for domain, cfg in self.DOMAINS.items():
            path = self.memory_dir / cfg["filename"]
            if not path.exists():
                if domain == "life":
                    path.write_text(self.LIFE_TEMPLATE, encoding="utf-8")
                elif domain == "daily":
                    path.write_text(self.DAILY_TEMPLATE, encoding="utf-8")
                elif domain == "patterns":
                    path.write_text(self.PATTERNS_TEMPLATE, encoding="utf-8")
                else:
                    path.write_text("", encoding="utf-8")

        (self.memory_dir / self.DOMAINS["memory"]["filename"]).write_text(
            self.POINTER_INDEX_TEMPLATE, encoding="utf-8",
        )

        for domain, template in [
            ("life", self.LIFE_TEMPLATE),
            ("daily", self.DAILY_TEMPLATE),
            ("patterns", self.PATTERNS_TEMPLATE),
        ]:
            p = self.memory_dir / self.DOMAINS[domain]["filename"]
            if not p.read_text(encoding="utf-8").strip():
                p.write_text(template, encoding="utf-8")

    def _domain_path(self, domain: str) -> Path:
        domain_cfg = self.DOMAINS.get(domain)
        if not domain_cfg:
            raise ValueError(f"Unknown memory domain: {domain}")
        return self.memory_dir / domain_cfg["filename"]

    def read_domain(self, domain: str) -> str:
        try:
            path = self._domain_path(domain)
        except ValueError:
            return ""
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()


    def load_coding_context(self) -> str:
        """Only coding-relevant memory: project_state, preferences, bugs."""
        coding_domains = ["project_state", "preferences", "bugs"]
        blocks = []
        for domain in coding_domains:
            cfg = self.DOMAINS[domain]
            path = self.memory_dir / cfg["filename"]
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8").strip()
            if not content or content.startswith("["):
                continue
            if domain == "bugs" and len(content) > 800:
                content = "...\n" + content[-800:]
            blocks.append(f"--- {cfg['filename']} ---\n{content}\n")
        if not blocks:
            return ""
        return "[[ MEMORY ]]\n" + "\n".join(blocks)

    def load_companion_context(self) -> str:
        """Personal/life memory for companion mode only."""
        companion_domains = ["life", "daily", "patterns"]
        blocks = []
        for domain in companion_domains:
            cfg = self.DOMAINS[domain]
            path = self.memory_dir / cfg["filename"]
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            blocks.append(f"--- {cfg['filename']} ---\n{content}\n")
        if not blocks:
            return ""
        return "[[ PERSONAL MEMORY ]]\n" + "\n".join(blocks)

    def load(self) -> str:
        """Backward-compat alias → load_coding_context."""
        return self.load_coding_context()


    @staticmethod
    def _extract_section(content: str, section_title: str) -> str:
        marker = f"## {section_title}"
        start = content.find(marker)
        if start == -1:
            return ""
        body_start = start + len(marker)
        if body_start < len(content) and content[body_start] == "\n":
            body_start += 1
        next_start = content.find("\n## ", body_start)
        if next_start == -1:
            next_start = len(content)
        return content[body_start:next_start].strip()

    @staticmethod
    def _replace_section(content: str, section_title: str, new_body: str) -> str:
        marker = f"## {section_title}"
        replacement = f"{marker}\n{new_body.strip()}\n"
        start = content.find(marker)
        if start == -1:
            return content.rstrip() + "\n\n" + replacement
        next_start = content.find("\n## ", start + len(marker))
        if next_start == -1:
            next_start = len(content)
        return content[:start] + replacement + content[next_start:]

    def _ensure_daily_content(self) -> str:
        daily_path = self._domain_path("daily")
        if not daily_path.exists() or not daily_path.read_text(encoding="utf-8").strip():
            daily_path.write_text(self.DAILY_TEMPLATE, encoding="utf-8")
        return daily_path.read_text(encoding="utf-8")

    @staticmethod
    def _field_from_section(section_text: str, field_name: str) -> str:
        prefix = f"{field_name}:"
        for line in section_text.splitlines():
            if line.strip().lower().startswith(prefix.lower()):
                return line.split(":", 1)[1].strip()
        return ""
    

    def _parse_daily_md(self, content: str) -> dict:
        schedule_section = self._extract_section(content, "Schedule (weekly recurring)")
        tomorrow_section = self._extract_section(content, "Tomorrow's Plan")
        review_section   = self._extract_section(content, "Today's Review (most recent)")
        patterns_section = self._extract_section(content, "Patterns Observed (DevIn fills over time)")
        focus_section    = self._extract_section(content, "Current Focus (rolling goal)")
        rituals_section  = self._extract_section(content, "Rituals Done Today")

        schedule = {}
        for line in schedule_section.splitlines():
            if ":" not in line:
                continue
            day, value = line.split(":", 1)
            if day.strip():
                schedule[day.strip()] = value.strip()

        tomorrow_tasks = [
            line.strip().replace("- [ ]", "", 1).strip()
            for line in tomorrow_section.splitlines()
            if line.strip().startswith("- [ ]")
        ]

        patterns = [
            line.strip().lstrip("-").strip()
            for line in patterns_section.splitlines()
            if line.strip().startswith("-") and line.strip().lstrip("-").strip()
        ]

        rituals_done = {}
        for line in rituals_section.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip():
                rituals_done[key.strip()] = value.strip()

        return {
            "schedule": schedule,
            "tomorrow_plan": {
                "date":  self._field_from_section(tomorrow_section, "Date"),
                "tasks": tomorrow_tasks,
                "notes": self._field_from_section(tomorrow_section, "Notes"),
            },
            "today_review": {
                "date":       self._field_from_section(review_section, "Date"),
                "done":       self._field_from_section(review_section, "Done"),
                "learned":    self._field_from_section(review_section, "Learned"),
                "mood":       self._field_from_section(review_section, "Mood"),
                "time_spent": self._field_from_section(review_section, "Time spent"),
                "devin_note": self._field_from_section(review_section, "DevIn's note"),
            },
            "patterns":          patterns,
            "current_focus":     " ".join(focus_section.split()),
            "rituals_done_today": rituals_done,
        }

    def load_daily(self) -> dict:
        daily_path = self._domain_path("daily")
        if not daily_path.exists():
            return {}
        content = daily_path.read_text(encoding="utf-8").strip()
        return self._parse_daily_md(content) if content else {}

    def save_daily_review(self, review: dict):
        content = self._ensure_daily_content()
        date_value = review.get("date") or datetime.now().strftime("%Y-%m-%d")
        review_body = "\n".join([
            f"Date: {date_value}",
            f"Done: {review.get('done', '[what was accomplished]')}",
            f"Learned: {review.get('learned', '[new insights or knowledge]')}",
            f"Mood: {review.get('mood', '[energy level, emotional state]')}",
            f"Time spent: {review.get('time_spent', '[where time went]')}",
            f"DevIn's note: {review.get('devin_note', '[observation DevIn made]')}",
        ])
        content = self._replace_section(content, "Today's Review (most recent)", review_body)
        patterns = review.get("patterns") or []
        if isinstance(patterns, str):
            patterns = [patterns]
        if patterns:
            content = self._append_bullets_to_section(
                content, "Patterns Observed (DevIn fills over time)", patterns,
            )
        current_focus = review.get("current_focus")
        if current_focus:
            content = self._replace_section(content, "Current Focus (rolling goal)", current_focus)
        self._domain_path("daily").write_text(content.strip() + "\n", encoding="utf-8")

    def save_tomorrow_plan(self, plan: list, notes: str = ""):
        content = self._ensure_daily_content()
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        clean_plan = [self._truncate(str(item), 140) for item in plan if str(item).strip()]
        if not clean_plan:
            clean_plan = ["[task 1]"]
        plan_lines = [f"Date: {tomorrow_date}"]
        for item in clean_plan[:8]:
            plan_lines.append(f"- [ ] {item}")
        notes_value = notes.strip() or "[anything DevIn flagged as sub-optimal]"
        plan_lines.append(f"Notes: {notes_value}")
        content = self._replace_section(content, "Tomorrow's Plan", "\n".join(plan_lines))
        self._domain_path("daily").write_text(content.strip() + "\n", encoding="utf-8")

    def mark_ritual_done(self, ritual: str):
        canonical = "late_night" if ritual in {"night", "late_night"} else ritual
        if canonical not in {"morning", "evening", "late_night"}:
            return
        content = self._ensure_daily_content()
        daily = self._parse_daily_md(content)
        rituals = daily.get("rituals_done_today", {})
        rituals[canonical] = datetime.now().strftime("%Y-%m-%d")
        ritual_lines = [
            f"morning: {rituals.get('morning', '(not yet)')}",
            f"evening: {rituals.get('evening', '(not yet)')}",
            f"late_night: {rituals.get('late_night', '(not yet)')}",
        ]
        content = self._replace_section(content, "Rituals Done Today", "\n".join(ritual_lines))
        self._domain_path("daily").write_text(content.strip() + "\n", encoding="utf-8")

    # ── Learning loop ─────────────────────────────────────────────────────────

    def mark_pattern_resolved(self, pattern: str, skill_name: str):
        bugs_path = self._domain_path("bugs")
        if not bugs_path.exists():
            return
        content = bugs_path.read_text(encoding="utf-8")
        resolved = f"\n[RESOLVED-{datetime.now().strftime('%Y-%m')}] {pattern} → skill: {skill_name}\n"
        bugs_path.write_text(content + resolved, encoding="utf-8")
        logger.info(f"Pattern '{pattern}' marked as resolved in bugs.md")

    def count_unresolved_pattern(self, pattern: str) -> int:
        bugs_path = self._domain_path("bugs")
        if not bugs_path.exists():
            return 0
        content = bugs_path.read_text(encoding="utf-8")
        resolved_lines = [ln for ln in content.splitlines() if "[RESOLVED" in ln]
        if any(pattern in ln for ln in resolved_lines):
            return 0
        return content.count(pattern)

    # ── Preference extraction ─────────────────────────────────────────────────

    def _extract_preferences(self, messages: list) -> list:
        """
        Scan HumanMessages for preference declarations.
        Returns normalized strings ready for preferences.md.
        """
        from langchain_core.messages import HumanMessage
        found: list = []
        for msg in messages:
            if not isinstance(msg, HumanMessage):
                continue
            raw = str(msg.content).strip()
            if not raw or raw.startswith("/") or len(raw.split()) > 20:
                continue
            raw_lower = raw.lower()
            for pattern, template in self._PREF_PATTERNS:
                m = re.search(pattern, raw_lower)
                if m:
                    try:
                        pref = template.format(*[g.strip() for g in m.groups()])
                    except IndexError:
                        pref = m.group(0).strip()
                    self._append_unique(found, pref)
                    break
        return found

    def _merge_preferences(self, new_prefs: list) -> str:
        """
        Merge new preferences into existing preferences.md.
        Same keyword → overwrite. New → append.
        """
        pref_path = self._domain_path("preferences")
        existing = pref_path.read_text(encoding="utf-8").strip() if pref_path.exists() else ""
        lines = [ln.strip() for ln in existing.splitlines() if ln.strip()]
        date_str = datetime.now().strftime("%Y-%m-%d")

        for pref in new_prefs:
            parts = pref.split()
            key = parts[0]
            subject = parts[1] if len(parts) > 1 else ""
            new_line = f"- {pref}  # {date_str}"
            replaced = False
            for i, line in enumerate(lines):
                if key in line.lower() and subject and subject in line.lower():
                    lines[i] = new_line
                    replaced = True
                    break
            if not replaced:
                lines.append(new_line)

        return "\n".join(lines) + "\n"

    # ── Session save ──────────────────────────────────────────────────────────

    def propose_save(self, messages: list) -> dict:
        """
        Extract saveable data from the session's message history.
        Populates: state, prefs, decisions, bugs, files_created, files_modified, life.
        """
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

        def _is_task_message(content: str) -> bool:
            content_lower = content.lower().strip()
            if not content_lower or content_lower.startswith("/"):
                return False
            task_verbs = [
                "create", "add", "edit", "fix", "write", "build",
                "implement", "refactor", "delete", "update", "install",
                "tạo", "sửa", "viết", "xóa", "thêm",
            ]
            words = content_lower.split()
            has_verb = any(re.search(rf"\b{re.escape(v)}\b", content_lower) for v in task_verbs)
            has_specific = len(words) >= 4 or any(
                ext in content_lower for ext in [".py", ".js", ".ts", ".json", ".md"]
            )
            return has_verb and has_specific

        def _extract_file_from_tool_content(content: str) -> str:
            match = re.search(r"\bto\s+([^\s]+?\.\w+)\b", content)
            return match.group(1) if match else ""

        def _record_task(task_map: dict, key: str, summary: str):
            existing = task_map.get(key)
            if existing is None or len(summary) > len(existing):
                task_map[key] = summary

        # ── File operations → state ──
        tasks_by_target: dict = {}
        files_created:   list = []
        files_modified:  list = []
        errors_seen:     list = []
        errors_fixed:    list = []

        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                content_str = str(msg.content).strip()
                if _is_task_message(content_str):
                    request = content_str[:80]
                    for j in range(i + 1, min(i + 12, len(messages))):
                        m = messages[j]
                        if not isinstance(m, ToolMessage):
                            continue
                        name    = getattr(m, "name", "")
                        content = str(m.content)
                        if name == "write_file" and "Success" in content:
                            fname = _extract_file_from_tool_content(content)
                            if fname:
                                _record_task(tasks_by_target, f"created:{fname.lower()}", f"{request} → created {fname}")
                                self._append_unique(files_created, fname)
                        elif name == "edit_file_replace" and "Success" in content:
                            for k in range(i, j):
                                if hasattr(messages[k], "tool_calls"):
                                    for tc in getattr(messages[k], "tool_calls", []):
                                        if tc.get("name") == "edit_file_replace":
                                            fpath = tc.get("args", {}).get("filepath", "")
                                            if fpath:
                                                _record_task(tasks_by_target, f"edited:{fpath.lower()}", f"{request} → edited {fpath}")
                                                self._append_unique(files_modified, fpath)

            if isinstance(msg, ToolMessage):
                content   = str(msg.content)
                tool_name = getattr(msg, "name", "")
                if any(marker in content for marker in ("FAIL", "Error:", "Traceback", "SyntaxError")):
                    snippet = self._truncate(content.splitlines()[0], 100)
                    self._append_unique(errors_seen, f"{tool_name}: {snippet}")
                elif ("PASS" in content or "Success" in content) and errors_seen:
                    self._append_unique(errors_fixed, errors_seen[-1])

        # ── Decisions from AI responses ──
        decision_keywords = [
            "quyết định", "chọn", "thay vì", "instead of", "decided to",
            "going with", "switched to", "trade-off", "because", "vì ",
        ]
        decisions_found: list = []
        for msg in messages:
            if not isinstance(msg, AIMessage) or msg.tool_calls:
                continue
            content = re.sub(r"<thought>.*?</thought>", "", str(msg.content), flags=re.DOTALL).strip()
            if not content or len(content) < 20:
                continue
            if any(kw in content.lower() for kw in decision_keywords):
                self._append_unique(decisions_found, self._truncate(content, 120))

        # ── Preferences ──
        prefs_found = self._extract_preferences(messages)

        # ── Build result ──
        result: dict = {}

        tasks_done = list(tasks_by_target.values())
        if tasks_done:
            result["state"] = "; ".join(tasks_done[-3:])
        if files_created:
            result["files_created"] = ", ".join(sorted(set(files_created)))
        if files_modified:
            result["files_modified"] = ", ".join(sorted(set(files_modified)))
        if decisions_found and tasks_done:
            result["decisions"] = " | ".join(decisions_found[-2:])

        unresolved = [e for e in errors_seen if e not in errors_fixed]
        if unresolved:
            result["bugs"] = " | ".join(unresolved[-2:])

        if prefs_found:
            result["prefs"]        = "; ".join(prefs_found)
            result["_prefs_list"]  = prefs_found

        life_updates = self.extract_life_context(messages)
        if self._has_life_updates(life_updates):
            result["life"]         = self._format_life_summary(life_updates)
            result["_life_struct"] = life_updates

        return result

    def format_proposal(self, summary: dict) -> str:
        lines = ["\n🧠 Session Summary — Save to Memory?"]
        has_content = False
        for key, label in [
            ("state",          "PROJECT_STATE"),
            ("prefs",          "PREFERENCES"),
            ("decisions",      "DECISIONS"),
            ("bugs",           "BUGS"),
            ("files_created",  "FILES CREATED"),
            ("files_modified", "FILES MODIFIED"),
            ("life",           "LIFE"),
        ]:
            if summary.get(key):
                has_content = True
                lines.append(f"  {label}: {summary[key]}")
        if not has_content:
            lines.append("  Nothing significant to save from this session.")
        lines.append("  Save all / edit / skip?")
        return "\n".join(lines)

    def save(self, data: dict):
        """Write extracted session data to appropriate memory files."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if data.get("state"):
            self._domain_path("project_state").write_text(data["state"], encoding="utf-8")

        if data.get("prefs"):
            prefs_list = data.get("_prefs_list")
            if isinstance(prefs_list, list) and prefs_list:
                merged = self._merge_preferences(prefs_list)
            else:
                existing = self._domain_path("preferences").read_text(encoding="utf-8").strip()
                merged = existing + f"\n- {data['prefs']}  # {timestamp[:10]}\n"
            self._domain_path("preferences").write_text(merged, encoding="utf-8")

        if data.get("decisions"):
            with open(self._domain_path("decisions"), "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}] {data['decisions']}\n")

        if data.get("bugs"):
            with open(self._domain_path("bugs"), "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}] {data['bugs']}\n")

        if data.get("life"):
            life_struct = data.get("_life_struct")
            if not isinstance(life_struct, dict):
                life_struct = self._parse_life_summary(str(data["life"]))
            self._save_life_context(life_struct)

    # ── Life context ──────────────────────────────────────────────────────────

    def extract_life_context(self, messages: list) -> dict:
        life_updates = {
            "schedule": [], "mood_notes": [], "goals_mentioned": [],
            "interests_mentioned": [], "last_state": "",
        }
        schedule_keywords = [
            "hôm nay có môn", "học môn", "thi", "deadline trường",
            "buổi sáng", "buổi chiều", "exam", "lecture", "class", "deadline",
        ]
        mood_keywords = [
            "mệt", "stress", "vui", "chán", "hứng", "inspired",
            "tired", "burned out", "drained", "excited", "anxious",
        ]
        goal_keywords = [
            "tớ muốn", "mình muốn", "dự định", "plan", "goal", "want to",
            "going to", "aim", "target", "muốn",
        ]
        interest_keywords = [
            "đang nghe", "đang xem", "đang chơi", "music", "song",
            "playlist", "artist", "film", "movie", "show", "game",
        ]
        from langchain_core.messages import HumanMessage
        for msg in messages:
            if not isinstance(msg, HumanMessage):
                continue
            content_raw = str(msg.content).strip()
            if not content_raw or content_raw.startswith("/"):
                continue
            content = content_raw.lower()
            snippet = self._truncate(content_raw, 120)
            if any(kw in content for kw in schedule_keywords):
                self._append_unique(life_updates["schedule"], snippet)
            if any(kw in content for kw in mood_keywords):
                self._append_unique(life_updates["mood_notes"], snippet)
            if any(kw in content for kw in goal_keywords):
                self._append_unique(life_updates["goals_mentioned"], snippet)
            if any(kw in content for kw in interest_keywords):
                self._append_unique(life_updates["interests_mentioned"], snippet)
            life_updates["last_state"] = self._truncate(content_raw, 150)
        for key in ("schedule", "mood_notes", "goals_mentioned", "interests_mentioned"):
            life_updates[key] = life_updates[key][:3]
        return life_updates

    @staticmethod
    def _has_life_updates(life_updates: dict) -> bool:
        return any(
            life_updates.get(key)
            for key in ("schedule", "mood_notes", "goals_mentioned", "interests_mentioned")
        ) or bool(life_updates.get("last_state"))

    @staticmethod
    def _format_life_summary(life_updates: dict) -> str:
        def _join(items):
            return " || ".join(items) if items else "none"
        return (
            f"schedule={_join(life_updates.get('schedule', []))}; "
            f"mood={_join(life_updates.get('mood_notes', []))}; "
            f"goals={_join(life_updates.get('goals_mentioned', []))}; "
            f"interests={_join(life_updates.get('interests_mentioned', []))}; "
            f"last_state={life_updates.get('last_state', '') or 'none'}"
        )

    @staticmethod
    def _parse_life_summary(summary_text: str) -> dict:
        parsed = {
            "schedule": [], "mood_notes": [], "goals_mentioned": [],
            "interests_mentioned": [], "last_state": "",
        }
        if not summary_text:
            return parsed
        key_map = {
            "schedule": "schedule", "mood": "mood_notes",
            "goals": "goals_mentioned", "interests": "interests_mentioned",
            "last_state": "last_state",
        }
        for part in [p.strip() for p in summary_text.split(";") if p.strip()]:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key    = key.strip().lower()
            value  = value.strip()
            mapped = key_map.get(key)
            if not mapped or value.lower() in ("", "none"):
                continue
            if mapped == "last_state":
                parsed[mapped] = value
            else:
                parsed[mapped] = [v.strip() for v in value.split("||") if v.strip()]
        return parsed

    def _save_life_context(self, life_updates: dict):
        if not self._has_life_updates(life_updates):
            return
        life_path = self._domain_path("life")
        if not life_path.exists() or not life_path.read_text(encoding="utf-8").strip():
            life_path.write_text(self.LIFE_TEMPLATE, encoding="utf-8")
        content = life_path.read_text(encoding="utf-8")
        content = self._append_bullets_to_section(content, "Schedule", life_updates.get("schedule", []))
        content = self._append_bullets_to_section(content, "Current Mood Patterns", life_updates.get("mood_notes", []))
        content = self._append_bullets_to_section(content, "Goals Being Tracked", life_updates.get("goals_mentioned", []))
        content = self._append_bullets_to_section(content, "Shared Interests", life_updates.get("interests_mentioned", []))
        content = self._set_last_known_state(content, life_updates.get("last_state", ""))
        life_path.write_text(content.strip() + "\n", encoding="utf-8")


    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= max_len:
            return normalized
        return normalized[: max_len - 3].rstrip() + "..."

    @staticmethod
    def _append_unique(target: list, value: str):
        if value and value not in target:
            target.append(value)

    @staticmethod
    def _append_bullets_to_section(content: str, section_title: str, bullets: list) -> str:
        if not bullets:
            return content
        section_marker = f"## {section_title}"
        start = content.find(section_marker)
        if start == -1:
            extra = f"\n\n{section_marker}\n" + "".join(f"- {item}\n" for item in bullets)
            return content.rstrip() + extra
        next_section = content.find("\n## ", start + len(section_marker))
        if next_section == -1:
            next_section = len(content)
        section_block = content[start:next_section]
        for item in bullets:
            line = f"- {item}"
            if line not in section_block:
                section_block = section_block.rstrip() + f"\n{line}\n"
        return content[:start] + section_block + content[next_section:]

    @staticmethod
    def _set_last_known_state(content: str, last_state: str) -> str:
        if not last_state:
            return content
        section_marker = "## Last Known State"
        replacement    = f"## Last Known State\n- {last_state}\n"
        start = content.find(section_marker)
        if start == -1:
            return content.rstrip() + "\n\n" + replacement
        next_section = content.find("\n## ", start + len(section_marker))
        if next_section == -1:
            next_section = len(content)
        return content[:start] + replacement + content[next_section:]


    def extract_patterns(self):
        log_dir = Path("data/logs")
        if not log_dir.exists():
            return
        logs = sorted(list(log_dir.glob("*.jsonl")))
        if not logs:
            return
        patterns_to_detect = {
            "Late night before class":               [["late", "night", "class"]],
            "Ambitious planning then scaling back":  [["too much", "didn't finish"]],
        }
        counts = {p: 0 for p in patterns_to_detect}
        for log_file in logs[-20:]:
            try:
                content = log_file.read_text(encoding="utf-8").lower()
                for pattern_name, triggers in patterns_to_detect.items():
                    for trig_list in triggers:
                        if all(t in content for t in trig_list):
                            counts[pattern_name] += 1
                            break
            except Exception:
                continue
        try:
            pattern_file = self._domain_path("patterns")
            current = pattern_file.read_text(encoding="utf-8")
            for p, count in counts.items():
                if count >= 2 and p not in current:
                    current += f"- {p} (Detected on {datetime.now().strftime('%Y-%m-%d')})\n"
            pattern_file.write_text(current, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to update patterns: {e}")

    def detect_stale(self) -> list:
        return []