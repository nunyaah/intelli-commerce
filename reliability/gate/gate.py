"""The regression gate decision + a human-readable diff.

A change passes only if ALL hold:
  * absolute floor: pass-rate >= the configured minimum,
  * no critical-grader collapse: safety-critical graders (grounding, sql_safety)
    don't drop below their floor,
  * budgets: aggregate cost / mean latency within budget,
  * no statistical regression vs the baseline (paired delta CI not below zero and
    McNemar not significantly worse).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from reliability.config import Budgets
from reliability.evals.report import RunReport
from reliability.stats.compare import REGRESSED, Comparison, compare_runs

# Graders whose pass-rate must never silently collapse, baseline or not.
CRITICAL_GRADERS = ("grounding", "sql_safety")


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    candidate_summary: dict = field(default_factory=dict)
    baseline_summary: Optional[dict] = None
    comparison: Optional[Comparison] = None

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reasons": self.reasons,
            "candidate_summary": self.candidate_summary,
            "baseline_summary": self.baseline_summary,
            "comparison": self.comparison.as_dict() if self.comparison else None,
        }


def run_gate(
    candidate: RunReport,
    baseline: Optional[RunReport] = None,
    budgets: Optional[Budgets] = None,
    min_pass_rate: float = 0.8,
    critical_grader_floor: float = 0.9,
    alpha: float = 0.05,
    seed: int = 1234,
) -> GateResult:
    budgets = budgets or Budgets()
    reasons: list[str] = []
    passed = True

    summary = candidate.summary()

    # 1) Absolute floor.
    if candidate.pass_rate < min_pass_rate:
        passed = False
        reasons.append(
            f"FAIL: pass-rate {candidate.pass_rate:.1%} is below the minimum {min_pass_rate:.0%}."
        )
    else:
        reasons.append(f"OK: pass-rate {candidate.pass_rate:.1%} meets the {min_pass_rate:.0%} floor.")

    # 2) Critical-grader collapse.
    grader_rates = candidate.grader_pass_rates()
    for g in CRITICAL_GRADERS:
        if g in grader_rates and grader_rates[g] < critical_grader_floor:
            passed = False
            reasons.append(
                f"FAIL: critical grader '{g}' pass-rate {grader_rates[g]:.1%} "
                f"below floor {critical_grader_floor:.0%}."
            )

    # 3) Budgets (aggregate cost + mean latency).
    agg_cost_budget = budgets.max_cost_usd * max(1, len(candidate.cases))
    if candidate.total_cost > agg_cost_budget:
        passed = False
        reasons.append(
            f"FAIL: total cost ${candidate.total_cost:.5f} exceeds budget ${agg_cost_budget:.5f}."
        )
    if candidate.avg_latency_ms > budgets.max_latency_ms:
        passed = False
        reasons.append(
            f"FAIL: mean latency {candidate.avg_latency_ms:.0f}ms exceeds budget "
            f"{budgets.max_latency_ms:.0f}ms."
        )

    # 4) Regression vs baseline.
    comparison: Optional[Comparison] = None
    if baseline is not None:
        comparison = compare_runs(baseline, candidate, alpha=alpha, seed=seed)
        if comparison.verdict == REGRESSED:
            passed = False
            reasons.append("FAIL: statistically significant regression vs baseline:")
            reasons.extend(f"  - {r}" for r in comparison.reasons)
        else:
            reasons.append(f"OK: no regression vs baseline ({comparison.verdict}).")
            reasons.extend(f"  - {r}" for r in comparison.reasons)
    else:
        reasons.append("NOTE: no baseline found — gating on absolute thresholds only.")

    return GateResult(
        passed=passed,
        reasons=reasons,
        candidate_summary=summary,
        baseline_summary=baseline.summary() if baseline else None,
        comparison=comparison,
    )
