"""
DevIn CLI — Entry point.
"""

import sys
import asyncio
import logging
from datetime import datetime, timedelta
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from devin.cli.renderer import (
    console,
    print_banner,
    print_error,
    print_response,
    print_tool_call,
    print_tool_result,
    print_token_summary,
    print_task_summary,
    ThoughtBuffer,
)
from devin.cli.commands import handle_slash_command
from devin.agent.history import InteractionLogger
from devin.agent.prompts import get_companion_prompt
from devin.constants import TECHNICAL_KEYWORDS, SIMPLE_INTENTS, LIFE_SHARING_PATTERNS

# Force UTF-8 rendering on Windows terminals to prevent rich crashes
if hasattr(sys.stdout, 'reconfigure'):
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.WARNING, format="%(name)s | %(message)s")
logger = logging.getLogger("devin")

OPINION_RULES_TEXT = """
OPINION RULES:
- When asked "what do you think?" or "is this good?", give a clear opinion with reasoning.
- Do not hide behind "it depends" without a recommendation.
- If something is weak, say why and suggest a better option.
- If something is strong, say what is strong specifically.
- Warn once when an approach is suboptimal, then respect the user's decision.
""".strip()

FAST_PATH_SYSTEM_PROMPT = (
    "You are DevIn, a brilliant best friend who happens to know tech. "
    "Talk naturally, casually, and directly in the same language style as the user. "
    "No robotic phrases like 'How can I help you today?' "
    f"\n\n{OPINION_RULES_TEXT}"
)

LIFE_MODE_SYSTEM_PROMPT = (
    "You are DevIn, a brilliant friend having a real conversation. "
    "Prioritize empathy, curiosity, and human connection before task-solving. "
    "Ask one gentle follow-up when useful, keep replies short and natural. "
    "Never force the message into a coding task. "
    f"\n\n{OPINION_RULES_TEXT}"
)

SURFACE_RESPONSES = {
    "met", "mệt", "on", "ổn", "binh thuong", "bình thường", "ok", "duoc", "được",
    "tot", "tốt", "khong sao", "không sao", "fine", "tired", "good",
}

EVENING_REVIEW_TRIGGERS = [
    "done for today", "done today", "xong roi", "xong rồi", "met", "mệt",
]

NIGHT_PLANNING_TRIGGERS = [
    "mai", "tomorrow", "sleep", "ngu", "ngủ", "ke hoach", "kế hoạch",
]

MORNING_RITUAL_TEXT = (
    "Morning mode: energizing, focused, brief. Keep output to 4-5 lines max and ask one open question."
)

EVENING_RITUAL_TEXT = (
    "Evening mode: reflective debrief. Ask one deeper follow-up when user is surface-level."
)

LATE_NIGHT_RITUAL_TEXT = (
    "Night mode: calm, strategic, concise. Help plan tomorrow and flag one suboptimal issue at most."
)


def _is_simple_intent(message: str) -> bool:
    msg = message.lower().strip()
    words = msg.split()
    if len(words) <= 4:
        return not any(kw in msg for kw in TECHNICAL_KEYWORDS)
    return any(p in msg for p in SIMPLE_INTENTS)


def _is_life_sharing(message: str) -> bool:
    msg = message.lower().strip()
    if not msg:
        return False
    return any(pattern in msg for pattern in LIFE_SHARING_PATTERNS)


def get_time_context() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "late_night"


def should_trigger_ritual(time_context: str, last_ritual: dict) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    ritual_key = "late_night" if time_context == "late_night" else time_context
    return last_ritual.get(ritual_key) != today


def _today_weekday_name() -> str:
    return datetime.now().strftime("%A")


def _tomorrow_weekday_name() -> str:
    return (datetime.now() + timedelta(days=1)).strftime("%A")


def _is_evening_review_trigger(message: str) -> bool:
    msg = message.lower()
    return any(trigger in msg for trigger in EVENING_REVIEW_TRIGGERS)


def _is_night_planning_trigger(message: str) -> bool:
    msg = message.lower()
    return any(trigger in msg for trigger in NIGHT_PLANNING_TRIGGERS)


