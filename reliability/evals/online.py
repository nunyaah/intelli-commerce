"""Online evaluation: sample live production traces and score them.

Unlike offline eval (fixed dataset, known expectations), online scoring runs the
*reference-free* graders — grounding, SQL-safety, budgets — over real captured
traces, plus a rubric-free answer-quality judge. This catches drift in
production without a labelled expectation for every query.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from reliability.config import Budgets, JudgeConfig
from reliability.evals.graders.budgets import BudgetsGrader
from reliability.evals.graders.grounding import GroundingGrader
from reliability.evals.graders.sql_safety import SqlSafetyGrader
from reliability.evals.dataset import EvalCase
from reliability.evals.judge import make_judge
from reliability.evals.graders import GradeContext
from reliability.evals.dataset import Dataset
from reliability import store
from reliability.store import list_traces, load_trace

_ONLINE_GRADERS = [GroundingGrader(), SqlSafetyGrader(), BudgetsGrader()]


def sample_and_score(
    sample_size: int = 20,
    fraction: float = 1.0,
    seed: int = 1234,
    budgets: Optional[Budgets] = None,
    judge_cfg: Optional[JudgeConfig] = None,
    persist: bool = True,
) -> dict:
    """Sample recent live traces, score them, and persist an online eval run."""
    budgets = budgets or Budgets()
    judge = make_judge(judge_cfg or JudgeConfig())
    rng = random.Random(seed)

    headers = list_traces(limit=max(sample_size * 3, sample_size), source="live")
    if fraction < 1.0:
        headers = [h for h in headers if rng.random() < fraction]
    headers = headers[:sample_size]

    ctx = GradeContext(judge=judge, budgets=budgets, dataset=Dataset("online", [], {}, {}))
    run_id = "online_" + uuid.uuid4().hex[:10]
    scored = []

    for h in headers:
        trace = load_trace(h["trace_id"])
        if trace is None:
            continue
        # Reference-free case: no expected tools, grounding + safety only.
        case = EvalCase(
            id=trace.trace_id, query=trace.query, difficulty="online",
            graders=["grounding", "sql_safety", "budgets"],
            expected={"must_be_grounded": True},
        )
        per_grader = {}
        for grader in _ONLINE_GRADERS:
            res = grader.score(case, trace, ctx)
            per_grader[grader.name] = res.score
            if persist:
                store.save_eval_result(
                    eval_run_id=run_id, case_id=trace.trace_id, trace_id=trace.trace_id,
                    grader=grader.name, score=res.score,
                    passed=res.score >= 0.999, weight=1.0, details=res.details,
                )
        scored.append({"trace_id": trace.trace_id, "query": trace.query, "scores": per_grader})

    summary = _summarize(scored)
    if persist and scored:
        store.save_eval_run(
            run_id=run_id, dataset_version="online", agent_version={}, agent_label="online-sample",
            mode="online", seed=seed, num_cases=len(scored),
            config={"sample_size": sample_size, "fraction": fraction}, summary=summary,
        )
    return {"run_id": run_id, "num_scored": len(scored), "summary": summary, "scored": scored}


def _summarize(scored: list[dict]) -> dict:
    if not scored:
        return {"num_scored": 0}
    graders = {g for s in scored for g in s["scores"]}
    means = {
        g: round(sum(s["scores"].get(g, 0.0) for s in scored) / len(scored), 4) for g in graders
    }
    return {"num_scored": len(scored), "grader_means": means}
