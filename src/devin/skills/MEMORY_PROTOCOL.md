# MEMORY_PROTOCOL — Persistent Memory Between Sessions

## When to Use This Skill
Load at the **start of every session** to understand what's already known, and at the **end of every session** to capture what should persist. This skill defines what gets remembered, how it's stored, who decides, and when it expires.

---

## 1. Core Principle

> **Memory exists to eliminate repeated context. It is not a log — it is a living snapshot.**
> Only information that would meaningfully change how the agent behaves in a future session is worth storing.

---

## 2. Memory Sections

Memory in the system prompt is always structured in **4 sections**. Never mix them.

```
## [MEMORY]

### PROJECT_STATE
[What's currently in progress, what's done, what's next]

### PREFERENCES
[Confirmed user preferences discovered or updated during sessions]

### DECISIONS
[Architectural and technical decisions made, with brief rationale]

### BUG_HISTORY
[Bugs encountered, root causes, fixes applied]

## [/MEMORY]
```

Each section follows its own update strategy (see Section 4).

---

## 3. What Gets Remembered — By Category

### PROJECT_STATE
Information that describes **where things stand right now.**

✅ Save:
- Current active task / feature being worked on
- What was completed in the last session
- Known blockers or open questions
- Next planned steps

❌ Don't save:
- Completed tasks older than the current sprint/focus
- Details that live in the code itself

Update strategy: **Overwrite** — only the current state matters, history lives in the code.

---

### PREFERENCES
User preferences that were **explicitly confirmed or corrected** during a session.

✅ Save:
- Preferences that differ from the defaults in WHO_YOU_ARE.md
- Corrections the user made to AI behavior mid-session ("stop doing X", "I prefer Y")
- Tool/library choices confirmed for this user ("use httpx not requests")

❌ Don't save:
- Preferences already documented in WHO_YOU_ARE.md or CODE_STYLE.md
- One-off exceptions ("just this once, do it differently")

Update strategy: **Overwrite** — latest confirmed preference replaces old one.

---

### DECISIONS
Technical and architectural decisions made **with reasoning**, so they don't get re-debated.

✅ Save:
- "Chose X over Y because Z"
- "Decided not to use X because of Y constraint"
- Any decision that took deliberation to reach

❌ Don't save:
- Trivial choices (variable names, minor formatting)
- Decisions that are obvious from the code

Update strategy: **Append with date** — decisions accumulate as a log.

```
[2024-01] Used SQLite over PostgreSQL — solo project, no concurrent writes needed
[2024-02] Switched from requests to httpx — needed async support for pipeline
```

---

### BUG_HISTORY
Bugs that were **non-trivial to diagnose**, stored to prevent re-investigation.

✅ Save:
- Root cause (not just symptom)
- What the fix was
- Any gotcha or non-obvious behavior discovered

❌ Don't save:
- Typos, syntax errors, obvious mistakes
- Bugs fixed in under 2 minutes

Update strategy: **Append with date** — bugs accumulate as a log.

```
[2024-01] Telegram webhook silently failing — cause: missing SSL cert on local dev. Fix: use ngrok tunnel.
[2024-02] CSV parser skipping last row — cause: missing newline at EOF. Fix: added newline in write step.
```

---

## 4. Update Rules Summary

| Section | Strategy | Who decides |
|---------|----------|-------------|
| PROJECT_STATE | Overwrite | Agent proposes at end of session, user confirms |
| PREFERENCES | Overwrite (per key) | Agent proposes, user confirms |
| DECISIONS | Append + date | Agent proposes, user confirms |
| BUG_HISTORY | Append + date | Agent proposes, user confirms |

---

## 5. End-of-Session Protocol

At the **end of every session** (when work is done or user signals wrapping up), the agent must run this routine:

```
## 🧠 Session Summary — Save to Memory?

**PROJECT_STATE update:**
→ [proposed new state — what's done, what's next, any blockers]

**PREFERENCES to save:** (if any new ones confirmed this session)
→ [preference: value]

**DECISIONS to log:** (if any made this session)
→ [date] [decision + rationale]

**BUGS to log:** (if any non-trivial bugs encountered)
→ [date] [bug + root cause + fix]

**Stale entries to consider removing:**
→ [anything that looks outdated based on this session]

Save all / edit / skip?
```

If the user says "save all" → update all proposed sections.
If the user edits → apply their version, not the proposed one.
If the user says "skip" → nothing is saved, no memory changes.

**Never update memory silently without running this protocol.**

---

## 6. Start-of-Session Protocol

At the **start of every session**, if memory exists, briefly surface it:

```
## 📋 Context from last session

**Where we left off:** [PROJECT_STATE in 1–2 sentences]
**Active preferences:** [any non-default preferences in effect]
**Relevant decisions:** [only ones relevant to today's likely work]

Continue from here?
```

If memory is empty or not loaded → ask:
```
No memory loaded. Want to start fresh, or should I ask a few questions to build context?
```

---

## 7. Staleness Detection

During any session, if the agent notices a memory entry that appears outdated:

**Trigger conditions:**
- PROJECT_STATE references a task that's clearly been completed
- A PREFERENCE conflicts with something the user just did or said
- A DECISION is being revisited / reversed
- A BUG_HISTORY entry is about code that no longer exists

**Action:** Flag it at the end of the session in the "Stale entries" section of the summary. Never silently delete — always propose to the user first.

```
**Stale entries to consider removing:**
→ DECISIONS [2024-01]: SQLite choice — you've since migrated to PostgreSQL, this may be outdated
→ PROJECT_STATE: References "build auth module" — this appears complete based on today's work
```

---

## 8. Memory Size Discipline

System prompts have token limits. Keep memory lean:

| Section | Max entries | Max per entry |
|---------|------------|---------------|
| PROJECT_STATE | 1 (current only) | ~100 words |
| PREFERENCES | 10 active | 1 line each |
| DECISIONS | Last 10 | 1–2 lines each |
| BUG_HISTORY | Last 10 | 2–3 lines each |

When a section exceeds the limit, propose archiving the oldest entries before adding new ones. Don't silently drop old entries.

---

## 9. Memory Template (Ready to Paste into System Prompt)

```
## [MEMORY]

### PROJECT_STATE
[Empty — populate after first session]

### PREFERENCES
[Empty — populate as preferences are confirmed]

### DECISIONS
[Empty — populate as decisions are made]

### BUG_HISTORY
[Empty — populate as non-trivial bugs are resolved]

## [/MEMORY]
```

---

## Quick Reference

```
Sections        : PROJECT_STATE / PREFERENCES / DECISIONS / BUG_HISTORY
State + prefs   : Overwrite (only current matters)
Decisions + bugs: Append with date (history matters)
Who saves       : End-of-session summary → user confirms → agent writes
Who deletes     : Agent flags stale → user confirms → agent removes
Session start   : Surface relevant memory in 3–4 lines
Session end     : Always run save protocol, never update silently
Size limit      : 10 entries max per section, ~100 words per entry
```
