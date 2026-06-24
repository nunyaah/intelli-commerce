"""Baseline persistence: a frozen eval run the gate compares new runs against."""
from __future__ import annotations

import json
import os
from typing import Optional

from reliability.evals.report import CaseReport, RunReport

DEFAULT_BASELINE = os.path.join(".reliability", "baseline.json")


def save_baseline(report: RunReport, path: str = DEFAULT_BASELINE) -> str:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    payload = {
        "run_id": report.run_id,
        "dataset_version": report.dataset_version,
        "agent_label": report.agent_label,
        "agent_version": report.agent_version,
        "mode": report.mode,
        "seed": report.seed,
        "summary": report.summary(),
        "cases": {
            cid: {
                "case_id": c.case_id,
                "trace_id": c.trace_id,
                "query": c.query,
                "overall_score": c.overall_score,
                "passed": c.passed,
                "grader_scores": c.grader_scores,
                "grader_passed": c.grader_passed,
                "difficulty": c.difficulty,
                "tags": c.tags,
                "cost_usd": c.cost_usd,
                "latency_ms": c.latency_ms,
            }
            for cid, c in report.cases.items()
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def load_baseline(path: str = DEFAULT_BASELINE) -> Optional[RunReport]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    report = RunReport(
        run_id=payload.get("run_id", "baseline"),
        dataset_version=payload.get("dataset_version", "0.0.0"),
        agent_label=payload.get("agent_label", "baseline"),
        agent_version=payload.get("agent_version", {}),
        mode=payload.get("mode", "offline"),
        seed=payload.get("seed", 0),
    )
    for cid, c in payload.get("cases", {}).items():
        report.cases[cid] = CaseReport(
            case_id=c["case_id"],
            trace_id=c.get("trace_id", ""),
            query=c.get("query", ""),
            overall_score=c["overall_score"],
            passed=c["passed"],
            grader_scores=c.get("grader_scores", {}),
            grader_passed=c.get("grader_passed", {}),
            difficulty=c.get("difficulty", "medium"),
            tags=c.get("tags", []),
            cost_usd=c.get("cost_usd", 0.0),
            latency_ms=c.get("latency_ms", 0.0),
        )
    return report
