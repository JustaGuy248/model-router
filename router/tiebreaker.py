"""Optional Haiku tie-breaker for *ambiguous* tasks.

The heuristic scorer flags tasks whose difficulty lands near a tier boundary as
``ambiguous``. Rather than pay for an LLM on every task, we only (optionally)
ask a cheap model to break those ties.

Design goals baked in here:

* **Off by default.** The pipeline never calls this unless explicitly enabled.
* **Pluggable.** A tie-breaker is just a callable
  ``(task_text, candidate_tiers) -> chosen_tier``. Swap in any implementation.
* **Mockable / no key required.** The default when you *do* enable tie-breaking
  without wiring a real client is a deterministic offline stub, so tests and
  demos run with no network and no ``ANTHROPIC_API_KEY``.
* **Fail-safe.** Any error from a live call falls back to the heuristic tier —
  the tool never crashes because an API blipped.

Public surface:

    make_tiebreaker(mode="off" | "mock" | "haiku") -> TieBreaker | None
    TieBreaker.decide(scored) -> str            # returns a tier key
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional

from .rubric import TIER_ORDER, TIER_BY_KEY
from .scorer import Scored

# A tie-break function: given the task text and the candidate tiers (cheapest
# first), return the chosen tier key.
TieFn = Callable[[str, List[str]], str]


def _candidate_tiers(scored: Scored) -> List[str]:
    """The heuristic tier plus its immediate neighbours, cheapest first.

    A boundary task realistically belongs to its tier or an adjacent one, so we
    only offer those choices — never a wild jump.
    """
    i = TIER_ORDER.index(scored.tier)
    lo = max(0, i - 1)
    hi = min(len(TIER_ORDER) - 1, i + 1)
    return TIER_ORDER[lo : hi + 1]


# --- Mock tie-breaker (deterministic, offline) -----------------------------
def mock_tie_fn(task_text: str, candidates: List[str]) -> str:
    """Deterministic offline stand-in for a real model.

    Heuristic-of-a-heuristic: if the task text contains a "hard" cue, pick the
    most expensive candidate; if it contains an "easy" cue, pick the cheapest;
    otherwise keep the middle (or the cheaper of two). Purely rule-based so it
    is reproducible in tests without any network.
    """
    text = task_text.lower()
    hard_cues = ("why", "design", "trade", "decide", "architecture", "secure",
                 "concurren", "novel", "migrate", "schema")
    easy_cues = ("list", "extract", "format", "rename", "copy paste",
                 "boilerplate", "simple", "trivial")

    if any(c in text for c in hard_cues):
        return candidates[-1]
    if any(c in text for c in easy_cues):
        return candidates[0]
    # No strong cue: keep the middle option, or the cheaper of a pair.
    return candidates[len(candidates) // 2] if len(candidates) > 1 else candidates[0]


# --- Live Haiku tie-breaker (lazy, fail-safe) ------------------------------
def haiku_tie_fn(task_text: str, candidates: List[str]) -> str:
    """Ask Haiku to pick among candidate tiers. Falls back on any problem.

    Requires the ``anthropic`` package and an ``ANTHROPIC_API_KEY``. If either
    is missing, or the call/parse fails, returns the cheapest candidate as a
    conservative, cost-saving default (the caller can override).
    """
    fallback = candidates[0]
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return fallback
    try:
        import anthropic  # imported lazily so the package stays optional
    except ImportError:
        return fallback

    options = ", ".join(candidates)
    descriptions = "\n".join(
        f"- {t}: {TIER_BY_KEY[t].summary}" for t in candidates
    )
    prompt = (
        "You route software tasks to the cheapest capable model tier.\n"
        f"Task: {task_text!r}\n\n"
        f"Choose exactly ONE of these tiers: {options}\n"
        f"{descriptions}\n\n"
        "Reply with only the tier name, nothing else."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip().lower()
        for cand in candidates:
            if cand in answer:
                return cand
        return fallback
    except Exception:
        # Network error, auth error, rate limit, malformed response -> fail safe.
        return fallback


@dataclass
class TieBreaker:
    """Wraps a tie-break function and applies it only to ambiguous tasks."""

    fn: TieFn
    name: str

    def decide(self, scored: Scored) -> str:
        """Return the tier for ``scored`` after (maybe) breaking the tie.

        Non-ambiguous tasks are returned unchanged. Ambiguous tasks are handed
        to the tie-break function with their candidate neighbourhood.
        """
        if not scored.ambiguous:
            return scored.tier
        candidates = _candidate_tiers(scored)
        chosen = self.fn(scored.task.text, candidates)
        return chosen if chosen in candidates else scored.tier


def make_tiebreaker(mode: str = "off") -> Optional[TieBreaker]:
    """Factory. ``mode`` is one of:

    * ``"off"``   -> ``None``; the pipeline uses heuristic tiers as-is (default).
    * ``"mock"``  -> deterministic offline tie-breaker (no key, no network).
    * ``"haiku"`` -> live Haiku call, falling back to mock/cheapest on failure.
    """
    mode = (mode or "off").lower()
    if mode == "off":
        return None
    if mode == "mock":
        return TieBreaker(fn=mock_tie_fn, name="mock")
    if mode == "haiku":
        return TieBreaker(fn=haiku_tie_fn, name="haiku")
    raise ValueError(f"unknown tie-breaker mode: {mode!r} (use off|mock|haiku)")
