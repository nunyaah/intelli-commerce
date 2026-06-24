"""Did the agent call the right tool(s), in a sensible order?"""
from __future__ import annotations

from reliability.evals.graders import GraderOutput


class ToolSelectionGrader:
    name = "tool_selection"

    def score(self, case, trace, ctx) -> GraderOutput:
        expected = case.expected.get("tools", [])
        mode = case.expected.get("tools_mode", "contains")
        called = trace.tool_names()

        if not expected:
            # Nothing required; full marks unless an error occurred.
            return GraderOutput(1.0, {"called": called, "note": "no tool requirement"})

        called_set = set(called)
        expected_set = set(expected)
        unexpected = [t for t in called if t not in expected_set]

        if mode == "exact":
            score = 1.0 if called_set == expected_set else 0.0
        elif mode == "ordered":
            score = 1.0 if _is_subsequence(expected, called) else 0.0
        else:  # contains
            hit = len(expected_set & called_set)
            score = hit / len(expected_set)

        return GraderOutput(
            round(score, 4),
            {
                "expected": expected,
                "mode": mode,
                "called": called,
                "missing": sorted(expected_set - called_set),
                "unexpected": unexpected,
            },
        )


def _is_subsequence(expected: list, called: list) -> bool:
    it = iter(called)
    return all(any(e == c for c in it) for e in expected)
