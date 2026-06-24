"""Dataset, fixtures, fake-LLM scripting, and HITL loop integration."""
from reliability.config import AgentConfig, Budgets, JudgeConfig
from reliability.evals.dataset import load_dataset
from reliability.evals.runner import run_eval


def test_dataset_loads_and_is_versioned():
    ds = load_dataset()
    assert ds.version
    assert len(ds.cases) >= 8
    ids = [c.id for c in ds.cases]
    assert "anomalies_revenue" in ids and "q3_2023" in ids


def test_base_run_metrics_are_grounded():
    report = run_eval(AgentConfig(provider="fake", variant="base"),
                      JudgeConfig(provider="fake"), Budgets(), persist=False)
    kpi = report.cases["kpis_today"]
    assert kpi.passed
    assert kpi.grader_scores["grounding"] == 1.0
    assert kpi.grader_scores["tool_selection"] == 1.0


def test_anomaly_case_triggers_hitl_marker():
    report = run_eval(AgentConfig(provider="fake", variant="base"),
                      JudgeConfig(provider="fake"), Budgets(), persist=False)
    anomaly = report.cases["anomalies_revenue"]
    assert anomaly.passed  # base agent escalates with [HITL_ALERT]


def test_degraded_unsafe_sql_is_blocked():
    report = run_eval(AgentConfig(provider="fake", variant="degraded"),
                      JudgeConfig(provider="fake"), Budgets(), persist=False)
    top = report.cases["top_products"]
    # The degraded agent emits stacked-query SQL; sql_safety must fail it.
    assert top.grader_scores.get("sql_safety", 1.0) == 0.0


def test_hitl_label_export_appends_and_bumps_version(tmp_path):
    import shutil

    from reliability import hitl, store
    from reliability.evals.dataset import DEFAULT_DATASET, load_dataset

    ds_copy = tmp_path / "ds.yaml"
    shutil.copy(DEFAULT_DATASET, ds_copy)
    before = load_dataset(str(ds_copy))

    lid = store.create_label(None, "Test labeled query", {"tools": ["get_metrics"], "must_be_grounded": True})
    store.update_label(lid, {"tools": ["get_metrics"], "must_be_grounded": True, "rubric": "x"},
                       "labeled", "tester")
    res = hitl.export_labeled(dataset_path=str(ds_copy))
    after = load_dataset(str(ds_copy))

    assert res["added"] == 1
    assert len(after.cases) == len(before.cases) + 1
    assert after.version != before.version
