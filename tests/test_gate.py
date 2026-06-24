"""End-to-end gate tests: the healthy agent passes, the degraded agent is caught.
Runs the real LangGraph agent in deterministic mock mode (free)."""
from reliability.config import AgentConfig, Budgets, JudgeConfig
from reliability.evals.runner import run_eval
from reliability.gate.gate import run_gate


def _agent(variant):
    return AgentConfig(provider="fake", variant=variant)


def _judge():
    return JudgeConfig(provider="fake")


def test_base_agent_passes_gate():
    base = run_eval(_agent("base"), _judge(), Budgets(), persist=False)
    assert base.pass_rate >= 0.9
    result = run_gate(base, baseline=None, min_pass_rate=0.8)
    assert result.passed
    assert result.exit_code == 0


def test_degraded_agent_fails_gate():
    base = run_eval(_agent("base"), _judge(), Budgets(), persist=False)
    degraded = run_eval(_agent("degraded"), _judge(), Budgets(), persist=False)

    assert degraded.pass_rate < base.pass_rate
    result = run_gate(degraded, baseline=base, min_pass_rate=0.8)
    assert not result.passed
    assert result.exit_code == 1
    assert result.comparison is not None
    assert result.comparison.verdict == "REGRESSED"
    # The delta CI must sit entirely below zero — an honest, not arbitrary, call.
    assert result.comparison.overall_delta_ci.high < 0


def test_reproducible_same_inputs_same_verdict():
    a = run_eval(_agent("degraded"), _judge(), Budgets(), persist=False, seed=7)
    b = run_eval(_agent("degraded"), _judge(), Budgets(), persist=False, seed=7)
    assert a.summary()["pass_rate"] == b.summary()["pass_rate"]
    assert a.summary()["grader_means"] == b.summary()["grader_means"]
