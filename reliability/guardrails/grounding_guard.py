"""Runtime grounding/hallucination check, run before an answer is returned.

Reuses the exact logic of the grounding grader so "what we test offline" and
"what we enforce at runtime" are identical. Flags numeric claims in the answer
that aren't supported by the tool results gathered during the run.
"""
from __future__ import annotations

from dataclasses import dataclass

from reliability.evals.graders.grounding import check_grounding


@dataclass
class GroundingVerdict:
    grounded: bool
    score: float
    ungrounded: list[float]


def check(answer: str, evidence_text: str, threshold: float = 0.999) -> GroundingVerdict:
    score, ungrounded = check_grounding(answer, evidence_text)
    return GroundingVerdict(grounded=score >= threshold, score=score, ungrounded=ungrounded)
