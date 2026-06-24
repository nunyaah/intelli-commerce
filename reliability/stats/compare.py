"""Paired A/B comparison of two eval runs -> an honest, statistically-grounded
verdict (REGRESSED / IMPROVED / NO CHANGE), per-grader and overall.

The decision rule follows the 2026 consensus: ship/flag on the *delta CI*, not a
single average. A regression is called only when the paired delta CI sits
entirely below zero, or McNemar finds significantly more pass->fail flips than
fail->pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from reliability.stats.bootstrap import CI, paired_delta_ci, wilson_ci
from reliability.stats.significance import TestResult, mcnemar, wilcoxon_signed_rank

REGRESSED = "REGRESSED"
IMPROVED = "IMPROVED"
NO_CHANGE = "NO_CHANGE"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class GraderComparison:
    grader: str
    baseline_mean: float
    candidate_mean: float
    delta: float
    delta_ci: CI
    baseline_pass_rate: float
    candidate_pass_rate: float
    verdict: str


@dataclass
class Comparison:
    n_cases: int
    baseline_label: str
    candidate_label: str
    baseline_pass_rate: float
    candidate_pass_rate: float
    baseline_pass_ci: CI
    candidate_pass_ci: CI
    overall_delta: float
    overall_delta_ci: CI
    mcnemar: TestResult
    wilcoxon: TestResult
    verdict: str
    reasons: list[str] = field(default_factory=list)
    per_grader: list[GraderComparison] = field(default_factory=list)
    cost_delta_usd: float = 0.0
    latency_delta_ms: float = 0.0

    def as_dict(self) -> dict:
        return {
            "n_cases": self.n_cases,
            "baseline_label": self.baseline_label,
            "candidate_label": self.candidate_label,
            "baseline_pass_rate": self.baseline_pass_rate,
            "candidate_pass_rate": self.candidate_pass_rate,
            "baseline_pass_ci": self.baseline_pass_ci.as_dict(),
            "candidate_pass_ci": self.candidate_pass_ci.as_dict(),
            "overall_delta": self.overall_delta,
            "overall_delta_ci": self.overall_delta_ci.as_dict(),
            "mcnemar": self.mcnemar.as_dict(),
            "wilcoxon": self.wilcoxon.as_dict(),
            "verdict": self.verdict,
            "reasons": self.reasons,
            "cost_delta_usd": self.cost_delta_usd,
            "latency_delta_ms": self.latency_delta_ms,
            "per_grader": [
                {
                    "grader": g.grader,
                    "baseline_mean": g.baseline_mean,
                    "candidate_mean": g.candidate_mean,
                    "delta": g.delta,
                    "delta_ci": g.delta_ci.as_dict(),
                    "baseline_pass_rate": g.baseline_pass_rate,
                    "candidate_pass_rate": g.candidate_pass_rate,
                    "verdict": g.verdict,
                }
                for g in self.per_grader
            ],
        }


def _verdict_from_ci(ci: CI, alpha_significant: bool = True) -> str:
    if ci.high < 0:
        return REGRESSED
    if ci.low > 0:
        return IMPROVED
    return NO_CHANGE


def compare_runs(baseline, candidate, alpha: float = 0.05, seed: int = 1234) -> Comparison:
    """``baseline`` / ``candidate`` are RunReport-like objects exposing
    ``.cases`` (dict case_id -> CaseReport) and ``.agent_label``."""
    common = sorted(set(baseline.cases) & set(candidate.cases))
    if not common:
        raise ValueError("no overlapping cases between the two runs")

    b_overall = [baseline.cases[c].overall_score for c in common]
    c_overall = [candidate.cases[c].overall_score for c in common]
    b_pass = [baseline.cases[c].passed for c in common]
    c_pass = [candidate.cases[c].passed for c in common]

    overall_delta = float(np.mean(c_overall) - np.mean(b_overall))
    overall_ci = paired_delta_ci(b_overall, c_overall, seed=seed)
    mc = mcnemar(b_pass, c_pass)
    wx = wilcoxon_signed_rank(b_overall, c_overall)

    b_rate = sum(b_pass) / len(b_pass)
    c_rate = sum(c_pass) / len(c_pass)

    # Per-grader comparisons over the graders present in both runs.
    graders = sorted(
        {g for c in common for g in baseline.cases[c].grader_scores}
        & {g for c in common for g in candidate.cases[c].grader_scores}
    )
    per_grader: list[GraderComparison] = []
    for g in graders:
        # Align on cases scored by both for this grader.
        paired = [
            (baseline.cases[c].grader_scores[g], candidate.cases[c].grader_scores[g])
            for c in common
            if g in baseline.cases[c].grader_scores and g in candidate.cases[c].grader_scores
        ]
        if not paired:
            continue
        gb = [p[0] for p in paired]
        gc = [p[1] for p in paired]
        g_ci = paired_delta_ci(gb, gc, seed=seed) if len(gb) > 1 else CI(float(np.mean(gc) - np.mean(gb)), float("nan"), float("nan"), 0.95)
        bp = [baseline.cases[c].grader_passed.get(g, True) for c in common if g in baseline.cases[c].grader_passed]
        cp = [candidate.cases[c].grader_passed.get(g, True) for c in common if g in candidate.cases[c].grader_passed]
        per_grader.append(
            GraderComparison(
                grader=g,
                baseline_mean=round(float(np.mean(gb)), 4),
                candidate_mean=round(float(np.mean(gc)), 4),
                delta=round(float(np.mean(gc) - np.mean(gb)), 4),
                delta_ci=g_ci,
                baseline_pass_rate=round(sum(bp) / len(bp), 4) if bp else 1.0,
                candidate_pass_rate=round(sum(cp) / len(cp), 4) if cp else 1.0,
                verdict=_verdict_from_ci(g_ci),
            )
        )

    # --- overall verdict ----------------------------------------------------
    reasons: list[str] = []
    verdict = NO_CHANGE
    if overall_ci.high < 0:
        verdict = REGRESSED
        reasons.append(
            f"Overall quality delta CI {_fmt(overall_ci)} is entirely below zero "
            f"(mean {overall_delta:+.3f})."
        )
    elif mc.p_value < alpha and mc.detail["b_regressions"] > mc.detail["c_fixes"]:
        verdict = REGRESSED
        reasons.append(
            f"McNemar significant (p={mc.p_value:.3g}) with {mc.detail['b_regressions']} "
            f"pass->fail vs {mc.detail['c_fixes']} fail->pass flips."
        )
    elif overall_ci.low > 0:
        verdict = IMPROVED
        reasons.append(f"Overall quality delta CI {_fmt(overall_ci)} is entirely above zero.")
    elif mc.p_value < alpha and mc.detail["c_fixes"] > mc.detail["b_regressions"]:
        verdict = IMPROVED
        reasons.append(
            f"McNemar significant (p={mc.p_value:.3g}) with more fixes than regressions."
        )
    else:
        reasons.append(
            f"No significant change: delta CI {_fmt(overall_ci)} straddles zero "
            f"(McNemar p={mc.p_value:.3g})."
        )

    # Flag any individual grader whose CI is entirely below zero, even if overall held.
    for g in per_grader:
        if g.verdict == REGRESSED and verdict != REGRESSED:
            reasons.append(f"Grader '{g.grader}' regressed (delta CI {_fmt(g.delta_ci)}).")

    return Comparison(
        n_cases=len(common),
        baseline_label=getattr(baseline, "agent_label", "baseline"),
        candidate_label=getattr(candidate, "agent_label", "candidate"),
        baseline_pass_rate=round(b_rate, 4),
        candidate_pass_rate=round(c_rate, 4),
        baseline_pass_ci=wilson_ci(sum(b_pass), len(b_pass)),
        candidate_pass_ci=wilson_ci(sum(c_pass), len(c_pass)),
        overall_delta=round(overall_delta, 4),
        overall_delta_ci=overall_ci,
        mcnemar=mc,
        wilcoxon=wx,
        verdict=verdict,
        reasons=reasons,
        per_grader=per_grader,
        cost_delta_usd=round(
            getattr(candidate, "total_cost", 0.0) - getattr(baseline, "total_cost", 0.0), 8
        ),
        latency_delta_ms=round(
            getattr(candidate, "avg_latency_ms", 0.0) - getattr(baseline, "avg_latency_ms", 0.0), 2
        ),
    )


def _fmt(ci: CI) -> str:
    return f"[{ci.low:+.3f}, {ci.high:+.3f}]"
