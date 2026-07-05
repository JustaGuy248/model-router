"""Model-Router: tag each task in a plan with the cheapest capable model tier.

The package is intentionally dependency-free (standard library only) so the
core logic can later be wrapped as a Claude skill or an MCP server without
dragging in a heavy install.

Typical use::

    from router import analyze_plan
    from router.formatter import render_text
    report = analyze_plan(open("plan.md").read())
    print(render_text(report))
"""

from .rubric import TIERS, DIMENSIONS, Tier, Dimension  # noqa: F401
from .decompose import Task, decompose  # noqa: F401
from .scorer import score_task, route_task, Scored  # noqa: F401
from .pricing import PRICING, estimate_cost  # noqa: F401
from .tiebreaker import make_tiebreaker, TieBreaker  # noqa: F401
from .pipeline import analyze_plan, PlanReport, RoutedTask  # noqa: F401
from .formatter import render_text, render_json  # noqa: F401

__version__ = "0.1.0"

__all__ = [
    "TIERS",
    "DIMENSIONS",
    "Tier",
    "Dimension",
    "Task",
    "decompose",
    "score_task",
    "route_task",
    "Scored",
    "PRICING",
    "estimate_cost",
    "make_tiebreaker",
    "TieBreaker",
    "analyze_plan",
    "PlanReport",
    "RoutedTask",
    "render_text",
    "render_json",
    "__version__",
]
