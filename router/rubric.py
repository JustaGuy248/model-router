"""The tier rubric — the auditable heart of the router.

Everything the router "believes" about model tiers and how tasks are scored
lives here as plain data, so a human can read, argue with, and tune it without
touching routing logic.

Two data structures:

* ``DIMENSIONS`` — the axes every task is scored on (0-3 each).
* ``TIERS``      — the four model tiers, their capability envelope, and the
                   score thresholds that map a task onto them.

Scoring model
-------------
Each task is scored 0-3 on five dimensions:

    reasoning_depth  0 none/lookup .. 3 novel multi-hop reasoning
    context_length   0 a sentence  .. 3 large multi-doc context
    creativity       0 mechanical  .. 3 open-ended generation/design
    tool_use         0 none        .. 3 orchestrates many tools/steps
    error_cost       0 throwaway   .. 3 hard-to-reverse / high-stakes

A weighted sum produces a single ``difficulty`` number. The tier is the
cheapest tier whose ``max_difficulty`` is >= that number. Weights and
thresholds are deliberately exposed so the mapping is inspectable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Dimension:
    """One scoring axis, with human-readable anchors for each 0-3 level."""

    key: str
    label: str
    weight: float
    anchors: Dict[int, str]


# --- The five scoring dimensions -------------------------------------------
# Weights reflect how strongly each axis pushes a task up the tier ladder.
# reasoning_depth and error_cost dominate because that is where the cheap
# tiers actually fail; context_length matters but a long-but-simple task
# (e.g. "reformat this") should not demand Opus, hence a lower weight.
DIMENSIONS: List[Dimension] = [
    Dimension(
        key="reasoning_depth",
        label="Reasoning depth",
        weight=1.4,
        anchors={
            0: "No reasoning — lookup, extraction, or fixed transform",
            1: "Light reasoning — a summary or a single obvious inference",
            2: "Multi-step logic — chains several steps or conditions",
            3: "Novel/deep reasoning — non-obvious problem solving",
        },
    ),
    Dimension(
        key="context_length",
        label="Context length",
        weight=0.8,
        anchors={
            0: "A sentence or two of context",
            1: "A short document / single file",
            2: "Several documents or a moderate codebase slice",
            3: "Large multi-document / whole-repo context",
        },
    ),
    Dimension(
        key="creativity",
        label="Creativity / open-endedness",
        weight=1.0,
        anchors={
            0: "Mechanical — one correct output",
            1: "Mild phrasing/wording choices",
            2: "Real generation — copy, plans, designs with many valid forms",
            3: "Open-ended invention — novel architecture or strategy",
        },
    ),
    Dimension(
        key="tool_use",
        label="Tool use / orchestration",
        weight=0.9,
        anchors={
            0: "No tools",
            1: "A single tool / API call",
            2: "A few coordinated tools or steps",
            3: "Orchestrates many tools/agents with branching",
        },
    ),
    Dimension(
        key="error_cost",
        label="Cost of being wrong",
        weight=1.3,
        anchors={
            0: "Throwaway — trivially checked or reverted",
            1: "Minor — a human will likely catch it",
            2: "Costly — feeds downstream work, hard to spot",
            3: "Severe — irreversible, security, money, or user-facing",
        },
    ),
]

# Fast lookup by key.
DIMENSION_BY_KEY: Dict[str, Dimension] = {d.key: d for d in DIMENSIONS}

# The maximum possible weighted difficulty (every dimension at 3).
MAX_DIFFICULTY: float = sum(d.weight * 3 for d in DIMENSIONS)


@dataclass(frozen=True)
class Tier:
    """A model tier and the capability envelope it covers."""

    key: str
    label: str
    #: Cheapest tier whose ``max_difficulty`` >= a task's difficulty wins.
    max_difficulty: float
    #: One-line description of what this tier is *for*.
    summary: str
    #: Concrete example task kinds that belong here (documentation + tests).
    examples: List[str] = field(default_factory=list)


# --- The four tiers, cheapest first ----------------------------------------
# ``max_difficulty`` values are expressed as a fraction of MAX_DIFFICULTY so
# the thresholds stay meaningful if weights are re-tuned. See TIER_CUTOFFS.
TIER_CUTOFFS = {
    # tier key -> fraction of MAX_DIFFICULTY it can handle up to
    "local": 0.18,
    "haiku": 0.40,
    "sonnet": 0.70,
    "opus": 1.00,
}

TIERS: List[Tier] = [
    Tier(
        key="local",
        label="Local / small model",
        max_difficulty=TIER_CUTOFFS["local"] * MAX_DIFFICULTY,
        summary="Deterministic extraction, formatting, boilerplate, regex-able work.",
        examples=[
            "Extract all URLs from a file",
            "Reformat JSON / fix indentation",
            "Rename variables by a fixed rule",
            "Split a CSV into columns",
        ],
    ),
    Tier(
        key="haiku",
        label="Haiku (fast, cheap)",
        max_difficulty=TIER_CUTOFFS["haiku"] * MAX_DIFFICULTY,
        summary="Simple summaries, light reasoning, short context, low error cost.",
        examples=[
            "Summarize a short article",
            "Classify a support ticket",
            "Draft a one-line commit message",
            "Answer an FAQ from a snippet",
        ],
    ),
    Tier(
        key="sonnet",
        label="Sonnet (workhorse)",
        max_difficulty=TIER_CUTOFFS["sonnet"] * MAX_DIFFICULTY,
        summary="Multi-step logic, code, moderate context, real generation.",
        examples=[
            "Implement a CRUD endpoint with tests",
            "Refactor a module and update call sites",
            "Write a marketing landing page",
            "Debug a failing test from a stack trace",
        ],
    ),
    Tier(
        key="opus",
        label="Opus (top tier)",
        max_difficulty=TIER_CUTOFFS["opus"] * MAX_DIFFICULTY,
        summary="Novel architecture, hard reasoning, high error-cost decisions.",
        examples=[
            "Design a new distributed system from scratch",
            "Reason about a subtle concurrency bug",
            "Make an irreversible schema/migration decision",
            "Produce a security-critical auth design",
        ],
    ),
]

# Fast lookup + canonical cheap->expensive ordering.
TIER_BY_KEY: Dict[str, Tier] = {t.key: t for t in TIERS}
TIER_ORDER: List[str] = [t.key for t in TIERS]

#: The top tier — the baseline everything is compared against for savings.
TOP_TIER: str = TIER_ORDER[-1]


def tier_for_difficulty(difficulty: float) -> Tier:
    """Return the cheapest tier able to handle ``difficulty``.

    Because ``opus`` has ``max_difficulty == MAX_DIFFICULTY`` it always
    catches anything the cheaper tiers can't, so this never returns ``None``.
    """
    for tier in TIERS:  # already cheapest-first
        if difficulty <= tier.max_difficulty:
            return tier
    return TIER_BY_KEY[TOP_TIER]
