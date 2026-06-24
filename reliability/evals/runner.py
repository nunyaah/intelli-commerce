"""Offline eval runner.

Drives the *real* agent over the versioned dataset, grades each run, computes a
weighted overall score + pass/fail per case, and persists everything to the
store. Reproducible: builds a deterministic fixture DB, records the agent
version + seed, and (in mock mode) is fully deterministic and free.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional


from reliability.agent_harness.runner import run_agent
from reliability.config import AgentConfig, Budgets, JudgeConfig
from reliability.data.fixtures import build_fixture_db
from reliability.evals.dataset import Dataset, EvalCase, load_dataset
from reliability.evals.graders import GradeContext, grade_case
from reliability.evals.judge import make_judge
from reliability.evals.report import CaseReport, RunReport
from reliability import store


def _weighted_overall(grades, dataset: Dataset, case: EvalCase) -> float:
    if not grades:
        return 0.0
    num = sum(g.score * g.weight for g in grades)
    den = sum(g.weight for g in grades)
    return round(num / den, 4) if den else 0.0


def run_eval(
    agent_cfg: Optional[AgentConfig] = None,
    judge_cfg: Optional[JudgeConfig] = None,
    budgets: Optional[Budgets] = None,
    dataset_path: Optional[str] = None,
    mode: str = "offline",
    repeats: int = 1,
    seed: int = 1234,
    use_fixture: bool = True,
    persist: bool = True,
    case_ids: Optional[list[str]] = None,
) -> RunReport:
    agent_cfg = agent_cfg or AgentConfig()
    judge_cfg = judge_cfg or JudgeConfig()
    budgets = budgets or Budgets()
    dataset = load_dataset(dataset_path) if dataset_path else load_dataset()
    judge = make_judge(judge_cfg)

    if use_fixture:
        # Point the agent at a fresh deterministic DB for this run.
        fixture_path = os.path.join(".reliability", f"fixture_{seed}.db")
        build_fixture_db(fixture_path)
        os.environ["DB_PATH"] = os.path.abspath(fixture_path)

    if persist:
        store.init_store()

    run_id = uuid.uuid4().hex[:12]
    report = RunReport(
        run_id=run_id,
        dataset_version=dataset.version,
        agent_label=agent_cfg.label(),
        agent_version=agent_cfg.version_dict(),
        mode=mode,
        seed=seed,
    )
    ctx = GradeContext(judge=judge, budgets=budgets, dataset=dataset)

    selected = [c for c in dataset.cases if (case_ids is None or c.id in case_ids)]
    for case in selected:
        for r in range(max(1, repeats)):
            cid = case.id if repeats == 1 else f"{case.id}#{r}"
            thread_id = f"{run_id}-{cid}"
            trace = run_agent(case.query, cfg=agent_cfg, thread_id=thread_id,
                              source="eval", persist=persist)
            grades = grade_case(case, trace, ctx)
            overall = _weighted_overall(grades, dataset, case)
            passed = all(g.passed for g in grades) if grades else False

            report.cases[cid] = CaseReport(
                case_id=cid,
                trace_id=trace.trace_id,
                query=case.query,
                overall_score=overall,
                passed=passed,
                grader_scores={g.grader: g.score for g in grades},
                grader_passed={g.grader: g.passed for g in grades},
                grader_details={g.grader: g.details for g in grades},
                difficulty=case.difficulty,
                tags=case.tags,
                cost_usd=trace.total_cost_usd,
                latency_ms=trace.duration_ms,
                error=trace.error,
            )

            if persist:
                for g in grades:
                    store.save_eval_result(
                        eval_run_id=run_id, case_id=cid, trace_id=trace.trace_id,
                        grader=g.grader, score=g.score, passed=g.passed,
                        weight=g.weight, details=g.details,
                    )

    if persist:
        store.save_eval_run(
            run_id=run_id,
            dataset_version=dataset.version,
            agent_version=agent_cfg.version_dict(),
            agent_label=agent_cfg.label(),
            mode=mode,
            seed=seed,
            num_cases=len(report.cases),
            config={
                "judge": judge_cfg.__dict__,
                "budgets": budgets.as_dict(),
                "repeats": repeats,
            },
            summary=report.summary(),
        )

    return report
