"""End-to-end pipeline, tie-breaker, formatter, and pricing tests — offline."""

import json
from pathlib import Path

from router import analyze_plan
from router.formatter import render_text, render_json
from router.pricing import estimate_cost, PRICING
from router.tiebreaker import make_tiebreaker, mock_tie_fn, haiku_tie_fn
from router.decompose import Task
from router.scorer import score_task

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_every_task_gets_tier_and_reason():
    report = analyze_plan((EXAMPLES / "plan_saas_mvp.md").read_text(encoding="utf-8"))
    assert report.tasks, "expected tasks from the sample plan"
    for rt in report.tasks:
        assert rt.final_tier in {"local", "haiku", "sonnet", "opus"}
        assert rt.scored.reason
        assert rt.scored.est_tokens > 0


def test_savings_math_is_consistent():
    report = analyze_plan((EXAMPLES / "plan_data_pipeline.md").read_text(encoding="utf-8"))
    recomputed_routed = sum(rt.cost_at_tier for rt in report.tasks)
    recomputed_top = sum(rt.cost_at_top for rt in report.tasks)
    assert abs(recomputed_routed - report.total_cost) < 1e-9
    assert abs(recomputed_top - report.baseline_cost) < 1e-9
    assert abs((report.baseline_cost - report.total_cost) - report.total_savings) < 1e-9
    # Routing to cheaper tiers can only reduce or match the baseline.
    assert report.total_cost <= report.baseline_cost + 1e-9
    if report.baseline_cost > 0:
        assert 0 <= report.savings_pct <= 100


def test_baseline_equals_all_top_tier():
    report = analyze_plan((EXAMPLES / "plan_saas_mvp.md").read_text(encoding="utf-8"))
    manual = sum(
        estimate_cost("opus", rt.scored.input_tokens, rt.scored.output_tokens)
        for rt in report.tasks
    )
    assert abs(manual - report.baseline_cost) < 1e-9


def test_tier_counts_sum_to_task_count():
    report = analyze_plan((EXAMPLES / "plan_saas_mvp.md").read_text(encoding="utf-8"))
    assert sum(report.tier_counts.values()) == len(report.tasks)


def test_prose_plan_produces_tasks():
    report = analyze_plan((EXAMPLES / "plan_content_prose.md").read_text(encoding="utf-8"))
    assert len(report.tasks) >= 5


def test_tiebreaker_off_is_none_and_no_reassignment():
    assert make_tiebreaker("off") is None
    report = analyze_plan("1. Reformat the file.\n2. Summarize the notes.", tiebreaker="off")
    assert all(rt.scored.heuristic_tier is None for rt in report.tasks)


def test_mock_tiebreaker_runs_offline():
    report = analyze_plan(
        (EXAMPLES / "plan_saas_mvp.md").read_text(encoding="utf-8"), tiebreaker="mock"
    )
    assert report.tiebreaker_mode == "mock"
    # It must still assign a valid tier to every task.
    assert all(rt.final_tier in PRICING for rt in report.tasks)


def test_mock_tie_fn_respects_candidates():
    assert mock_tie_fn("Extract the list of URLs", ["local", "haiku"]) == "local"
    assert mock_tie_fn("Design the architecture", ["sonnet", "opus"]) == "opus"


def test_haiku_tie_fn_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # With no key it must return the cheapest candidate, never raise.
    assert haiku_tie_fn("Design a novel system", ["sonnet", "opus"]) == "sonnet"


def test_render_text_is_ascii_safe():
    report = analyze_plan((EXAMPLES / "plan_saas_mvp.md").read_text(encoding="utf-8"))
    text = render_text(report)
    text.encode("ascii")  # raises if any non-ASCII slipped in
    assert "MODEL-ROUTER" in text
    assert "Savings" in text


def test_render_json_roundtrips():
    report = analyze_plan((EXAMPLES / "plan_data_pipeline.md").read_text(encoding="utf-8"))
    payload = json.loads(render_json(report))
    assert payload["summary"]["total_tasks"] == len(report.tasks)
    assert len(payload["tasks"]) == len(report.tasks)
    assert payload["top_tier"] == "opus"


def test_estimate_cost_unknown_tier_uses_max():
    unknown = estimate_cost("bogus", 1000, 1000)
    opus = estimate_cost("opus", 1000, 1000)
    assert unknown == opus


def test_local_is_free():
    assert estimate_cost("local", 10_000, 10_000) == 0.0
