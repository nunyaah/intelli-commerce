"""Run the real LangGraph agent once and capture a full trace.

This is the single entry point used by the eval runner, the online sampler, and
the live API path. It guarantees every invocation is traced and (optionally)
persisted + exported, without changing the agent's own code paths.
"""
from __future__ import annotations

import uuid
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage

from agent.graph import build_graph
from reliability.agent_harness.llm_factory import make_llm
from reliability.config import AgentConfig, otlp_endpoint
from reliability.store import save_trace
from reliability.tracing.schema import Trace
from reliability.tracing.tracer import TraceCollector


def run_agent(
    query: str,
    cfg: Optional[AgentConfig] = None,
    thread_id: Optional[str] = None,
    source: str = "eval",
    persist: bool = True,
    export_otlp: Optional[bool] = None,
) -> Trace:
    cfg = cfg or AgentConfig()
    thread_id = thread_id or uuid.uuid4().hex

    llm = make_llm(cfg)
    graph = build_graph(llm=llm, system_prompt=cfg.system_prompt)

    collector = TraceCollector(
        query=query,
        thread_id=thread_id,
        agent_version=cfg.version_dict(),
        default_model=cfg.model,
        source=source,
    )
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [collector],
        "recursion_limit": 12,
    }
    state = {
        "messages": [HumanMessage(content=query)],
        "thread_id": thread_id,
        "hitl_pending": False,
        "hitl_payload": None,
    }

    final_answer = ""
    error: Optional[str] = None
    try:
        from reliability.guardrails.context import run_context

        with run_context(collector.trace.trace_id, thread_id):
            result = graph.invoke(state, config=config)
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and (msg.content or "").strip():
                final_answer = msg.content
                break
    except Exception as e:  # noqa: BLE001 — surface failure as a traced error, never crash the run
        error = f"{type(e).__name__}: {e}"

    trace = collector.finalize(final_answer, error)

    if persist:
        save_trace(trace)

    do_export = export_otlp if export_otlp is not None else (otlp_endpoint() is not None)
    if do_export:
        try:
            from reliability.tracing.otel_export import export_trace

            export_trace(trace)
        except Exception:  # noqa: BLE001 — export is best-effort, never fail the run
            pass

    return trace
