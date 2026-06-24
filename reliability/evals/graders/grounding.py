"""Grounding / faithfulness grader.

Every numeric claim in the final answer must trace to evidence — either a tool
result or the user's own question (echoing the user's figures is fine). This is
the guard against invented numbers, the most damaging failure mode for an
analytics agent.

Numeric matching is value-based (normalised, tolerance-compared), not substring,
so "$4,200,000" is correctly flagged when the tools only ever returned ~$1,032.
"""
from __future__ import annotations

import re

from reliability.evals.graders import GraderOutput

_NUM = re.compile(r"-?\$?\s?\d[\d,]*\.?\d*\s?%?")


def extract_numbers(text: str) -> list[float]:
    if not text:
        return []
    out: list[float] = []
    for tok in _NUM.findall(text):
        cleaned = tok.replace("$", "").replace(",", "").replace("%", "").strip()
        if cleaned in ("", "-", "."):
            continue
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def is_supported(value: float, evidence: list[float], rel_tol: float = 1e-3, abs_tol: float = 0.02) -> bool:
    for e in evidence:
        if abs(value - e) <= max(abs_tol, abs(e) * rel_tol):
            return True
    return False


def check_grounding(answer: str, evidence_text: str) -> tuple[float, list[float]]:
    """Shared grounding logic for the grader AND the runtime guard.

    Returns (score in 0..1, list of ungrounded numbers). A number in the answer
    is grounded if it matches (by value, with tolerance) any number in the
    evidence (tool results + the user's own question).
    """
    answer_nums = extract_numbers(answer)
    if not answer_nums:
        return 1.0, []
    evidence_nums = extract_numbers(evidence_text)
    ungrounded = [n for n in answer_nums if not is_supported(n, evidence_nums)]
    score = 1.0 - (len(ungrounded) / len(answer_nums))
    return round(score, 4), ungrounded


class GroundingGrader:
    name = "grounding"

    def score(self, case, trace, ctx) -> GraderOutput:
        answer = trace.final_answer or ""
        evidence_text = f"{trace.tool_outputs_text()}\n{trace.query}"
        score, ungrounded = check_grounding(answer, evidence_text)
        return GraderOutput(
            score,
            {
                "answer_numbers": extract_numbers(answer),
                "ungrounded": ungrounded,
            },
        )
