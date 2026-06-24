"""Versioned eval dataset loading + append (used by the HITL feedback loop)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DEFAULT_DATASET = os.path.join(_DATA_DIR, "dataset_v1.yaml")


@dataclass
class EvalCase:
    id: str
    query: str
    difficulty: str = "medium"
    tags: list[str] = field(default_factory=list)
    graders: list[str] = field(default_factory=list)
    expected: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)


@dataclass
class Dataset:
    version: str
    cases: list[EvalCase]
    thresholds: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)
    path: Optional[str] = None

    def threshold_for(self, grader: str, case: EvalCase) -> float:
        if grader in case.thresholds:
            return float(case.thresholds[grader])
        return float(self.thresholds.get(grader, 0.5))

    def weight_for(self, grader: str) -> float:
        return float(self.weights.get(grader, 1.0))


def load_dataset(path: str = DEFAULT_DATASET) -> Dataset:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    grading = raw.get("grading", {})
    cases = [
        EvalCase(
            id=c["id"],
            query=c["query"],
            difficulty=c.get("difficulty", "medium"),
            tags=c.get("tags", []),
            graders=c.get("graders", []),
            expected=c.get("expected", {}),
            thresholds=c.get("thresholds", {}),
        )
        for c in raw.get("cases", [])
    ]
    return Dataset(
        version=raw.get("version", "0.0.0"),
        cases=cases,
        thresholds=grading.get("thresholds", {}),
        weights=grading.get("weights", {}),
        path=path,
    )


def append_cases(new_cases: list[dict], path: str = DEFAULT_DATASET, bump: str = "patch") -> str:
    """Append human-labeled cases (from the HITL loop) and bump the version."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    existing_ids = {c["id"] for c in raw.get("cases", [])}
    added = 0
    for c in new_cases:
        if c["id"] in existing_ids:
            continue
        raw.setdefault("cases", []).append(c)
        existing_ids.add(c["id"])
        added += 1
    if added:
        raw["version"] = _bump_version(raw.get("version", "1.0.0"), bump)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f, sort_keys=False, allow_unicode=True)
    return raw["version"]


def _bump_version(version: str, part: str) -> str:
    try:
        major, minor, patch = (int(x) for x in version.split("."))
    except ValueError:
        return "1.0.1"
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"
