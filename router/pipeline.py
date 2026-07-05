"""End-to-end glue: plan text -> decomposed, scored, (optionally) tie-broken,
rolled-up report.

This is the one function most callers want:

    from router import analyze_plan
    report = analyze_plan(open("plan.md").read(), tiebreaker="off")

``analyze_plan`` returns a :class:`PlanReport` — a plain data object the
formatter turns into a table + savings summary, and which a future skill / MCP
server can serialize straight to JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .decompose import decompose
from .scorer import Scored, score_task
from .pricing import estimate_cost
from .rubric import TIER_ORDER, TOP_TIER
from .tiebreaker import make_tiebreaker


@dataclass
class RoutedTask:
    """A scored task after any tie-break, with its costed numbers."""

    scored: Scored
    final_tier: str
    cost_at_tier: float
    cost_at_top: float

    @property
    def savings(self) -> float:
        return self.cost_at_top - self.cost_at_tier


@dataclass
class PlanReport:
    """The full analysis of a plan."""

    tasks: List[RoutedTask]
    tiebreaker_mode: str
    #: tier key -> number of tasks routed there
    tier_counts: Dict[str, int] = field(default_factory=dict)
    total_cost: float = 0.0
    baseline_cost: float = 0.0          # everything on the top tier
    total_savings: float = 0.0
    savings_pct: float = 0.0
    total_tokens: int = 0

    @property
    def top_tier(self) -> str:
        return TOP_TIER


def analyze_plan(plan_text: str, tiebreaker: str = "off") -> PlanReport:
    """Decompose, score, optionally tie-break, and roll up a plan.

    ``tiebreaker`` is one of ``"off"`` (default), ``"mock"``, or ``"haiku"``.
    """
    tb = make_tiebreaker(tiebreaker)
    tasks = decompose(plan_text)

    routed: List[RoutedTask] = []
    tier_counts: Dict[str, int] = {t: 0 for t in TIER_ORDER}
    total_cost = 0.0
    baseline_cost = 0.0
    total_tokens = 0

    for task in tasks:
        scored = score_task(task)
        final_tier = tb.decide(scored) if tb is not None else scored.tier
        if final_tier != scored.tier:
            scored.heuristic_tier = scored.tier

        cost_at_tier = estimate_cost(final_tier, scored.input_tokens, scored.output_tokens)
        cost_at_top = estimate_cost(TOP_TIER, scored.input_tokens, scored.output_tokens)

        routed.append(
            RoutedTask(
                scored=scored,
                final_tier=final_tier,
                cost_at_tier=cost_at_tier,
                cost_at_top=cost_at_top,
            )
        )
        tier_counts[final_tier] += 1
        total_cost += cost_at_tier
        baseline_cost += cost_at_top
        total_tokens += scored.est_tokens

    total_savings = baseline_cost - total_cost
    savings_pct = (total_savings / baseline_cost * 100.0) if baseline_cost else 0.0

    return PlanReport(
        tasks=routed,
        tiebreaker_mode=(tiebreaker or "off"),
        tier_counts=tier_counts,
        total_cost=total_cost,
        baseline_cost=baseline_cost,
        total_savings=total_savings,
        savings_pct=savings_pct,
        total_tokens=total_tokens,
    )
