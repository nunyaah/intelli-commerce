"""Reliability dashboard API: traces, evals, guardrails, and the HITL labeling
loop — all backed by the real reliability store (never hardcoded).
"""
import sys

sys.path.insert(0, "/app")

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from reliability import store
from reliability import hitl
from reliability.stats.compare import compare_runs
from reliability.evals.report import CaseReport, RunReport

router = APIRouter()


# --- Traces ------------------------------------------------------------------
@router.get("/traces")
def list_traces(limit: int = 100, source: str | None = None):
    return store.list_traces(limit=limit, source=source)


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    trace = store.load_trace(trace_id)
    if trace is None:
        raise HTTPException(404, "trace not found")
    return trace.to_dict()


# --- Evals -------------------------------------------------------------------
@router.get("/evals/runs")
def list_eval_runs(limit: int = 50):
    return store.list_eval_runs(limit=limit)


@router.get("/evals/runs/{run_id}")
def get_eval_run(run_id: str):
    run = store.get_eval_run(run_id)
    if run is None:
        raise HTTPException(404, "eval run not found")
    return run


def _run_to_report(run: dict) -> RunReport:
    """Reconstruct a RunReport from stored eval_results for statistical compare."""
    report = RunReport(
        run_id=run["id"], dataset_version=run["dataset_version"],
        agent_label=run["agent_label"], agent_version=run["agent_version"],
        mode=run["mode"], seed=run["seed"],
    )
    by_case: dict[str, dict] = {}
    for r in run["results"]:
        c = by_case.setdefault(r["case_id"], {"scores": {}, "passed": {}, "trace_id": r["trace_id"]})
        c["scores"][r["grader"]] = r["score"]
        c["passed"][r["grader"]] = bool(r["passed"])
    for cid, c in by_case.items():
        # Weighted overall is recomputed simply (mean) for compare display.
        scores = list(c["scores"].values())
        overall = round(sum(scores) / len(scores), 4) if scores else 0.0
        report.cases[cid] = CaseReport(
            case_id=cid, trace_id=c["trace_id"], query="", overall_score=overall,
            passed=all(c["passed"].values()) if c["passed"] else False,
            grader_scores=c["scores"], grader_passed=c["passed"],
        )
    return report


@router.get("/evals/compare")
def compare(baseline: str, candidate: str):
    b = store.get_eval_run(baseline)
    c = store.get_eval_run(candidate)
    if b is None or c is None:
        raise HTTPException(404, "baseline or candidate run not found")
    cmp = compare_runs(_run_to_report(b), _run_to_report(c))
    return cmp.as_dict()


# --- Guardrails --------------------------------------------------------------
@router.get("/guardrails/events")
def guardrail_events(limit: int = 100):
    return store.list_guardrail_events(limit=limit)


# --- HITL labeling loop ------------------------------------------------------
class CreateLabelBody(BaseModel):
    trace_id: str


class UpdateLabelBody(BaseModel):
    expected: dict
    label_status: str = "labeled"  # labeled | rejected
    labeled_by: str = "reviewer"
    note: str = ""


@router.get("/labels")
def list_labels(status: str | None = None):
    return store.list_labels(status=status)


@router.post("/labels")
def create_label(body: CreateLabelBody):
    label_id = hitl.create_label_from_trace(body.trace_id)
    if label_id is None:
        raise HTTPException(404, "trace not found")
    return {"id": label_id}


@router.put("/labels/{label_id}")
def update_label(label_id: int, body: UpdateLabelBody):
    store.update_label(label_id, body.expected, body.label_status, body.labeled_by, body.note)
    return {"status": "ok", "id": label_id}


@router.post("/labels/export")
def export_labels():
    return hitl.export_labeled()
