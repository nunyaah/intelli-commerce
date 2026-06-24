# IntelliCommerce — Agent Reliability & Evaluation Suite

> *I make AI agents trustworthy enough to ship — so they don't silently break, hallucinate, or blow the token budget.*

A production-grade **observability + evaluation + guardrails + CI regression-gating** layer for LLM agents, built around a real, non-trivial system-under-test: **IntelliCommerce**, a LangGraph ReAct agent that analyses live e-commerce data with five tools (SQL, RAG, KPIs, anomaly detection, web search).

**The outcome that matters:** change the agent's prompt, model, or a tool → run **one command** → get a **statistically honest verdict on whether quality regressed**, plus what it now **costs** and how **slow** it is — and a **CI gate that blocks the change if it regressed**. Every run is fully traced in a dashboard.

```bash
# Watch the suite catch a regression and fail the build — deterministic, free, ~30s:
python -m reliability.cli demo          # or: bash scripts/demo.sh  /  pwsh scripts/demo.ps1
```

```
✗ GATE FAILED — change blocked
  FAIL: pass-rate 30.0% is below the minimum 80%.
  FAIL: critical grader 'grounding' pass-rate 57.1% below floor 90%.
  FAIL: statistically significant regression vs baseline:
    - Overall quality delta CI [-0.405, -0.139] is entirely below zero (mean -0.274).
  McNemar p=0.0156 (7 pass→fail, 0 fail→pass)
```

---

## Why this exists (and what's original)

Off-the-shelf tools (DeepEval, Ragas, promptfoo, Langfuse) give you *metrics* and *transport*. None of them give you an **honest paired statistical verdict that gates CI**. That engine — graders, statistics, guardrails, gating — is the original work here. We **stand on open standards** for the plumbing and **build** the judgment layer.

| Pillar | Stand on (integrate) | Built here (original) |
|---|---|---|
| **Tracing** | OpenTelemetry **GenAI semantic conventions** (`gen_ai.*`); optional OTLP export to **Langfuse v3** | A LangChain callback that assembles the full trace tree (LLM + tool spans, tokens, cost, latency, retries, errors) + a self-contained SQLite span store + the cost model |
| **Evaluation** | Metric *definitions* as inspiration | The **whole engine**: versioned dataset, 5 graders, an LLM-judge (+ deterministic mock), and the **statistics** — paired bootstrap CIs, McNemar, Wilcoxon, A/B compare — implemented in numpy and unit-tested |
| **Guardrails** | Presidio (optional PII backend), `sqlglot` (SQL AST) | SQL-safety guard, regex+Luhn PII redactor, pre-return grounding check, max-cost circuit breaker, event logging |

> Research note: as of mid-2026 the OTel GenAI conventions are still *experimental*; Langfuse went OTel-native (SDK v3) and is ClickHouse-owned but MIT/self-hostable. The 2026 eval-stats consensus — *ship only when the paired delta CI is entirely one side of zero; McNemar for pass/fail, Wilcoxon for ordinal scores* — is exactly what the gate implements.

---

## The three pillars

### 1 · Tracing & observability
Every agent run (live or eval) is instrumented end-to-end via a `BaseCallbackHandler` ([reliability/tracing/tracer.py](reliability/tracing/tracer.py)): one span per LLM call (model, input/output tokens, **cost**, latency) and per tool call (args + result + errors), tied to a thread/run id. Spans use OTel GenAI attribute names and persist to a SQLite store ([reliability/store.py](reliability/store.py)); when `OTEL_EXPORTER_OTLP_ENDPOINT` is set they also export to any OTLP collector (e.g. Langfuse v3). The **Traces** tab renders the span tree + transcript + cost/latency per run.

