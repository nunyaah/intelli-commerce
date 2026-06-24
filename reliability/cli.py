"""IntelliCommerce Reliability Suite — command line.

One tool to run the agent, capture traces, evaluate, compare versions with honest
statistics, and gate CI.

Examples:
    python -m reliability.cli eval --mock
    python -m reliability.cli baseline --mock                 # freeze a baseline
    python -m reliability.cli gate --mock --variant degraded  # red on regression
    python -m reliability.cli compare --mock --variant degraded
    python -m reliability.cli online --sample 20
    python -m reliability.cli demo                            # scripted "break it"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from reliability.config import AgentConfig, Budgets, JudgeConfig


# --- pretty printing ---------------------------------------------------------
def _c(text: str, code: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def green(t): return _c(t, "32")
def red(t): return _c(t, "31")
def yellow(t): return _c(t, "33")
def bold(t): return _c(t, "1")
def dim(t): return _c(t, "2")


def _build_configs(args) -> tuple[AgentConfig, JudgeConfig, Budgets]:
    mock = args.mock or os.environ.get("RELIABILITY_MOCK") == "1"
    provider = "fake" if mock else args.provider
    system_prompt = AgentConfig().system_prompt
    if getattr(args, "system_prompt_file", None):
        with open(args.system_prompt_file, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    agent_cfg = AgentConfig(
        provider=provider,
        model=args.model,
        temperature=args.temperature,
        system_prompt=system_prompt,
        variant=args.variant,
        seed=args.seed,
    )
    judge_cfg = JudgeConfig(provider="fake" if mock else args.judge_provider, model=args.judge_model)
    budgets = Budgets(max_cost_usd=args.max_cost, max_latency_ms=args.max_latency)
    return agent_cfg, judge_cfg, budgets


def _print_summary(report) -> None:
    s = report.summary()
    print(bold(f"\nEval run {report.run_id}  ·  agent={report.agent_label}  ·  dataset v{report.dataset_version}"))
    print(f"  cases            : {s['num_cases']}  (passed {s['num_passed']})")
    rate = s["pass_rate"]
    rate_str = f"{rate:.1%}"
    print(f"  pass-rate        : {green(rate_str) if rate >= 0.8 else red(rate_str)}")
    print(f"  mean quality     : {s['mean_overall_score']:.3f}")
    print(f"  total cost (USD) : ${s['total_cost_usd']:.6f}")
    print(f"  avg latency (ms) : {s['avg_latency_ms']:.0f}")
    print(dim("  grader pass-rates:"))
    for g, r in sorted(s["grader_pass_rates"].items()):
        mark = green("ok") if r >= 0.9 else (yellow("warn") if r >= 0.6 else red("LOW"))
        print(dim(f"    {g:<16} {r:>6.1%}  {mark}"))


def _print_per_case(report) -> None:
    print(dim("  per-case:"))
    for cid, c in report.cases.items():
        mark = green("PASS") if c.passed else red("FAIL")
        fails = [g for g, p in c.grader_passed.items() if not p]
        extra = dim(f"  (failed: {', '.join(fails)})") if fails else ""
        print(f"    {mark}  {cid:<22} q={c.overall_score:.2f}{extra}")


# --- commands ----------------------------------------------------------------
def cmd_eval(args) -> int:
    from reliability.evals.runner import run_eval

    agent_cfg, judge_cfg, budgets = _build_configs(args)
    report = run_eval(agent_cfg, judge_cfg, budgets, dataset_path=args.dataset,
                      repeats=args.repeats, seed=args.seed)
    if args.json:
        print(json.dumps({"summary": report.summary(),
                          "cases": {k: vars(v) for k, v in report.cases.items()}}, default=str, indent=2))
    else:
        _print_summary(report)
        _print_per_case(report)
    return 0


def cmd_baseline(args) -> int:
    from reliability.evals.runner import run_eval
    from reliability.gate.baseline import save_baseline

    agent_cfg, judge_cfg, budgets = _build_configs(args)
    report = run_eval(agent_cfg, judge_cfg, budgets, dataset_path=args.dataset,
                      repeats=args.repeats, seed=args.seed)
    path = save_baseline(report, args.baseline)
    _print_summary(report)
    print(green(f"\n✓ Baseline saved to {path}"))
    return 0


def _print_comparison(cmp) -> None:
    print(bold(f"\nA/B comparison  ·  {cmp.n_cases} paired cases"))
    print(f"  baseline : {cmp.baseline_label}   pass-rate {cmp.baseline_pass_rate:.1%}")
    print(f"  candidate: {cmp.candidate_label}   pass-rate {cmp.candidate_pass_rate:.1%}")
    ci = cmp.overall_delta_ci
    print(f"  quality delta   : {cmp.overall_delta:+.3f}  95% CI [{ci.low:+.3f}, {ci.high:+.3f}]")
    print(f"  McNemar         : p={cmp.mcnemar.p_value:.4g}  "
          f"({cmp.mcnemar.detail['b_regressions']} regressions, {cmp.mcnemar.detail['c_fixes']} fixes)")
    print(f"  Wilcoxon        : p={cmp.wilcoxon.p_value:.4g}")
    print(f"  cost delta      : ${cmp.cost_delta_usd:+.6f}   latency delta: {cmp.latency_delta_ms:+.0f}ms")
    color = red if cmp.verdict == "REGRESSED" else (green if cmp.verdict == "IMPROVED" else yellow)
    print(bold(f"  verdict         : {color(cmp.verdict)}"))
    for r in cmp.reasons:
        print(dim(f"    {r}"))
    if cmp.per_grader:
        print(dim("  per-grader delta:"))
        for g in cmp.per_grader:
            gci = g.delta_ci
            print(dim(f"    {g.grader:<16} {g.delta:+.3f}  CI [{gci.low:+.3f},{gci.high:+.3f}]  {g.verdict}"))


def cmd_compare(args) -> int:
    from reliability.evals.runner import run_eval
    from reliability.gate.baseline import load_baseline
    from reliability.stats.compare import compare_runs

    agent_cfg, judge_cfg, budgets = _build_configs(args)
    candidate = run_eval(agent_cfg, judge_cfg, budgets, dataset_path=args.dataset,
                         repeats=args.repeats, seed=args.seed)
    baseline = load_baseline(args.baseline)
    if baseline is None:
        print(red(f"No baseline at {args.baseline}. Run `baseline` first."))
        return 2
    cmp = compare_runs(baseline, candidate, seed=args.seed)
    _print_comparison(cmp)
    return 0


def cmd_gate(args) -> int:
    from reliability.evals.runner import run_eval
    from reliability.gate.baseline import load_baseline
    from reliability.gate.gate import run_gate

    agent_cfg, judge_cfg, budgets = _build_configs(args)
    candidate = run_eval(agent_cfg, judge_cfg, budgets, dataset_path=args.dataset,
                         repeats=args.repeats, seed=args.seed)
    baseline = load_baseline(args.baseline)
    result = run_gate(candidate, baseline, budgets=budgets,
                      min_pass_rate=args.min_pass_rate, alpha=args.alpha, seed=args.seed)

    _print_summary(candidate)
    if result.comparison:
        _print_comparison(result.comparison)
    print(bold("\n── Gate decision ──"))
    for r in result.reasons:
        print(("  " + r))
    if result.passed:
        print(bold(green("\n✓ GATE PASSED")))
    else:
        print(bold(red("\n✗ GATE FAILED — change blocked")))
    if args.json:
        print(json.dumps(result.as_dict(), default=str, indent=2))
    return result.exit_code


def cmd_online(args) -> int:
    from reliability.evals.online import sample_and_score

    _, judge_cfg, budgets = _build_configs(args)
    res = sample_and_score(sample_size=args.sample, fraction=args.fraction, seed=args.seed,
                           budgets=budgets, judge_cfg=judge_cfg)
    print(json.dumps(res["summary"], indent=2))
    print(green(f"Scored {res['num_scored']} live traces -> run {res['run_id']}"))
    return 0


def cmd_demo(args) -> int:
    """Scripted 'break it' demo: freeze a good baseline, then regress the agent
    and watch the gate go red."""
    from reliability.evals.runner import run_eval
    from reliability.gate.baseline import load_baseline, save_baseline
    from reliability.gate.gate import run_gate

    os.environ["RELIABILITY_MOCK"] = "1"
    args.mock = True

    print(bold("\n[1/3] Establishing baseline with the healthy agent (mock mode)..."))
    base_cfg, judge_cfg, budgets = _build_configs(args)
    base_report = run_eval(base_cfg, judge_cfg, budgets, seed=args.seed)
    save_baseline(base_report, args.baseline)
    _print_summary(base_report)

    print(bold("\n[2/3] Regressing the agent (degraded prompt/behaviour) and re-running evals..."))
    args.variant = "degraded"
    deg_cfg, _, _ = _build_configs(args)
    deg_report = run_eval(deg_cfg, judge_cfg, budgets, seed=args.seed)
    _print_summary(deg_report)

    print(bold("\n[3/3] Running the CI gate on the regressed agent vs baseline..."))
    baseline = load_baseline(args.baseline)
    result = run_gate(deg_report, baseline, budgets=budgets,
                      min_pass_rate=args.min_pass_rate, alpha=args.alpha, seed=args.seed)
    if result.comparison:
        _print_comparison(result.comparison)
    print(bold("\n── Gate decision ──"))
    for r in result.reasons:
        print("  " + r)
    if result.passed:
        print(bold(green("\n✓ GATE PASSED (unexpected for the demo)")))
        return 0
    print(bold(red("\n✗ GATE FAILED — the regression was caught and the build is blocked.")))
    print(dim("This is the intended outcome: the suite caught the degraded agent."))
    return 0  # demo itself succeeds by catching the regression


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reliability", description="IntelliCommerce Reliability & Eval Suite")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--mock", action="store_true", help="deterministic FakeChatModel + mock judge (free, CI)")
        sp.add_argument("--provider", default="groq")
        sp.add_argument("--model", default=AgentConfig().model)
        sp.add_argument("--variant", default="base", help="FakeChatModel scenario variant (e.g. degraded)")
        sp.add_argument("--temperature", type=float, default=0.0)
        sp.add_argument("--system-prompt-file", default=None, help="override the agent system prompt (real A/B)")
        sp.add_argument("--judge-provider", default="groq")
        sp.add_argument("--judge-model", default=JudgeConfig().model)
        sp.add_argument("--dataset", default=None)
        sp.add_argument("--repeats", type=int, default=1)
        sp.add_argument("--seed", type=int, default=1234)
        sp.add_argument("--max-cost", type=float, default=Budgets().max_cost_usd)
        sp.add_argument("--max-latency", type=float, default=Budgets().max_latency_ms)
        sp.add_argument("--baseline", default=os.path.join(".reliability", "baseline.json"))
        sp.add_argument("--json", action="store_true")
        return sp

    common(sub.add_parser("eval", help="run the eval suite once")).set_defaults(func=cmd_eval)
    common(sub.add_parser("baseline", help="run evals and freeze a baseline")).set_defaults(func=cmd_baseline)
    common(sub.add_parser("compare", help="A/B compare a candidate against the baseline")).set_defaults(func=cmd_compare)
    g = common(sub.add_parser("gate", help="run the CI regression gate (exit 1 on regression)"))
    g.add_argument("--min-pass-rate", type=float, default=0.8)
    g.add_argument("--alpha", type=float, default=0.05)
    g.set_defaults(func=cmd_gate)
    o = common(sub.add_parser("online", help="sample & score live production traces"))
    o.add_argument("--sample", type=int, default=20)
    o.add_argument("--fraction", type=float, default=1.0)
    o.set_defaults(func=cmd_online)
    d = common(sub.add_parser("demo", help="scripted 'break it' regression demo"))
    d.add_argument("--min-pass-rate", type=float, default=0.8)
    d.add_argument("--alpha", type=float, default=0.05)
    d.set_defaults(func=cmd_demo)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    # Box-drawing / check glyphs need UTF-8; Windows consoles default to cp1252.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
