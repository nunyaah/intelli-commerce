"""Statistical rigor for honest A/B verdicts.

Implemented from first principles in numpy (no scipy) so the logic is auditable
and unit-tested. Follows 2026 eval-statistics practice: paired bootstrap CIs on
the per-case delta, McNemar for paired pass/fail, Wilcoxon signed-rank for
ordinal score deltas. Ship a change only when the delta CI sits entirely on one
side of zero.
"""
