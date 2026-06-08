"""Tests for memory engine life-context behavior and task extraction safeguards."""

from langchain_core.messages import HumanMessage, ToolMessage

from devin.agent.memory import MemoryEngine


def test_memory_engine_creates_life_domain(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))

    assert (tmp_path / "life.md").exists()
    assert (tmp_path / "daily.md").exists()

    index_content = (tmp_path / "memory.md").read_text(encoding="utf-8")
    assert "life.md" in index_content
    assert "daily.md" in index_content


def test_extract_life_context_detects_personal_signals(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))
    messages = [
        HumanMessage(content="hôm nay có môn Kinh tế, mệt quá"),
        HumanMessage(content="tớ muốn build portfolio mạnh hơn tháng này"),
        HumanMessage(content="đang nghe nhạc lofi để đỡ stress"),
    ]

    life = memory.extract_life_context(messages)

    assert life["schedule"]
    assert life["mood_notes"]
    assert life["goals_mentioned"]
    assert life["interests_mentioned"]
    assert life["last_state"]


def test_propose_and_save_life_context(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))
    messages = [
        HumanMessage(content="hôm nay có môn AI lúc sáng"),
        HumanMessage(content="tớ muốn tập trung build DevIn production"),
        HumanMessage(content="đang xem một phim sci-fi khá hay"),
    ]

    summary = memory.propose_save(messages)

    assert "life" in summary
    assert "_life_struct" in summary

    memory.save(summary)

    life_content = (tmp_path / "life.md").read_text(encoding="utf-8")
    assert "hôm nay có môn AI lúc sáng" in life_content
    assert "tớ muốn tập trung build DevIn production" in life_content
    assert "đang xem một phim sci-fi khá hay" in life_content


def test_load_daily_parses_sections(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))

    daily = memory.load_daily()

    assert "schedule" in daily
    assert "tomorrow_plan" in daily
    assert "today_review" in daily
    assert "rituals_done_today" in daily


def test_save_daily_review_updates_review_block(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))

    memory.save_daily_review(
        {
            "done": "Built daily ritual mode",
            "learned": "Need lightweight debrief prompts",
            "mood": "drained",
            "time_spent": "2h coding, 1h class",
            "devin_note": "Energy dipped after class but recovered while coding.",
            "patterns": ["Hay giam nang luong sau mon dai"],
        }
    )

    content = (tmp_path / "daily.md").read_text(encoding="utf-8")
    assert "Done: Built daily ritual mode" in content
    assert "Mood: drained" in content
    assert "Hay giam nang luong sau mon dai" in content


def test_save_tomorrow_plan_and_mark_ritual_done(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))

    memory.save_tomorrow_plan(
        ["Attend economics class", "Implement memory parser", "Review tests"],
        notes="3 heavy tasks, keep one buffer slot.",
    )
    memory.mark_ritual_done("morning")

    daily = memory.load_daily()
    content = (tmp_path / "daily.md").read_text(encoding="utf-8")

    assert daily["tomorrow_plan"]["tasks"]
    assert "Notes: 3 heavy tasks, keep one buffer slot." in content
    assert daily["rituals_done_today"]["morning"] != "(not yet)"


def test_propose_save_filters_frustration_and_deduplicates_same_file(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))
    messages = [
        HumanMessage(content="create greet.py that prints Good morning"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_1", name="write_file"),
        HumanMessage(content="write greet.py with print('Good morning')"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_2", name="write_file"),
        HumanMessage(content="no, you create it"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_3", name="write_file"),
        HumanMessage(content="do it for me"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_4", name="write_file"),
        HumanMessage(content="you do it"),
        ToolMessage(content="Success: wrote file to greet.py", tool_call_id="call_5", name="write_file"),
    ]

    summary = memory.propose_save(messages)

    assert "state" in summary
    state = summary["state"].lower()
    assert "created greet.py" in state
    assert state.count("created greet.py") == 1
    assert "no, you create it" not in state
    assert "do it for me" not in state
    assert "you do it" not in state
    assert summary["files_created"] == "greet.py"


def test_propose_save_ignores_short_imperative_without_specifics(tmp_path):
    memory = MemoryEngine(memory_dir=str(tmp_path))
    messages = [
        HumanMessage(content="do it"),
        ToolMessage(content="Success: wrote file to throwaway.py", tool_call_id="call_1", name="write_file"),
    ]

    summary = memory.propose_save(messages)

    assert "state" not in summary
    assert "files_created" not in summary