def needs_deeper_followup(response: str) -> bool:
    words = response.lower().strip().split()
    if len(words) <= 3:
        return True

    joined = " ".join(words)
    if any(surface in joined for surface in SURFACE_RESPONSES) and len(words) < 6:
        return True
    return False


def _extract_tasks_from_text(text: str) -> list[str]:
    normalized = text.replace("\n", ",")
    raw_parts = [p.strip(" -\t") for p in normalized.split(",")]
    tasks = []
    for part in raw_parts:
        if len(part) < 4:
            continue
        lowered = part.lower()
        if lowered in {"mai", "tomorrow", "plan", "ke hoach", "kế hoạch"}:
            continue
        tasks.append(part)
    return tasks[:8]


def _has_heavy_school_day(tomorrow_day: str, weekly_schedule: dict) -> bool:
    text = (weekly_schedule.get(tomorrow_day, "") or "").lower()
    heavy_keywords = ["exam", "thi", "deadline", "kinh te", "toan", "project", "lab", "full day", "ca ngay"]
    return any(keyword in text for keyword in heavy_keywords)


def _get_early_commitments(tomorrow_day: str, weekly_schedule: dict) -> list[str]:
    text = (weekly_schedule.get(tomorrow_day, "") or "").lower()
    early_keywords = ["sang", "sáng", "7", "8", "8:00", "9:00", "morning", "early"]
    if any(keyword in text for keyword in early_keywords):
        return [weekly_schedule.get(tomorrow_day, "")]
    return []


def _is_pattern_relevant(pattern: str, tomorrow_tasks: list[str], tomorrow_day: str) -> bool:
    p = pattern.lower()
    if tomorrow_day.lower() in p:
        return True
    joined_tasks = " ".join(tomorrow_tasks).lower()
    task_tokens = [tok for tok in joined_tasks.split() if len(tok) > 3]
    return any(token in p for token in task_tokens[:8])


def analyze_tomorrow(
    tomorrow_tasks: list[str],
    weekly_schedule: dict,
    observed_patterns: list[str],
    current_hour: int,
) -> list[str]:
    issues = []
    tomorrow_day = _tomorrow_weekday_name()

    if len(tomorrow_tasks) > 5:
        issues.append(
            "5+ tasks kha nhieu. Thuc te thuong chi xong 2-3 viec trong ngay. Top 3 cua ban la gi?"
        )

    has_heavy_school = _has_heavy_school_day(tomorrow_day, weekly_schedule)
    has_heavy_dev = any("build" in t.lower() or "implement" in t.lower() for t in tomorrow_tasks)
    if has_heavy_school and has_heavy_dev:
        issues.append(
            "Ngay mai co lich hoc nang + task dev nang. Mot trong hai se bi sacrifice. Priority la gi?"
        )

    if current_hour >= 23:
        early_commitments = _get_early_commitments(tomorrow_day, weekly_schedule)
        if early_commitments:
            issues.append(
                f"Dang plan luc {current_hour}h ma mai co lich sang som. Nen nghi som de giu nang luong."
            )

    for pattern in observed_patterns:
        if _is_pattern_relevant(pattern, tomorrow_tasks, tomorrow_day):
            issues.append(f"To hay thay ban {pattern} - keep in mind.")
            break

    return issues


def _extract_mood(text: str) -> str:
    msg = text.lower()
    mood_map = {
        "drained": ["mệt", "met", "drained", "tired", "burned out"],
        "stressed": ["stress", "anxious", "overwhelmed"],
        "excited": ["vui", "hứng", "excited", "inspired"],
    }
    for mood, keywords in mood_map.items():
        if any(k in msg for k in keywords):
            return mood
    return "mixed"