### 2 · Evaluation engine *(the core)*
- **Versioned dataset** ([reliability/data/dataset_v1.yaml](reliability/data/dataset_v1.yaml)) — easy → adversarial: happy-path KPIs, ambiguous asks, an anomaly case that **must** escalate to HITL, hallucination bait (no data for Q3 2023), an unsafe-SQL request, and a PII case.
- **Graders** ([reliability/evals/graders/](reliability/evals/graders/)) — programmatic *and* LLM-judge:
  - **tool-selection** — right tool(s), sensible order
  - **grounding/faithfulness** — every numeric claim must trace to a tool result (value-matched, not substring; echoing the user's own figures is allowed)
  - **SQL safety** — SELECT-only, single statement, known tables (AST via `sqlglot`)
  - **answer quality** — anchored-rubric LLM judge (+ deterministic mock for CI)
  - **cost & latency budgets**
- **Statistics** ([reliability/stats/](reliability/stats/)) — paired **bootstrap CIs** on the per-case delta, **McNemar** (paired pass/fail), **Wilcoxon** signed-rank (ordinal scores), and A/B `compare_runs` that returns `REGRESSED / IMPROVED / NO_CHANGE` with reasons.
- **Run modes** — **offline** (against the dataset, deterministic fixture DB) and **online** (sampled scoring of live production traces, [reliability/evals/online.py](reliability/evals/online.py)).

### 3 · Runtime guardrails + CI gate
- **Guardrails** ([reliability/guardrails/](reliability/guardrails/)) wrapping the live agent: unsafe SQL blocked at the tool boundary (shares logic with the grader), PII redaction, a pre-return grounding check, and a per-run max-cost circuit breaker with a clean fallback. Every event is logged and shown in the **Guardrails** tab.
- **CI regression gate** ([reliability/gate/](reliability/gate/)) — a CLI + GitHub Action ([.github/workflows/agent-evals.yml](.github/workflows/agent-evals.yml)) that runs the suite on every change and **fails the build** on a statistically significant regression, a critical-grader collapse, or a budget breach — with a readable diff vs the committed baseline.
- **Closed HITL loop** ([reliability/hitl.py](reliability/hitl.py)) — the once write-only queue now feeds review → label → **export corrected labels into the eval dataset** (auto-bumping its version), via the **HITL & Labeling** tab.

---

## The one-command loop

```bash
pip install -r requirements-dev.txt

# Mock mode (deterministic, free, no API key) — ideal for CI and demos:
python -m reliability.cli eval     --mock                 # run the suite once
python -m reliability.cli baseline --mock                 # freeze a baseline
python -m reliability.cli gate     --mock --variant degraded   # exit 1 on regression
python -m reliability.cli compare  --mock --variant degraded   # A/B with full stats
python -m reliability.cli online   --sample 20            # score sampled live traces
python -m reliability.cli demo                            # scripted "break it"

# Real mode (uses Groq; cheap) — change the agent and re-gate:
export GROQ_API_KEY=...
python -m reliability.cli baseline                              # baseline on current agent
python -m reliability.cli gate --model gemma2-9b-it             # swap model and re-gate
python -m reliability.cli gate --system-prompt-file my_prompt.txt   # swap prompt and re-gate
```

Reproducibility: every run records the **agent version** (provider/model/prompt-hash/variant), **seed**, dataset version, and budgets. Same inputs → same verdict.

---

## Dashboard

The existing React dashboard is extended with four tabs wired to **real** store data (never hardcoded):

| Tab | What it shows |
|---|---|
| **Overview** | Original live KPIs, charts, chat, anomaly/HITL queue |
| **Traces** | Trace explorer + per-run drill-down: span tree, transcript, tokens/cost/latency |
| **Evaluations** | Run history, per-grader pass-rates, and A/B comparison with delta CIs + McNemar/Wilcoxon + verdict |
| **Guardrails** | Live guardrail events: SQL blocks, PII redactions, grounding flags, circuit-breaker trips |
| **HITL & Labeling** | Review a real trace → correct its expected behaviour → export into the eval dataset |

---

## Run it

```bash
git clone <repo-url> && cd intelli-commerce
cp .env.example .env            # paste GROQ_API_KEY (only needed for the live agent)
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API / docs | http://localhost:8000 · http://localhost:8000/docs |
| Langfuse (optional) | http://localhost:3001 |

The reliability API (`/api/traces`, `/api/evals/*`, `/api/guardrails/events`, `/api/labels/*`) and store (`/data/reliability.db`) come up automatically.

---

## Testing

The eval engine must itself be trustworthy, so it has real unit tests ([tests/](tests/)) over graders, statistics, guardrails, and the end-to-end gate:

```bash
pytest -q          # 34 tests: SQL guard, PII/Luhn, bootstrap/McNemar/Wilcoxon, graders, gate
```

`tests/test_gate.py` proves both directions: the healthy agent passes the gate, and the degraded agent is caught (delta CI entirely below zero, exit code 1).

---

## Cost notes (bootstrapping-friendly)

- **CI and the demo cost $0**: mock mode uses a deterministic `FakeChatModel` + mock judge — no network, no credits, no secrets. The GitHub Action runs entirely in mock mode.
- **Real eval runs are cents**: the agent under test is Groq `llama-3.1-8b-instant` (~$0.05/$0.08 per 1M tokens); the LLM judge is Groq `llama-3.3-70b-versatile`. A full 10-case offline run is well under a cent; Groq's free tier covers normal use.
- Cost is computed per span from a transparent pricing table ([reliability/tracing/cost.py](reliability/tracing/cost.py)) and enforced by the budget grader + circuit breaker.

---

## Architecture

```
            ┌─ Data generators ─► SQLite ─► Pipeline ─► ChromaDB (RAG) ─┐
            │                                                            │
  React ◄── FastAPI (SSE chat + REST) ◄── LangGraph ReAct agent (SUT) ◄─┘
 dashboard        │   tools: query_orders · search_tickets · get_metrics · detect_anomaly · web_search
                  │
   ┌──────────────┴───────────────  RELIABILITY SUITE  ───────────────────────────┐
   │  TraceCollector (OTel GenAI)  →  SQLite span store  →  Dashboard / OTLP export │
   │  Eval runner → graders (+ judge) → stats (bootstrap/McNemar/Wilcoxon) → Gate   │
   │  Guardrails (SQL · PII · grounding · cost breaker)  →  guardrail events         │
   │  HITL review → label → eval dataset (versioned)                                 │
   └────────────────────────────────────────────────────────────────────────────────┘
```

## Repo layout (reliability suite)

```
reliability/
  config.py              # env config + reproducible AgentConfig/JudgeConfig/Budgets
  store.py               # SQLite store: traces, eval runs, guardrail events, labels
  cli.py                 # eval / baseline / compare / gate / online / demo
  hitl.py                # review → label → export-to-dataset loop
  tracing/               # schema (OTel GenAI), tracer callback, cost model, OTLP export
  agent_harness/         # LLM factory, deterministic FakeChatModel, traced runner
  evals/                 # dataset, graders/, judge, runner, online sampler, report
  stats/                 # bootstrap, significance (McNemar/Wilcoxon), compare
  guardrails/            # sql_guard, pii, grounding_guard, circuit_breaker, pipeline
  data/                  # dataset_v1.yaml, fixtures, fake_scripts.yaml
  baselines/baseline.json  # committed baseline the CI gate compares against
tests/                   # unit + integration tests
```
