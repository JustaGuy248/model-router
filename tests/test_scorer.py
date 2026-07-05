"""Tests for the heuristic scorer and rubric — deterministic, offline."""

import pytest

from router.decompose import Task
from router.scorer import score_task
from router.rubric import DIMENSIONS, MAX_DIFFICULTY, tier_for_difficulty, TIER_ORDER


def _score(text):
    return score_task(Task(text=text, index=1))


def test_local_for_deterministic_extraction():
    for text in [
        "Extract all email addresses from the log file",
        "Reformat this JSON file",
        "Rename the columns to snake_case",
    ]:
        assert _score(text).tier == "local", text


def test_haiku_for_simple_summary():
    assert _score("Summarize the weekly changelog into three bullets").tier == "haiku"


def test_sonnet_for_code_and_multistep():
    for text in [
        "Implement a REST endpoint for user signup with tests",
        "Refactor the billing module and update the call sites",
    ]:
        assert _score(text).tier == "sonnet", text


def test_opus_for_novel_architecture():
    s = _score("Design a novel distributed rate-limiter from scratch")
    assert s.tier == "opus"


def test_tiers_are_monotonic_in_difficulty():
    easy = _score("Extract URLs from a file").difficulty
    mid = _score("Implement a CRUD endpoint with tests").difficulty
    hard = _score("Design a novel distributed system from scratch").difficulty
    assert easy < mid < hard


def test_unknown_task_is_safe_default_not_local():
    s = _score("Do the needful with the thing")
    assert s.tier != "local"       # never route an unknown task to local
    assert s.ambiguous is True


def test_scores_cover_all_dimensions():
    s = _score("Implement the login endpoint")
    assert set(s.scores.keys()) == {d.key for d in DIMENSIONS}
    assert all(0 <= v <= 3 for v in s.scores.values())


def test_reason_is_populated():
    s = _score("Design the auth architecture")
    assert s.reason and isinstance(s.reason, str)


def test_token_estimates_positive():
    s = _score("Summarize the release notes")
    assert s.input_tokens > 0
    assert s.output_tokens > 0
    assert s.est_tokens == s.input_tokens + s.output_tokens


@pytest.mark.parametrize(
    "difficulty,expected",
    [
        (0.0, "local"),
        (MAX_DIFFICULTY, "opus"),
        (MAX_DIFFICULTY * 10, "opus"),  # above max still resolves
    ],
)
def test_tier_for_difficulty_bounds(difficulty, expected):
    assert tier_for_difficulty(difficulty).key == expected


def test_tier_order_is_cheapest_first():
    assert TIER_ORDER == ["local", "haiku", "sonnet", "opus"]
