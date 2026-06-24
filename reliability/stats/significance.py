"""Paired significance tests for agent A/B comparison.

  * McNemar  -> paired binary pass/fail (did the same cases flip?)
  * Wilcoxon -> paired ordinal/continuous score deltas (non-normal-safe)

Both are exact-where-cheap / well-behaved normal approximations otherwise, and
return a clear two-sided p-value plus the direction of change.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class TestResult:
    name: str
    statistic: float
    p_value: float
    detail: dict

    def as_dict(self) -> dict:
        return {"name": self.name, "statistic": self.statistic, "p_value": self.p_value, **self.detail}


def mcnemar(baseline_pass: list[bool], candidate_pass: list[bool]) -> TestResult:
    """Exact McNemar test on paired pass/fail.

    b = cases the baseline passed but the candidate failed (regressions)
    c = cases the baseline failed but the candidate passed (fixes)
    Exact two-sided binomial p-value over the n = b + c discordant pairs.
    """
    if len(baseline_pass) != len(candidate_pass):
        raise ValueError("paired arrays must be equal length")
    b = sum(1 for a, c in zip(baseline_pass, candidate_pass) if a and not c)
    c = sum(1 for a, cc in zip(baseline_pass, candidate_pass) if not a and cc)
    n = b + c
    if n == 0:
        return TestResult("mcnemar", 0.0, 1.0, {"b_regressions": b, "c_fixes": c, "n_discordant": 0})
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) * (0.5 ** n)
    p = min(1.0, 2.0 * tail)
    return TestResult("mcnemar", float(b - c), float(p),
                      {"b_regressions": b, "c_fixes": c, "n_discordant": n})


def wilcoxon_signed_rank(baseline: list[float], candidate: list[float]) -> TestResult:
    """Wilcoxon signed-rank on paired scores (candidate - baseline).

    Normal approximation with continuity + tie correction. Zero-differences are
    dropped (Wilcoxon convention). Suitable for the small-but-not-tiny n typical
    of eval suites; for n < ~6 treat the p-value as indicative.
    """
    a = np.asarray(baseline, dtype=float)
    b = np.asarray(candidate, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired arrays must be equal length")
    diffs = b - a
    nonzero = diffs[diffs != 0]
    n = nonzero.size
    if n == 0:
        return TestResult("wilcoxon", 0.0, 1.0, {"n": 0, "w_plus": 0.0, "w_minus": 0.0})

    abs_d = np.abs(nonzero)
    order = np.argsort(abs_d, kind="mergesort")
    ranks = np.empty(n, dtype=float)
    sorted_abs = abs_d[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_abs[j + 1] == sorted_abs[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # average of ranks i+1..j+1
        ranks[order[i:j + 1]] = avg_rank
        i = j + 1

    signs = np.sign(nonzero)
    w_plus = float(np.sum(ranks[signs > 0]))
    w_minus = float(np.sum(ranks[signs < 0]))
    w = min(w_plus, w_minus)

    mean_w = n * (n + 1) / 4.0
    # Tie correction for the variance.
    _, counts = np.unique(sorted_abs, return_counts=True)
    tie_term = np.sum(counts**3 - counts)
    var_w = (n * (n + 1) * (2 * n + 1) - tie_term / 2.0) / 24.0
    if var_w <= 0:
        return TestResult("wilcoxon", float(w), 1.0, {"n": n, "w_plus": w_plus, "w_minus": w_minus})
    z = (w - mean_w + 0.5) / math.sqrt(var_w)
    p = min(1.0, 2.0 * _normal_cdf(z))  # z <= 0 since w is the smaller sum
    return TestResult("wilcoxon", float(w), float(p),
                      {"n": n, "w_plus": w_plus, "w_minus": w_minus, "z": float(z)})


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
