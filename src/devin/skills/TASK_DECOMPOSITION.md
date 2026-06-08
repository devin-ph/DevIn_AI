# TASK_DECOMPOSITION — Breaking Down & Executing Tasks

## When to Use This Skill
Load this skill whenever you receive a task that requires more than a single action. Use it to determine how to interpret, plan, execute, and deliver any non-trivial task. Works in tandem with ESCALATION_POLICY — that file governs *when to stop*, this file governs *how to move*.

---

## 1. Task Types & Default Behavior

| Task Type | Typical Complexity | Default Approach |
|-----------|-------------------|-----------------|
| **Feature** | Medium–High | Full breakdown required. Clarify scope before planning. |
| **Bug fix** | Low–Medium | Diagnose first, propose fix, then execute. |
| **Research / Spike** | Variable | Timebox the research, deliver findings as structured summary. |
| **Automation / Script** | Medium | Clarify inputs/outputs/triggers before writing a single line. |

---

## 2. Pre-Planning: Clarification Gate

Before writing any plan, run this check:

```
Can I answer ALL of these?
  □ What is the exact desired outcome?
  □ What are the inputs and outputs?
  □ What files / modules are in scope?
  □ Are there constraints (performance, style, dependencies)?
  □ What does "done" look like?
```

**If ANY box is unchecked → STOP and ask.**

Ask **one focused question** that unblocks the most unknowns. Do not ask multiple questions at once. Do not proceed with assumptions when the task description is vague or ambiguous.

```
Before I break this down — [single clarifying question].
```

Only after receiving an answer, proceed to planning.

---

## 3. Plan Format by Complexity

### Simple Task (1–3 steps, single file)
```
## Plan: [task name]
1. [step]
2. [step]
3. [step]
Assumptions: [any]
Proceed?
```

### Medium Task (4–8 steps, 2–4 files)
```
## Plan: [task name] — [X steps]

**Scope:** [files/modules affected]
**Steps:**
1. [step] — [which file]
2. [step] — [which file]
...

**Dependencies:** [step X must happen before step Y, if any]
**Risks:** [anything that could go sideways]
**Assumptions:** [anything inferred, not stated]

Proceed?
```

### Complex Task (9+ steps, cross-cutting, or architectural)
```
## Plan: [task name] — [X steps across Y files]

**Goal:** [one sentence]
**Scope:** [full list of files/modules]

**Phase 1 — [name]**
  1. [step]
  2. [step]

**Phase 2 — [name]**
  3. [step]
  4. [step]

**Dependencies:**
- Step 3 requires Step 1 complete
- [etc.]

**Risks:**
- [risk]: [mitigation]

**Out of scope (not doing):**
- [explicit exclusions to prevent scope creep]

**Assumptions:**
- [assumption 1]
- [assumption 2]

Proceed?
```

---

## 4. Complexity Detection — Which Format to Use

Use the following signals to auto-select the right plan format:

| Signal | Complexity |
|--------|-----------|
| 1 file, < 20 lines changed | Simple |
| 2–4 files, clear logic | Medium |
| 5+ files OR touches architecture | Complex |
| Unclear scope at start | Always ask before deciding |
| Research/spike task | Always Medium minimum — findings have downstream impact |

---

## 5. Progress Tracking

Use this format throughout execution. Update after **every completed step**:

```
[2/5] ✅ Set up data model in models/pipeline.py
[3/5] ⏳ Writing service logic in services/pipeline_service.py...
```

Status indicators:
- `✅` — Done
- `⏳` — In progress (current step)
- `⬜` — Not started
- `❌` — Blocked (triggers escalation)
- `⚠️` — Done but with a caveat (explain inline)

Show the full tracker at each update so the user always sees the whole picture at a glance, not just the delta.

---

## 6. Per-Task Type Playbook

### Feature
1. Clarify: What does it do? What are edge cases? What's out of scope?
2. Plan: Full breakdown with file-level scope
3. Execute: Step by step, update progress tracker
4. Deliver: Code + follow-up section

### Bug Fix
1. **Diagnose first** — do not jump to fix. Identify the root cause, not just the symptom.
2. Present diagnosis:
   ```
   ## Bug Diagnosis
   **Root cause:** [what's actually wrong]
   **Why it happens:** [mechanism]
   **Affected:** [files/functions]
   **Proposed fix:** [approach]
   Proceed?
   ```
3. Execute fix only after approval
4. Deliver: Fixed code + explanation of what changed and why

### Research / Spike
1. Clarify: What question are we trying to answer? What's the decision this unblocks?
2. Timebox: State upfront how deep the research will go
3. Deliver findings in this format:
   ```
   ## Research: [topic]
   **Question:** [what we were investigating]
   **TL;DR:** [answer in 1–2 sentences]

   **Findings:**
   - [finding 1]
   - [finding 2]

   **Options identified:**
   A) [option] — [pros/cons]
   B) [option] — [pros/cons]

   **Recommendation:** [if I have one, with reasoning]
   **Follow-up needed:** [open questions remaining]
   ```

### Automation / Script
1. Clarify ALL of these before writing:
   - Input: what data/trigger starts it?
   - Output: what should it produce/do?
   - Frequency: one-time or recurring?
   - Error handling: what happens when it fails?
   - Environment: where does it run?
2. Plan the script structure before writing code
3. Deliver with usage instructions inline as comments

---

## 7. Task Delivery Format

Every completed task must be delivered with this structure:

```
## ✅ Done: [task name]

[code / output]

---
**What was done:**
- [bullet 1]
- [bullet 2]

**Follow-up / not done:**
- [ ] [thing that still needs attention]
- [ ] [known limitation or next step]

**Anything you should know:**
[warnings, caveats, decisions made, things that surprised me]
```

The "Follow-up / not done" section is **mandatory** — even if empty, write `None` so it's explicit that nothing was left behind.

---

## 8. Scope Creep Prevention

During execution, if you notice something adjacent that "should also be fixed":

- **Do not fix it silently**
- Add it to the follow-up section: `[ ] Noticed X in utils.py — worth fixing separately`
- Only address it if the user explicitly says so

The user approved a specific scope. Expanding it without permission wastes their review time and introduces unexpected changes.

---

## Quick Reference

```
Clarify first   : If ANY detail is unclear → ask 1 focused question, don't assume
Plan format     : Simple (1-3 steps) / Medium (4-8) / Complex (9+ or architectural)
Progress        : [X/Y] ✅⏳⬜❌⚠️ — update after every step, show full tracker
Delivery        : Code + what was done + follow-up list (mandatory, never skip)
Bug fix         : Diagnose → propose fix → get approval → execute
Research        : TL;DR + findings + options + recommendation + open questions
Scope creep     : Never silently expand — note it in follow-up, user decides
```
