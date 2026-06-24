"""In-memory eval report types (consumed by the stats comparison + the gate)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CaseReport:
    case_id: str
    trace_id: str
    query: str
    overall_score: float
    passed: bool
    grader_scores: dict[str, float] = field(default_factory=dict)
    grader_passed: dict[str, bool] = field(default_factory=dict)
    grader_details: dict[str, dict] = field(default_factory=dict)
    difficulty: str = "medium"
    tags: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class RunReport:
    run_id: str
    dataset_version: str
    agent_label: str
    agent_version: dict
    mode: str
    seed: int
    cases: dict[str, CaseReport] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for c in self.cases.values() if c.passed) / len(self.cases)

    @property
    def total_cost(self) -> float:
        return round(sum(c.cost_usd for c in self.cases.values()), 8)

    @property
    def avg_latency_ms(self) -> float:
        if not self.cases:
            return 0.0
        return round(float(np.mean([c.latency_ms for c in self.cases.values()])), 2)

    @property
    def mean_overall(self) -> float:
        if not self.cases:
            return 0.0
        return round(float(np.mean([c.overall_score for c in self.cases.values()])), 4)

    def grader_pass_rates(self) -> dict[str, float]:
        agg: dict[str, list[bool]] = {}
        for c in self.cases.values():
            for g, p in c.grader_passed.items():
                agg.setdefault(g, []).append(p)
        return {g: round(sum(v) / len(v), 4) for g, v in agg.items()}

    def grader_means(self) -> dict[str, float]:
        agg: dict[str, list[float]] = {}
        for c in self.cases.values():
            for g, s in c.grader_scores.items():
                agg.setdefault(g, []).append(s)
        return {g: round(float(np.mean(v)), 4) for g, v in agg.items()}

    def summary(self) -> dict:
        return {
            "pass_rate": round(self.pass_rate, 4),
            "mean_overall_score": self.mean_overall,
            "total_cost_usd": self.total_cost,
            "avg_latency_ms": self.avg_latency_ms,
            "num_cases": len(self.cases),
            "num_passed": sum(1 for c in self.cases.values() if c.passed),
            "grader_pass_rates": self.grader_pass_rates(),
            "grader_means": self.grader_means(),
        }
