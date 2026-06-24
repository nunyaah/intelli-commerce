import json
import sys
import uuid
from datetime import datetime
from typing import Optional

sys.path.insert(0, "/app")

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent.graph import get_graph
from api.langfuse_client import get_callback
from shared.db import get_conn

from reliability.config import AgentConfig, Budgets
from reliability.guardrails.context import run_context
from reliability.guardrails.pipeline import GuardrailPipeline
from reliability.store import init_store, save_trace
from reliability.tracing.tracer import TraceCollector

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    # Optional so an explicit JSON null from the frontend (first message, before a
    # thread exists) validates instead of returning 422.
    thread_id: Optional[str] = None


@router.post("/chat")
def chat(req: ChatRequest):
    thread_id = req.thread_id or str(uuid.uuid4())

    def generate():
        graph = get_graph()
        cfg = AgentConfig()  # live agent = production defaults

        # Full-trace instrumentation of the real agent run, plus optional Langfuse.
        collector = TraceCollector(
            query=req.message, thread_id=thread_id, agent_version=cfg.version_dict(),
            default_model=cfg.model, source="live",
        )
        callbacks = [collector]
        lf = get_callback()
        if lf is not None:
            callbacks.append(lf)

        guard = GuardrailPipeline(
            budgets=Budgets(), trace_id=collector.trace.trace_id, thread_id=thread_id,
        )

        try:
            init_store()
        except Exception:
            pass

        config = {"configurable": {"thread_id": thread_id}, "callbacks": callbacks}
        state = {
            "messages": [HumanMessage(content=req.message)],
            "thread_id": thread_id,
            "hitl_pending": False,
            "hitl_payload": None,
        }

        final_answer = ""
        error = None
        try:
            with run_context(collector.trace.trace_id, thread_id):
                for chunk in graph.stream(state, config=config, stream_mode="updates"):
                    for node, update in chunk.items():
                        for msg in update.get("messages", []):
                            tool_calls = getattr(msg, "tool_calls", None) or []
                            content = getattr(msg, "content", "") or ""
                            if tool_calls:
                                for tc in tool_calls:
                                    yield _sse({"type": "tool_call", "tool": tc["name"],
                                                "args": tc.get("args", {}), "node": node})
                            elif content:
                                # Runtime output guard: PII redaction + grounding check
                                # against the evidence gathered so far in this run.
                                evidence = collector.trace.tool_outputs_text()
                                guarded = guard.guard_output(content, evidence)
                                final_answer = guarded.text
                                yield _sse({
                                    "type": "message", "content": guarded.text, "node": node,
                                    "guardrails": {
                                        "pii_redacted": guarded.pii_redacted,
                                        "grounding_flagged": guarded.grounding_flagged,
                                    },
                                })
                                for ev in guarded.events:
                                    if ev["action"] in ("redact", "flag"):
                                        yield _sse({"type": "guardrail", **ev})

                        # Max-cost circuit breaker (per live run).
                        if guard.check_total(collector.trace.total_cost_usd):
                            yield _sse({"type": "guardrail", "guard": "cost_circuit_breaker",
                                        "action": "trip", "severity": "high"})
                            final_answer = guard.fallback_message()
                            yield _sse({"type": "message", "content": final_answer, "node": "guardrail"})
                            raise _BudgetTripped()

                        if update.get("hitl_pending"):
                            payload = update.get("hitl_payload") or {}
                            _enqueue_hitl(thread_id, payload, collector.trace.trace_id)
                            yield _sse({"type": "hitl_alert", "payload": payload, "thread_id": thread_id})

            yield _sse({"type": "done", "thread_id": thread_id})
        except _BudgetTripped:
            yield _sse({"type": "done", "thread_id": thread_id})
        except Exception as e:  # noqa: BLE001
            error = str(e)
            yield _sse({"type": "error", "message": error})
        finally:
            try:
                trace = collector.finalize(final_answer, error)
                save_trace(trace)
            except Exception:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class _BudgetTripped(Exception):
    pass


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _enqueue_hitl(thread_id: str, payload: dict, trace_id: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO hitl_queue (thread_id, trace_id, query, anomaly_type, description, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (thread_id, trace_id, payload.get("query", ""), "anomaly",
         payload.get("message", ""), "pending", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
