"""Heuristic scorer: a task -> per-dimension scores -> difficulty -> tier.

This is the fast, free, deterministic engine. It reads the task text, matches
signal keywords for each rubric dimension, takes the highest level that fires
(with a sensible floor), then feeds the weighted sum through the rubric's tier
cutoffs.

It also estimates token usage per task and flags *ambiguous* tasks — ones whose
difficulty lands close to a tier boundary — as candidates for the optional
Haiku tie-breaker.

Everything here is inspectable: the per-dimension score and the exact signal
that raised it are recorded on the ``Scored`` result so the reason column in
the report is honest, not hand-wavy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .decompose import Task
from .rubric import (
    DIMENSIONS,
    MAX_DIFFICULTY,
    TIER_BY_KEY,
    TIER_ORDER,
    tier_for_difficulty,
)


# --- Signal tables ---------------------------------------------------------
# For each dimension: (level, [keywords]). The scorer takes the MAX level whose
# keyword appears in the task text. Keywords are matched as whole words,
# case-insensitively. Order within a dimension does not matter — max wins.
#
# These tables are the tuning surface. Add a word here, not logic below.
SIGNALS: Dict[str, List[Tuple[int, List[str]]]] = {
    "reasoning_depth": [
        (0, ["extract", "list", "rename", "format", "reformat", "copy",
             "lint", "sort", "count", "strip", "concatenate"]),
        (1, ["summarize", "summary", "classify", "categorize", "explain",
             "describe", "tag", "label", "draft", "answer"]),
        (2, ["implement", "build", "code", "refactor", "integrate", "wire",
             "parse", "compute", "calculate", "transform", "validate",
             "debug", "fix", "test", "configure"]),
        (3, ["design", "architect", "architecture", "algorithm", "optimize",
             "concurrency", "distributed", "strategy", "reason", "prove",
             "novel", "research", "tradeoff", "trade-off", "scalab"]),
    ],
    "context_length": [
        (0, ["a line", "single line", "one file", "snippet", "sentence"]),
        (1, ["file", "function", "module", "endpoint", "component"]),
        (2, ["several", "multiple files", "across", "codebase", "package",
             "subsystem", "many"]),
        (3, ["whole repo", "entire codebase", "monorepo", "all documents",
             "cross-repo", "system-wide", "everything"]),
    ],
    "creativity": [
        (0, ["extract", "format", "reformat", "rename", "parse", "validate",
             "lint", "sort", "count"]),
        (1, ["rewrite", "rephrase", "tweak", "adjust"]),
        (2, ["write", "generate", "create", "compose", "design",
             "plan", "landing page", "content", "blog", "newsletter",
             "marketing", "copywrite"]),
        (3, ["invent", "novel", "from scratch", "brainstorm", "greenfield",
             "new architecture", "creative"]),
    ],
    "tool_use": [
        (0, []),
        (1, ["api", "query", "fetch", "http", "request", "endpoint"]),
        (2, ["integrate", "pipeline", "orchestrate", "database", "deploy",
             "ci", "workflow", "multiple services", "distributed"]),
        (3, ["multi-agent", "agents", "orchestration", "distributed system",
             "microservices", "event-driven"]),
    ],
    "error_cost": [
        (0, ["scratch note", "example", "sample", "prototype", "throwaway",
             "comment"]),
        (1, ["summary", "summarize", "rename", "docs", "documentation",
             "readme"]),
        (2, ["implement", "refactor", "data", "compute", "billing",
             "pricing", "report", "customer-facing", "architecture",
             "design", "novel"]),
        (3, ["migration", "migrate", "schema", "security", "auth",
             "authentication", "payment", "irreversible", "production",
             "delete", "encryption", "credentials", "money", "from scratch",
             "greenfield", "new architecture"]),
    ],
}

# Per-dimension floor so a bland task is not scored all-zero. Kept LOW so that
# genuinely deterministic tasks (extract/format) can reach the `local` tier —
# a higher reasoning floor made `local` unreachable. Unknown tasks (nothing
# matched at all) are handled separately in ``score_task`` for safety.
DIMENSION_FLOOR: Dict[str, int] = {
    "reasoning_depth": 0,
    "context_length": 1,
    "creativity": 0,
    "tool_use": 0,
    "error_cost": 1,
}

# A task whose difficulty is within this fraction of MAX_DIFFICULTY of a tier
# boundary is considered *ambiguous* and eligible for the tie-breaker.
AMBIGUITY_MARGIN: float = 0.06 * MAX_DIFFICULTY

# Token estimation anchors (deterministic). Indexed by dimension level 0-3.
_INPUT_TOKENS_BY_CONTEXT = {0: 400, 1: 1500, 2: 6000, 3: 25000}
_OUTPUT_TOKENS_BY_EFFORT = {0: 150, 1: 500, 2: 1500, 3: 4000}


@dataclass
class Scored:
    """The full, auditable scoring result for one task."""

    task: Task
    scores: Dict[str, int]                 # dimension key -> 0..3
    evidence: Dict[str, str]               # dimension key -> matched signal / "floor"
    difficulty: float
    tier: str
    reason: str
    input_tokens: int
    output_tokens: int
    ambiguous: bool
    #: If a tie-breaker overrides the tier, the original is preserved here.
    heuristic_tier: Optional[str] = None
    meta: dict = field(default_factory=dict)

    @property
    def est_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def _match_dimension(text_lower: str, dim_key: str) -> Tuple[int, str]:
    """Return (level, evidence) — the highest firing signal for a dimension.

    Starts at the dimension's floor with evidence "floor". Any keyword that
    matches and sits at a strictly higher level takes over, recording the word
    that won as evidence.
    """
    best_level = DIMENSION_FLOOR[dim_key]
    best_evidence = "floor"
    for level, keywords in SIGNALS[dim_key]:
        # Consider a level if it can raise the score, OR if it equals the floor
        # and we have not yet recorded real evidence (so a level-0 "extract"
        # match is remembered as a genuine `local` signal, not "no signal").
        if level < best_level:
            continue
        if level == best_level and best_evidence != "floor":
            continue
        for kw in keywords:
            # Whole-word match for single words; substring for multi-word phrases.
            pattern = re.escape(kw) if " " in kw else r"\b" + re.escape(kw)
            if re.search(pattern, text_lower):
                best_level = level
                best_evidence = kw
                break  # this level is settled; move to higher levels
    return best_level, best_evidence


def _reason_string(scored_dims: Dict[str, int], evidence: Dict[str, str], tier: str) -> str:
    """Human-readable justification for the chosen tier."""
    # Surface the two dimensions that contributed most (score * weight).
    weight = {d.key: d.weight for d in DIMENSIONS}
    ranked = sorted(
        scored_dims.items(), key=lambda kv: kv[1] * weight[kv[0]], reverse=True
    )
    label = {d.key: d.label for d in DIMENSIONS}
    parts = []
    for key, score in ranked[:2]:
        ev = evidence.get(key, "floor")
        tag = f"{label[key].lower()}={score}"
        if ev != "floor":
            tag += f" ('{ev}')"
        parts.append(tag)
    return f"{TIER_BY_KEY[tier].label}: " + ", ".join(parts)


def score_task(task: Task) -> Scored:
    """Score one task deterministically and route it to a tier."""
    text_lower = task.text.lower()

    scores: Dict[str, int] = {}
    evidence: Dict[str, str] = {}
    for dim in DIMENSIONS:
        level, ev = _match_dimension(text_lower, dim.key)
        scores[dim.key] = level
        evidence[dim.key] = ev

    difficulty = sum(scores[d.key] * d.weight for d in DIMENSIONS)
    tier = tier_for_difficulty(difficulty).key

    # Token estimate: input driven by context size + task length; output by the
    # harder of reasoning/creativity.
    ctx = scores["context_length"]
    effort = max(scores["reasoning_depth"], scores["creativity"])
    task_words = len(task.text.split())
    input_tokens = _INPUT_TOKENS_BY_CONTEXT[ctx] + int(task_words * 1.3)
    output_tokens = _OUTPUT_TOKENS_BY_EFFORT[effort]

    # Ambiguity: difficulty sits near any tier boundary.
    ambiguous = _is_near_boundary(difficulty)

    # Safety net: if NOTHING matched (every dimension sat at its floor), we have
    # no real signal. Don't trust the cheap `local` tier for an unknown task —
    # bump to at least `haiku` and flag it as ambiguous for the tie-breaker.
    no_signal = all(ev == "floor" for ev in evidence.values())
    if no_signal:
        ambiguous = True
        if TIER_ORDER.index(tier) < TIER_ORDER.index("haiku"):
            tier = "haiku"

    reason = _reason_string(scores, evidence, tier)
    if no_signal:
        reason = f"{TIER_BY_KEY[tier].label}: no strong signals - safe default"

    return Scored(
        task=task,
        scores=scores,
        evidence=evidence,
        difficulty=round(difficulty, 3),
        tier=tier,
        reason=reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        ambiguous=ambiguous,
    )


def _is_near_boundary(difficulty: float) -> bool:
    """True if ``difficulty`` is within AMBIGUITY_MARGIN of a tier cutoff."""
    from .rubric import TIERS

    for tier in TIERS[:-1]:  # boundaries are the non-top cutoffs
        if abs(difficulty - tier.max_difficulty) <= AMBIGUITY_MARGIN:
            return True
    return False


def route_task(task: Task) -> Scored:
    """Alias for :func:`score_task` — the "route" verb reads better at callsites."""
    return score_task(task)
