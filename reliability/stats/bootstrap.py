"""Bootstrap confidence intervals."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CI:
    point: float
    low: float
    high: float
    level: float

    def as_dict(self) -> dict:
        return {"point": self.point, "low": self.low, "high": self.high, "level": self.level}

    @property
    def excludes_zero(self) -> bool:
        return self.low > 0 or self.high < 0


def bootstrap_ci(
    values, statistic=np.mean, n_resamples: int = 10000, level: float = 0.95, seed: int = 1234
) -> CI:
    """Percentile bootstrap CI for an arbitrary statistic of one sample."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return CI(float("nan"), float("nan"), float("nan"), level)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(n_resamples, arr.size))
    stats = statistic(arr[idx], axis=1)
    alpha = (1.0 - level) / 2.0
    lo, hi = np.quantile(stats, [alpha, 1.0 - alpha])
    return CI(float(statistic(arr)), float(lo), float(hi), level)


def paired_delta_ci(
    baseline, candidate, n_resamples: int = 10000, level: float = 0.95, seed: int = 1234
) -> CI:
    """Bootstrap CI for mean(candidate) - mean(baseline) on PAIRED samples.

    Resamples item indices (not the two arms independently) so instance-level
    correlation is preserved — the correct procedure for regression testing.
    """
    a = np.asarray(baseline, dtype=float)
    b = np.asarray(candidate, dtype=float)
    if a.shape != b.shape or a.size == 0:
        raise ValueError("paired_delta_ci requires two equal-length non-empty samples")
    diffs = b - a
    return bootstrap_ci(diffs, statistic=np.mean, n_resamples=n_resamples, level=level, seed=seed)


def wilson_ci(successes: int, n: int, level: float = 0.95) -> CI:
    """Wilson score interval for a proportion (better than normal at the edges)."""
    if n == 0:
        return CI(float("nan"), float("nan"), float("nan"), level)
    # z for two-sided level; common values without scipy.
    z = {0.90: 1.6449, 0.95: 1.9600, 0.99: 2.5758}.get(round(level, 2), 1.9600)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return CI(float(p), float(max(0.0, centre - half)), float(min(1.0, centre + half)), level)