def _build_evening_review(user_input: str, assistant_note: str) -> dict:
    done_text = "Shared debrief about the day"
    lowered = user_input.lower()
    if any(k in lowered for k in ["xong", "done", "build", "finished", "hoan thanh", "hoàn thành"]):
        done_text = user_input[:140]

    learned_text = "Not explicitly stated"
    if any(k in lowered for k in ["learn", "hoc", "học", "realized", "aha"]):
        learned_text = user_input[:140]

    time_text = "Not specified"
    if any(k in lowered for k in ["gio", "h", "hours", "hour", "buoi", "buổi"]):
        time_text = user_input[:140]

    patterns = []
    if "mệt" in lowered or "met" in lowered:
        patterns.append("Hay bi giam nang luong vao cuoi ngay")
    if "lãng phí" in lowered or "lang phi" in lowered:
        patterns.append("Co dau hieu mat focus vao buoi chieu")

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "done": done_text,
        "learned": learned_text,
        "mood": _extract_mood(user_input),
        "time_spent": time_text,
        "devin_note": " ".join(assistant_note.split())[:160],
        "patterns": patterns,
    }


def _serialize_daily_for_prompt(daily: dict) -> str:
    if not daily:
        return "No daily context yet."

    today = _today_weekday_name()
    tomorrow = _tomorrow_weekday_name()
    schedule = daily.get("schedule", {})
    tomorrow_plan = daily.get("tomorrow_plan", {})
    review = daily.get("today_review", {})

    lines = [
        f"Today ({today}) schedule: {schedule.get(today, 'Unknown')}",
        f"Tomorrow ({tomorrow}) schedule: {schedule.get(tomorrow, 'Unknown')}",
        f"Tomorrow plan date: {tomorrow_plan.get('date', 'Unknown')}",
        f"Tomorrow tasks: {', '.join(tomorrow_plan.get('tasks', [])[:4]) or 'None'}",
        f"Last review mood: {review.get('mood', 'Unknown')}",
    ]
    return "\n".join(lines)


def _fallback_greeting(project_state: str) -> str:
    if project_state:
        return "Yo, welcome back. Want to continue where we left off, or switch gears today?"
    return "Hey, good to see you. Feeling like a quick win or something bigger today?"


def generate_greeting(life_context: str, project_state: str, companion_llm=None) -> str:
    """Generate a short, casual contextual greeting from memory."""
    prompt = f"""
You are DevIn, a brilliant friend. Generate a SHORT, CASUAL greeting.

What you know about your friend:
{(life_context or "Not much yet - first session")[:1400]}

What you were working on together:
{(project_state or "Nothing yet")[:800]}

Rules:
- Max 2 sentences
- Sound like a friend, not an assistant
- Reference something real if you know it
- If nothing to reference, just say hey naturally
- Never say "How can I help you today?"

Generate only the greeting text.
"""

    try:
        llm = companion_llm
        if llm is None:
            from devin.agent.llm_provider import create_llm
            llm = create_llm(temperature=0.35)
        response = llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content="Generate the greeting now."),
        ])
        greeting = response.content if hasattr(response, "content") else str(response)
        greeting = " ".join(str(greeting).split()).strip()

        if not greeting:
            return _fallback_greeting(project_state)
        if "how can i help you today" in greeting.lower():
            return _fallback_greeting(project_state)
        return greeting
    except Exception as e:
        logger.debug(f"Greeting generation failed, using fallback: {e}")
        return _fallback_greeting(project_state)


def _recent_conversation_messages(conversation: list, limit: int = 8) -> list:
    return [
        msg
        for msg in conversation
        if isinstance(msg, (HumanMessage, AIMessage))
    ][-limit:]


