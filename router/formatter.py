"""Render a :class:`PlanReport` as text (a table + savings rollup) or JSON.

Two renderers:

* :func:`render_text` — a monospace-friendly table plus a rollup summary, for
  the CLI. Pure ASCII so it prints correctly on every terminal (including the
  Windows console, which mangles fancy box-drawing / em-dashes).
* :func:`render_json` — a JSON-serializable dict, so the same core can be wired
  into a Claude skill or MCP server later with no reformatting.
"""

from __future__ import annotations

import json
from typing import Dict, List

from .pipeline import PlanReport, RoutedTask
from .rubric import TIER_ORDER, TIER_BY_KEY, TOP_TIER


def _truncate(text: str, width: int) -> str:
    text = " ".join(text.split())  # collapse whitespace/newlines
    if len(text) <= width:
        return text
    return text[: max(0, width - 3)] + "..."


def _table(routed: List[RoutedTask], task_width: int = 44, reason_width: int = 40) -> str:
    headers = ["#", "Task", "Tier", "Reason", "Est.Tok", "Cost$"]
    widths = [3, task_width, 7, reason_width, 8, 8]

    def row(cells: List[str]) -> str:
        return "  ".join(c.ljust(w)[:w] for c, w in zip(cells, widths))

    lines = [row(headers), row(["-" * w for w in widths])]
    for i, rt in enumerate(routed, start=1):
        s = rt.scored
        tier_cell = rt.final_tier
        if s.heuristic_tier and s.heuristic_tier != rt.final_tier:
            tier_cell = f"{rt.final_tier}*"  # * = changed by tie-breaker
        lines.append(
            row(
                [
                    str(i),
                    _truncate(s.task.text, task_width),
                    tier_cell,
                    _truncate(s.reason, reason_width),
                    f"{s.est_tokens:,}",
                    f"{rt.cost_at_tier:.4f}",
                ]
            )
        )
    return "\n".join(lines)


def _rollup(report: PlanReport) -> str:
    lines: List[str] = []
    lines.append("Tier distribution:")
    for tier in TIER_ORDER:
        count = report.tier_counts.get(tier, 0)
        if count:
            bar = "#" * count
            lines.append(f"  {tier:7} {count:3}  {bar}")
    lines.append("")
    lines.append(f"Total tasks        : {len(report.tasks)}")
    lines.append(f"Est. total tokens  : {report.total_tokens:,}")
    lines.append(
        f"Cost (routed)      : ${report.total_cost:.4f}"
    )
    lines.append(
        f"Cost (all {TOP_TIER:<6}) : ${report.baseline_cost:.4f}   "
        f"<- baseline: everything on the top model"
    )
    lines.append(
        f"Savings            : ${report.total_savings:.4f}  "
        f"({report.savings_pct:.1f}% cheaper)"
    )
    if report.tiebreaker_mode and report.tiebreaker_mode != "off":
        changed = sum(
            1 for rt in report.tasks
            if rt.scored.heuristic_tier and rt.scored.heuristic_tier != rt.final_tier
        )
        lines.append(
            f"Tie-breaker        : {report.tiebreaker_mode} "
            f"({changed} task(s) reassigned; * in table)"
        )
    return "\n".join(lines)


def render_text(report: PlanReport) -> str:
    """Full human-readable report: table + rollup."""
    parts = [
        "MODEL-ROUTER  -  task-by-task tier assignment",
        "=" * 72,
        _table(report.tasks),
        "",
        "-" * 72,
        _rollup(report),
    ]
    return "\n".join(parts)


def render_json(report: PlanReport) -> str:
    """JSON string — the machine-readable form for skill/MCP use."""
    payload: Dict = {
        "tiebreaker_mode": report.tiebreaker_mode,
        "top_tier": report.top_tier,
        "summary": {
            "total_tasks": len(report.tasks),
            "total_tokens": report.total_tokens,
            "total_cost": round(report.total_cost, 6),
            "baseline_cost": round(report.baseline_cost, 6),
            "total_savings": round(report.total_savings, 6),
            "savings_pct": round(report.savings_pct, 2),
            "tier_counts": report.tier_counts,
        },
        "tasks": [
            {
                "index": rt.scored.task.index,
                "text": rt.scored.task.text,
                "section": rt.scored.task.section,
                "tier": rt.final_tier,
                "heuristic_tier": rt.scored.heuristic_tier,
                "reason": rt.scored.reason,
                "scores": rt.scored.scores,
                "difficulty": rt.scored.difficulty,
                "ambiguous": rt.scored.ambiguous,
                "est_tokens": rt.scored.est_tokens,
                "cost_at_tier": round(rt.cost_at_tier, 6),
                "cost_at_top": round(rt.cost_at_top, 6),
            }
            for rt in report.tasks
        ],
    }
    return json.dumps(payload, indent=2)
