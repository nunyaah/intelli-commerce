"""Max-cost circuit breaker.

Tracks cumulative spend within a single agent run and trips when it would exceed
the budget, so a misbehaving (e.g. looping) agent can't run up an unbounded bill.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CircuitBreaker:
    max_cost_usd: float
    spent_usd: float = 0.0
    tripped: bool = False

    def add(self, cost_usd: float) -> bool:
        """Record additional spend. Returns True if the breaker is (now) tripped."""
        self.spent_usd = round(self.spent_usd + max(0.0, cost_usd), 8)
        if self.spent_usd > self.max_cost_usd:
            self.tripped = True
        return self.tripped

    def would_exceed(self, next_cost_usd: float) -> bool:
        return (self.spent_usd + next_cost_usd) > self.max_cost_usd