def generate_ritual_greeting(
    time_ctx: str,
    daily: dict,
    life_context: str,
    project_state: str,
    companion_llm=None,
) -> str:
    daily_text = _serialize_daily_for_prompt(daily)
    stage = "opening"
    companion_prompt = get_companion_prompt(
        time_context=time_ctx,
        daily_context=daily_text,
        life_context=life_context,
        ritual_stage=stage,
    )

    mode_hint = {
        "morning": MORNING_RITUAL_TEXT,
        "evening": EVENING_RITUAL_TEXT,
        "late_night": LATE_NIGHT_RITUAL_TEXT,
    }.get(time_ctx, "Companion mode: natural and concise.")

    ritual_request = f"""
Generate a ritual opening for {time_ctx}.

{mode_hint}

Project carry-over:
{project_state or 'No active project carry-over.'}

Rules:
- Sound human and casual.
- Max 4-5 lines.
- Ask only one open-ended question.
- If schedule is heavy, acknowledge it.
- If schedule is light, suggest opportunity briefly.
- Never say: How can I help you today?
"""

    try:
        llm = companion_llm
        if llm is None:
            from devin.agent.llm_provider import create_llm
            llm = create_llm(temperature=0.35)
        response = llm.invoke([
            SystemMessage(content=companion_prompt),
            HumanMessage(content=ritual_request),
        ])
        text = response.content if hasattr(response, "content") else str(response)
        cleaned = "\n".join(line.strip() for line in str(text).splitlines() if line.strip()).strip()
        if cleaned:
            return cleaned
    except Exception as e:
        logger.debug(f"Ritual greeting generation failed: {e}")

    if time_ctx == "morning":
        return "Morning! Hom nay ban muon focus vao viec nao truoc?"
    if time_ctx == "evening":
        return "Hey, xong ngay roi? Ke toi nghe hom nay nhu nao di."
    if time_ctx == "late_night":
        return "Muon roi day - mai co gi khong? Plan nhanh truoc khi nghi nhe."
    return _fallback_greeting(project_state)


def generate_deeper_question(surface_response: str, context: str, companion_llm=None) -> str:
    """Generate one specific deeper follow-up question for evening review."""
    prompt = f"""
User gave a surface-level response:
"{surface_response}"

Context:
{context or 'No extra context.'}

Generate exactly ONE specific follow-up question that goes deeper.
Rules:
- Natural friend tone
- Under 20 words
- No list, no explanation
- Focus on emotion, bottleneck, or context
"""
    try:
        llm = companion_llm
        if llm is None:
            from devin.agent.llm_provider import create_llm
            llm = create_llm(temperature=0.4)
        response = llm.invoke([
            SystemMessage(content="You are DevIn, a close friend who asks sharp but caring follow-up questions."),
            HumanMessage(content=prompt),
        ])
        question = response.content if hasattr(response, "content") else str(response)
        question = " ".join(str(question).split())
        if question.endswith("?"):
            return question
        if question:
            return question + "?"
    except Exception as e:
        logger.debug(f"Deeper question generation failed: {e}")

    return "Met kieu overwhelm hay chi het nang luong tam thoi?"


