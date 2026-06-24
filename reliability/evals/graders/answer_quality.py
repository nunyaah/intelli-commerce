"""Answer-quality grader (LLM-as-judge against the case rubric)."""
from __future__ import annotations

from reliability.evals.graders import GraderOutput


class AnswerQualityGrader:
    name = "answer_quality"

    def score(self, case, trace, ctx) -> GraderOutput:
        rubric = case.expected.get("rubric", "The answer correctly and helpfully addresses the question.")
        verdict = ctx.judge.score(
            query=case.query,
            answer=trace.final_answer or "",
            rubric=rubric,
            evidence=trace.tool_outputs_text(),
            expected=case.expected,
        )
        return GraderOutput(
            round(verdict.score, 4),
            {"reasoning": verdict.reasoning, "backend": verdict.backend, "rubric": rubric},
        )
