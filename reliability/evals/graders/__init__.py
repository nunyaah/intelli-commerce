"""Graders: programmatic (tool-selection, grounding, SQL-safety, budgets) and
LLM-as-judge (answer-quality). Each returns a 0..1 score + details; the runner
applies the dataset's pass threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from reliability.config import Budgets
from reliability.evals.dataset import Dataset, EvalCase
from reliability.tracing.schema import Trace


@dataclass
class GraderOutput:
    score: float
    details: dict = field(default_factory=dict)


@dataclass
class GradeContext:
    judge: object  # MockJudge | GroqJudge
    budgets: Budgets
    dataset: Dataset


@dataclass
class CaseGrade:
    grader: str
    score: float
    passed: bool
    threshold: float
    weight: float
    details: dict


from reliability.evals.graders.tool_selection import ToolSelectionGrader  # noqa: E402
from reliability.evals.graders.grounding import GroundingGrader  # noqa: E402
from reliability.evals.graders.sql_safety import SqlSafetyGrader  # noqa: E402
from reliability.evals.graders.answer_quality import AnswerQualityGrader  # noqa: E402
from reliability.evals.graders.budgets import BudgetsGrader  # noqa: E402

REGISTRY = {
    g.name: g
    for g in [
        ToolSelectionGrader(),
        GroundingGrader(),
        SqlSafetyGrader(),
        AnswerQualityGrader(),
        BudgetsGrader(),
    ]
}


def grade_case(case: EvalCase, trace: Trace, ctx: GradeContext) -> list[CaseGrade]:
    """Run every grader the case declares; return per-grader pass/fail."""
    out: list[CaseGrade] = []
    for grader_name in case.graders:
        grader = REGISTRY.get(grader_name)
        if grader is None:
            continue
        result = grader.score(case, trace, ctx)
        threshold = ctx.dataset.threshold_for(grader_name, case)
        weight = ctx.dataset.weight_for(grader_name)
        out.append(
            CaseGrade(
                grader=grader_name,
                score=round(result.score, 4),
                passed=result.score >= threshold - 1e-9,
                threshold=threshold,
                weight=weight,
                details=result.details,
            )
        )
    return out