async def run_cli_async():
    """Run the DevIn interactive CLI with async streaming."""
    from devin.agent.graph import build_graph, create_companion_chain
    from devin.tools.registry import create_default_registry

    print_banner()

    try:
        registry = create_default_registry()
    except Exception as e:
        print_error(f"Failed to load tools: {e}")
        return

    try:
        agent = build_graph(registry=registry)
    except Exception as e:
        print_error(f"Failed to create agent: {e}")
        console.print("  [dim]Make sure your API keys are set in .env[/]")
        return

    companion_llm = None
    try:
        companion_llm = create_companion_chain()
    except Exception as e:
        logger.debug(f"Companion chain unavailable, using fallback model creation: {e}")

    console.print()

    interaction_logger = InteractionLogger()
    conversation: list = []
    debug_mode = False
    memory_engine = None
    life_context = ""
    project_state = ""
    daily_context = {}

    try:
        from devin.agent.memory import MemoryEngine

        memory_engine = MemoryEngine()
        life_context = memory_engine.read_domain("life")
        project_state = memory_engine.read_domain("project_state")
        daily_context = memory_engine.load_daily()

        time_ctx = get_time_context()
        rituals_done = daily_context.get("rituals_done_today", {}) if daily_context else {}

        if time_ctx in {"morning", "evening", "late_night"} and should_trigger_ritual(time_ctx, rituals_done):
            ritual_greeting = generate_ritual_greeting(
                time_ctx=time_ctx,
                daily=daily_context,
                life_context=life_context,
                project_state=project_state,
                companion_llm=companion_llm,
            )
            if ritual_greeting:
                console.print(f"  [cyan]{ritual_greeting}[/]\n")
            memory_engine.mark_ritual_done(time_ctx)
        else:
            greeting = generate_greeting(life_context, project_state, companion_llm=companion_llm)
            if greeting:
                console.print(f"  [cyan]{greeting}[/]\n")
    except Exception as e:
        logger.debug(f"Unable to render contextual greeting: {e}")

    while True:
        try:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: console.input("[bold white]You ▶ [/]").strip()
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n  [devin.system]👋 Goodbye![/]\n")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                conversation, debug_mode, should_continue = handle_slash_command(
                    user_input, conversation, debug_mode, agent, registry
                )
                if not should_continue:
                    break
                continue

            interaction_logger.log("user", user_input)
            user_message = HumanMessage(content=user_input)
            conversation.append(user_message)
            full_messages = conversation

            console.print()

            current_time_ctx = get_time_context()
            life_mode_trigger = _is_life_sharing(user_input)
            evening_trigger = current_time_ctx == "evening" and (
                life_mode_trigger or _is_evening_review_trigger(user_input)
            )
            night_trigger = current_time_ctx == "late_night" and (
                life_mode_trigger or _is_night_planning_trigger(user_input)
            )

            if evening_trigger or night_trigger or life_mode_trigger:
                try:
                    if memory_engine is not None:
                        daily_context = memory_engine.load_daily()
                        life_context = memory_engine.read_domain("life")

                        if current_time_ctx in {"morning", "evening", "late_night"}:
                            rituals_done = daily_context.get("rituals_done_today", {}) if daily_context else {}
                            if should_trigger_ritual(current_time_ctx, rituals_done):
                                memory_engine.mark_ritual_done(current_time_ctx)

                    stage = "opening"
                    if current_time_ctx == "evening" and needs_deeper_followup(user_input):
                        stage = "deepening"
                    elif current_time_ctx == "late_night":
                        stage = "closing"

                    daily_text = _serialize_daily_for_prompt(daily_context)

                    if current_time_ctx == "evening" and needs_deeper_followup(user_input):
                        response_text = generate_deeper_question(
                            user_input,
                            daily_text,
                            companion_llm=companion_llm,
                        )
                    else:
                        quick_llm = companion_llm
                        if quick_llm is None:
                            from devin.agent.llm_provider import create_llm
                            quick_llm = create_llm()
                        companion_prompt = get_companion_prompt(
                            time_context=current_time_ctx,
                            daily_context=daily_text,
                            life_context=life_context,
                            ritual_stage=stage,
                        )

                        extra_system_messages = []
                        tomorrow_tasks = []
                        tomorrow_notes = ""
                        if current_time_ctx == "late_night" and _is_night_planning_trigger(user_input):
                            tomorrow_tasks = _extract_tasks_from_text(user_input)
                            weekly_schedule = daily_context.get("schedule", {}) if daily_context else {}
                            patterns = daily_context.get("patterns", []) if daily_context else []
                            issues = analyze_tomorrow(
                                tomorrow_tasks=tomorrow_tasks,
                                weekly_schedule=weekly_schedule,
                                observed_patterns=patterns,
                                current_hour=datetime.now().hour,
                            )
                            if issues:
                                tomorrow_notes = " | ".join(issues[:2])
                                extra_system_messages.append(SystemMessage(content=(
                                    "Planning observation: " + issues[0] + " "
                                    "Mention this once clearly with reason, then ask if they want to adjust."
                                )))

                            if memory_engine is not None and tomorrow_tasks:
                                memory_engine.save_tomorrow_plan(tomorrow_tasks, notes=tomorrow_notes)

                        companion_messages = [SystemMessage(content=companion_prompt)]
                        companion_messages.extend(extra_system_messages)
                        companion_messages.extend(_recent_conversation_messages(conversation))

                        life_response = quick_llm.invoke(companion_messages)
                        response_text = life_response.content if hasattr(life_response, "content") else str(life_response)

                    if memory_engine is not None and current_time_ctx == "evening":
                        review = _build_evening_review(user_input, response_text)
                        memory_engine.save_daily_review(review)

                    interaction_logger.log(
                        "assistant",
                        response_text,
                        {
                            "fast_path": "companion_mode",
                            "time_context": current_time_ctx,
                            "ritual_stage": stage,
                        },
                    )
                    conversation.append(AIMessage(content=response_text))
                    print_response(response_text)
                    continue
                except Exception as e:
                    logger.debug(f"Companion mode failed, falling back to graph: {e}")

            if _is_life_sharing(user_input):
                try:
                    quick_llm = companion_llm
                    if quick_llm is None:
                        from devin.agent.llm_provider import create_llm
                        quick_llm = create_llm()
                    life_messages = [SystemMessage(content=LIFE_MODE_SYSTEM_PROMPT)] + conversation[-6:]
                    life_response = quick_llm.invoke(life_messages)
                    response_text = life_response.content if hasattr(life_response, 'content') else str(life_response)

                    interaction_logger.log("assistant", response_text, {"fast_path": "life_mode"})
                    conversation.append(AIMessage(content=response_text))
                    print_response(response_text)
                    if hasattr(life_response, 'usage_metadata'):
                        print_token_summary(life_response.usage_metadata)
                    continue
                except Exception as e:
                    logger.debug(f"Life mode failed, falling back to graph: {e}")

            if _is_simple_intent(user_input):
                try:
                    from devin.agent.llm_provider import create_llm
                    quick_llm = create_llm()
                    quick_messages = [SystemMessage(content=FAST_PATH_SYSTEM_PROMPT)] + conversation[-6:]
                    quick_response = quick_llm.invoke(quick_messages)
                    response_text = quick_response.content if hasattr(quick_response, 'content') else str(quick_response)
                    interaction_logger.log("assistant", response_text, {"fast_path": True})
                    conversation.append(AIMessage(content=response_text))
                    print_response(response_text)
                    if hasattr(quick_response, 'usage_metadata'): print_token_summary(quick_response.usage_metadata)
                    continue
                except Exception as e:
                    logger.debug(f"Fast path failed, falling back to full graph: {e}")

            try:
                from devin.cli.stream import _process_stream
                
                executed_tasks = []
                agent_status = console.status("  [cyan]🧠 Thinking...[/]", spinner="dots")
                agent_status.start()

                try:
                    stream_res = await _process_stream(agent, agent_status, full_messages, executed_tasks)
                    
                    final_response = stream_res["final_response"]
                    final_response_str = stream_res["final_response_str"]
                    already_rendered = stream_res["already_rendered"]
                    iteration = stream_res["iteration"]
                    total_token_usage = stream_res["total_token_usage"]
                    
                    if stream_res.get("updated_conversation") is not None:
                        conversation = stream_res["updated_conversation"]

                except Exception as e:
                    agent_status.stop()
                    print_error(f"Execution failed: {e}")
                    logger.exception("Graph execution failed.")
                    if conversation and isinstance(conversation[-1], HumanMessage):
                        conversation.pop()
                    console.print("\n  [devin.system]⚠️ Graph execution crashed. State has been reset. Ready for next input.[/]\n")
                    continue
                finally:
                    agent_status.stop()

                print_task_summary(executed_tasks)

                if already_rendered and final_response_str:
                    interaction_logger.log("assistant", final_response_str, {"iterations": iteration})
                    print_response(final_response_str)
                elif not already_rendered and final_response:
                    interaction_logger.log("assistant", final_response, {"iterations": iteration})
                    print_response(final_response)
                elif not already_rendered and not final_response:
                    print_error("Agent did not produce a response.")
                    
                print_token_summary(total_token_usage)

            except KeyboardInterrupt:
                console.print("\n  [devin.system]⚡ Interrupted. Ready for next input.[/]\n")
                continue
        except KeyboardInterrupt:
            console.print("\n  [devin.system]👋 Goodbye![/]\n")
            break

def main():
    """Entry point for the devin command."""
    try:
        asyncio.run(run_cli_async())
    except KeyboardInterrupt:
        console.print("\n  [devin.system]👋 Goodbye![/]\n")

if __name__ == "__main__":
    main()