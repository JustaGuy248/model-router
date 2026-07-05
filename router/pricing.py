"""Per-tier token pricing and cost math.

Prices are **approximate USD per 1,000,000 tokens** and are intentionally kept
as editable data — plug in your real contract rates and every number the tool
prints updates. ``local`` is treated as $0 (self-hosted); it still consumes
tokens, which is why the estimator tracks them.

The numbers below are representative list prices for the Claude tiers as of the
2026 model line-up (Haiku 4.5 / Sonnet 5 / Opus 4.x). They are the *defaults*,
not a source of truth — see ``PRICING`` to override.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class TierPrice:
    """USD per 1,000,000 tokens, split by input vs. output."""

    input_per_mtok: float
    output_per_mtok: float


# tier key -> price. Edit these to match your actual rates.
PRICING: Dict[str, TierPrice] = {
    "local": TierPrice(0.0, 0.0),
    "haiku": TierPrice(1.0, 5.0),
    "sonnet": TierPrice(3.0, 15.0),
    "opus": TierPrice(15.0, 75.0),
}


def estimate_cost(tier: str, input_tokens: float, output_tokens: float) -> float:
    """Cost in USD to run ``input/output_tokens`` on ``tier``.

    Unknown tiers fall back to the most expensive rate so a mistake surfaces as
    an over-estimate rather than a silent $0.
    """
    price = PRICING.get(tier)
    if price is None:
        price = max(PRICING.values(), key=lambda p: p.output_per_mtok)
    return (
        input_tokens / 1_000_000 * price.input_per_mtok
        + output_tokens / 1_000_000 * price.output_per_mtok
    )
