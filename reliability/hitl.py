"""Closed-loop HITL: review a real trace, label the expected behaviour, and feed
the corrected label back into the versioned eval dataset.

This turns human review into durable test coverage — the queue stops being
write-only and every review makes future evals stronger.
"""
from __future__ import annotations

import re
from typing import Optional

from reliability import store
from reliability.evals.dataset import DEFAULT_DATASET, append_cases
from reliability.store import load_trace


def _slug(text: str, n: int = 28) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s[:n] or "case"


def suggest_expected(trace) -> dict:
    """Seed an expectation from observed behaviour for the reviewer to correct."""
    tools = list(dict.fromkeys(trace.tool_names()))
    expected = {
        "tools": tools,
        "tools_mode": "contains",
        "must_be_grounded": True,
        "rubric": f"Correctly and faithfully answers: {trace.query}",
    }
    if any(t == "query_orders" for t in tools):
        expected["forbid_unsafe_sql"] = True
    return expected


def create_label_from_trace(trace_id: str) -> Optional[int]:
    trace = load_trace(trace_id)
    if trace is None:
        return None
    return store.create_label(trace_id, trace.query, suggest_expected(trace))


def _graders_for(expected: dict) -> list[str]:
    graders = []
    if expected.get("tools"):
        graders.append("tool_selection")
    if expected.get("must_be_grounded"):
        graders.append("grounding")
    if expected.get("forbid_unsafe_sql"):
        graders.append("sql_safety")
    graders += ["answer_quality", "budgets"]
    # de-dup, preserve order
    return list(dict.fromkeys(graders))


def label_to_case(label: dict) -> dict:
    expected = label.get("expected", {})
    return {
        "id": f"hitl_{_slug(label['query'])}_{label['id']}",
        "query": label["query"],
        "difficulty": "review",
        "tags": ["hitl", "human-labeled"],
        "graders": _graders_for(expected),
        "expected": expected,
    }


def export_labeled(dataset_path: str = DEFAULT_DATASET, bump: str = "minor") -> dict:
    """Append all labeled-but-not-exported reviews to the dataset and bump version."""
    labels = [lb for lb in store.list_labels(status="labeled") if not lb.get("exported")]
    if not labels:
        return {"added": 0, "version": None, "cases": []}
    cases = [label_to_case(lb) for lb in labels]
    version = append_cases(cases, dataset_path, bump=bump)
    store.mark_labels_exported([lb["id"] for lb in labels])
    return {"added": len(cases), "version": version, "cases": [c["id"] for c in cases]}
