"""Cost & latency budget grader: per-run hard ceilings on $ and wall-clock."""
from __future__ import annotations

from reliability.evals.graders import GraderOutput


class BudgetsGrader:
    name = "budgets"

    def score(self, case, trace, ctx) -> GraderOutput:
        b = ctx.budgets
        cost = trace.total_cost_usd
        latency = trace.duration_ms
        cost_ok = cost <= b.max_cost_usd
        latency_ok = latency <= b.max_latency_ms
        score = 1.0 if (cost_ok and latency_ok) else 0.0
        return GraderOutput(
            score,
            {
                "cost_usd": cost,
                "max_cost_usd": b.max_cost_usd,
                "cost_ok": cost_ok,
                "latency_ms": latency,
                "max_latency_ms": b.max_latency_ms,
                "latency_ok": latency_ok,
                "input_tokens": trace.total_input_tokens,
                "output_tokens": trace.total_output_tokens,
            },
        )
