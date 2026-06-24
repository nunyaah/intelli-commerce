"""Token -> cost model.

Prices are USD per 1M tokens. Groq publishes per-model pricing; these are the
mid-2026 free/standard-tier figures and are deliberately easy to update. The
point is a *consistent, auditable* cost number attached to every span, not
billing-grade accuracy.
"""
from __future__ import annotations

from dataclasses import dataclass

# USD per 1,000,000 tokens (input, output).
PRICING: dict[str, tuple[float, float]] = {
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-70b-versatile": (0.59, 0.79),
    "gemma2-9b-it": (0.20, 0.20),
    "mixtral-8x7b-32768": (0.24, 0.24),
}

# Used when a model is unknown so cost is never silently zero.
_FALLBACK = (0.10, 0.10)


@dataclass(frozen=True)
class CostBreakdown:
    input_tokens: int
    output_tokens: int
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def price_for(model: str) -> tuple[float, float]:
    if model in PRICING:
        return PRICING[model]
    # Tolerate vendor prefixes / version suffixes.
    for key, val in PRICING.items():
        if key in model or model in key:
            return val
    return _FALLBACK


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = price_for(model)
    return round(
        (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate,
        8,
    )


def breakdown(model: str, input_tokens: int, output_tokens: int) -> CostBreakdown:
    return CostBreakdown(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd(model, input_tokens, output_tokens),
    )
