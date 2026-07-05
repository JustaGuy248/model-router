"""Tests for the plan decomposer — all offline, no network."""

from router.decompose import decompose


def test_numbered_list():
    tasks = decompose("1. First task.\n2. Second task.\n3. Third task.")
    assert [t.text for t in tasks] == ["First task.", "Second task.", "Third task."]
    assert [t.index for t in tasks] == [1, 2, 3]
    assert all(t.source == "list" for t in tasks)


def test_bulleted_and_paren_markers():
    tasks = decompose("- alpha\n* beta\n+ gamma\n1) delta")
    assert [t.text for t in tasks] == ["alpha", "beta", "gamma", "delta"]


def test_nested_depth():
    plan = "1. Top level\n   - nested child\n     - deeper child"
    tasks = decompose(plan)
    assert tasks[0].depth == 0
    assert tasks[1].depth == 1
    assert tasks[2].depth == 2


def test_checkbox_state_stripped():
    tasks = decompose("- [ ] todo item\n- [x] done item")
    assert tasks[0].text == "todo item"
    assert tasks[0].done is False
    assert tasks[1].text == "done item"
    assert tasks[1].done is True


def test_headings_become_sections_not_tasks():
    plan = "# Title\n## Setup\n1. do a thing\n## Build\n2. do another"
    tasks = decompose(plan)
    assert len(tasks) == 2
    assert tasks[0].section == "Setup"
    assert tasks[1].section == "Build"


def test_code_fences_skipped():
    plan = "1. real task\n```\n1. fake task inside code\n```\n2. another real task"
    tasks = decompose(plan)
    assert [t.text for t in tasks] == ["real task", "another real task"]


def test_prose_fallback_picks_imperatives():
    plan = "We need to add caching. Build the CLI wrapper. The sky is blue today."
    tasks = decompose(plan)
    texts = [t.text for t in tasks]
    assert any("add caching" in t for t in texts)
    assert any("Build the CLI wrapper" in t for t in texts)
    assert not any("sky is blue" in t for t in texts)
    assert all(t.source == "prose" for t in tasks)


def test_empty_plan_returns_empty():
    assert decompose("") == []
    assert decompose("\n\n   \n") == []


def test_blockquotes_ignored():
    plan = "> a quoted line\n1. a genuine task"
    tasks = decompose(plan)
    assert len(tasks) == 1
    assert tasks[0].text == "a genuine task"
