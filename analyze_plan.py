#!/usr/bin/env python3
"""analyze_plan.py — route each task in a project plan to the cheapest capable
model tier, and print a cost/savings breakdown.

Usage:
    python analyze_plan.py <plan.md>
    python analyze_plan.py <plan.md> --json
    python analyze_plan.py <plan.md> --tiebreaker mock
    cat plan.md | python analyze_plan.py -

The core logic lives in the importable ``router`` package; this file is only
the CLI shell so the same engine can later back a Claude skill or MCP server.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output even on the Windows console (which defaults to cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from router import analyze_plan
from router.formatter import render_text, render_json


def _read_plan(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    if not p.exists():
        sys.stderr.write(f"error: plan file not found: {path}\n")
        raise SystemExit(2)
    return p.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze_plan.py",
        description="Tag each task in a plan with the cheapest capable model "
        "tier (local/haiku/sonnet/opus) and estimate the savings vs. running "
        "everything on the top model.",
    )
    parser.add_argument(
        "plan",
        help="path to a plan file (markdown or prose), or '-' to read stdin",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of the text table",
    )
    parser.add_argument(
        "--tiebreaker",
        choices=["off", "mock", "haiku"],
        default="off",
        help="resolve ambiguous tasks: off (default), mock (offline, no key), "
        "or haiku (live Haiku call; needs ANTHROPIC_API_KEY, falls back safely)",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    plan_text = _read_plan(args.plan)
    report = analyze_plan(plan_text, tiebreaker=args.tiebreaker)

    if not report.tasks:
        sys.stderr.write(
            "warning: no tasks found in the plan. Provide a markdown list "
            "(1. / - items) or imperative prose.\n"
        )
        return 1

    if args.json:
        print(render_json(report))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
