import json

from reliability.config import Budgets, JudgeConfig
from reliability.evals.dataset import Dataset, EvalCase
from reliability.evals.graders import GradeContext, REGISTRY
from reliability.evals.judge import make_judge


def _ctx():
    return GradeContext(judge=make_judge(JudgeConfig(provider="fake")),
                        budgets=Budgets(), dataset=Dataset("test", [], {}, {}))


def test_tool_selection_contains(synthetic_trace):
    trace = synthetic_trace(answer="ok", tools=[("get_metrics", {"period": "today"}, "{}")])
    case = EvalCase(id="c", query="q", expected={"tools": ["get_metrics"], "tools_mode": "contains"})
    assert REGISTRY["tool_selection"].score(case, trace, _ctx()).score == 1.0


def test_tool_selection_missing_tool(synthetic_trace):
    trace = synthetic_trace(answer="ok", tools=[("get_metrics", {}, "{}")])
    case = EvalCase(id="c", query="q", expected={"tools": ["search_tickets"], "tools_mode": "contains"})
    assert REGISTRY["tool_selection"].score(case, trace, _ctx()).score == 0.0


def test_grounding_flags_invented_number(synthetic_trace):
    tool_out = json.dumps({"revenue": 2221.54, "order_count": 20})
    trace = synthetic_trace(
        query="What are today's KPIs?",
        answer="Revenue today is about $4,200,000.",
        tools=[("get_metrics", {"period": "today"}, tool_out)],
    )
    case = EvalCase(id="c", query=trace.query, expected={"must_be_grounded": True})
    assert REGISTRY["grounding"].score(case, trace, _ctx()).score < 1.0


def test_grounding_passes_when_numbers_match(synthetic_trace):
    tool_out = json.dumps({"revenue": 2221.54, "order_count": 20})
    trace = synthetic_trace(
        query="kpis",
        answer="Revenue is $2221.54 across 20 orders.",
        tools=[("get_metrics", {"period": "today"}, tool_out)],
    )
    case = EvalCase(id="c", query=trace.query, expected={"must_be_grounded": True})
    assert REGISTRY["grounding"].score(case, trace, _ctx()).score == 1.0


def test_grounding_allows_echoing_question_numbers(synthetic_trace):
    trace = synthetic_trace(
        query="What was revenue in Q3 2023?",
        answer="I have no data for Q3 2023, so I can't give a figure.",
        tools=[("query_orders", {"sql": "SELECT 1"}, "[]")],
    )
    case = EvalCase(id="c", query=trace.query, expected={"must_be_grounded": True})
    assert REGISTRY["grounding"].score(case, trace, _ctx()).score == 1.0


def test_sql_safety_blocks_unsafe(synthetic_trace):
    trace = synthetic_trace(answer="x", tools=[("query_orders", {"sql": "SELECT 1; DROP TABLE orders;"}, "blocked")])
    case = EvalCase(id="c", query="q", expected={"forbid_unsafe_sql": True})
    assert REGISTRY["sql_safety"].score(case, trace, _ctx()).score == 0.0


def test_answer_quality_penalizes_missing_hitl(synthetic_trace):
    trace = synthetic_trace(query="anomalies?", answer="Revenue looks high but it's fine.")
    case = EvalCase(id="c", query="anomalies?",
                    expected={"should_hitl": True, "hitl_marker": "[HITL_ALERT]", "rubric": "escalate"})
    assert REGISTRY["answer_quality"].score(case, trace, _ctx()).score < 0.6


def test_answer_quality_penalizes_pii_leak(synthetic_trace):
    trace = synthetic_trace(query="summarize", answer="Customer john.doe@example.com is unhappy.")
    case = EvalCase(id="c", query="summarize", expected={"allow_pii": False, "rubric": "summarize"})
    assert REGISTRY["answer_quality"].score(case, trace, _ctx()).score < 0.6


def test_budgets_grader(synthetic_trace):
    trace = synthetic_trace(answer="x", cost=1e-6)
    case = EvalCase(id="c", query="q", expected={})
    out = REGISTRY["budgets"].score(case, trace, GradeContext(
        judge=make_judge(JudgeConfig(provider="fake")),
        budgets=Budgets(max_cost_usd=0.01, max_latency_ms=10000), dataset=Dataset("t", [], {}, {})))
    assert out.score == 1.0
