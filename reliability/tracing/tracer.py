"""A LangChain callback handler that assembles a full trace tree.

It captures every LLM inference and tool execution as an OTel-GenAI-shaped span
(tokens, cost, latency, args, results, errors) tied to a single trace/thread id.
This is the instrumentation of the *real* agent — it makes no assumptions about
the model and works for both ChatGroq and the FakeChatModel.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from langchain_core.callbacks.base import BaseCallbackHandler

from reliability.tracing import cost as cost_model
from reliability.tracing.schema import Span, SpanKind, Trace


def _now_ms() -> float:
    return time.time() * 1000.0


def _coerce_text(obj: Any) -> str:
    if obj is None:
        return ""
    content = getattr(obj, "content", None)
    if content is not None:
        return content if isinstance(content, str) else str(content)
    return str(obj)


def _extract_usage(response: Any) -> tuple[int, int, Optional[str]]:
    """Pull (input_tokens, output_tokens, model) from an LLMResult."""
    in_tok = out_tok = 0
    model = None
    try:
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        if msg is not None:
            um = getattr(msg, "usage_metadata", None) or {}
            in_tok = int(um.get("input_tokens", 0) or 0)
            out_tok = int(um.get("output_tokens", 0) or 0)
            rmd = getattr(msg, "response_metadata", None) or {}
            model = rmd.get("model_name") or rmd.get("model")
    except (AttributeError, IndexError, TypeError):
        pass

    llm_output = getattr(response, "llm_output", None) or {}
    if (in_tok == 0 and out_tok == 0) and isinstance(llm_output, dict):
        tu = llm_output.get("token_usage") or llm_output.get("usage") or {}
        in_tok = int(tu.get("prompt_tokens", tu.get("input_tokens", 0)) or 0)
        out_tok = int(tu.get("completion_tokens", tu.get("output_tokens", 0)) or 0)
    if not model and isinstance(llm_output, dict):
        model = llm_output.get("model_name") or llm_output.get("model")
    return in_tok, out_tok, model


class TraceCollector(BaseCallbackHandler):
    """Builds a :class:`Trace` from a single agent invocation."""

    # We never raise out of a callback — instrumentation must not break the SUT.
    raise_error = False

    def __init__(self, query: str, thread_id: Optional[str], agent_version: dict,
                 default_model: str, source: str = "eval", trace_id: Optional[str] = None):
        self.trace = Trace(
            trace_id=trace_id or uuid.uuid4().hex,
            query=query,
            thread_id=thread_id,
            agent_version=agent_version,
            source=source,
            started_at=None,
        )
        self.default_model = default_model
        self._open: dict[str, Span] = {}
        self._started = False

    def _ensure_started(self) -> None:
        if not self._started:
            self.trace.started_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            self._started = True

    # --- LLM spans -----------------------------------------------------------
    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
        self._ensure_started()
        model = (serialized or {}).get("kwargs", {}).get("model") or self.default_model
        span = Span(
            span_id=str(run_id),
            trace_id=self.trace.trace_id,
            parent_id=str(parent_run_id) if parent_run_id else None,
            name=f"chat {model}",
            kind=SpanKind.LLM,
            start_ms=_now_ms(),
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": model,
            },
        )
        self._open[str(run_id)] = span

    def on_llm_end(self, response, *, run_id, **kwargs):
        span = self._open.pop(str(run_id), None)
        if span is None:
            return
        span.end_ms = _now_ms()
        in_tok, out_tok, model = _extract_usage(response)
        model = model or span.attributes.get("gen_ai.request.model") or self.default_model
        span.attributes["gen_ai.request.model"] = model
        span.attributes["gen_ai.usage.input_tokens"] = in_tok
        span.attributes["gen_ai.usage.output_tokens"] = out_tok
        span.attributes["gen_ai.cost.usd"] = cost_model.cost_usd(model, in_tok, out_tok)
        self.trace.spans.append(span)

    def on_llm_error(self, error, *, run_id, **kwargs):
        span = self._open.pop(str(run_id), None)
        if span is None:
            return
        span.end_ms = _now_ms()
        span.status = "error"
        span.error = str(error)
        self.trace.spans.append(span)

    # --- Tool spans ----------------------------------------------------------
    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, inputs=None, **kwargs):
        self._ensure_started()
        name = (serialized or {}).get("name") or "tool"
        args = inputs if inputs is not None else input_str
        span = Span(
            span_id=str(run_id),
            trace_id=self.trace.trace_id,
            parent_id=str(parent_run_id) if parent_run_id else None,
            name=f"execute_tool {name}",
            kind=SpanKind.TOOL,
            start_ms=_now_ms(),
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": name,
                "gen_ai.tool.call.arguments": args,
            },
        )
        self._open[str(run_id)] = span

    def on_tool_end(self, output, *, run_id, **kwargs):
        span = self._open.pop(str(run_id), None)
        if span is None:
            return
        span.end_ms = _now_ms()
        span.attributes["gen_ai.tool.call.result"] = _coerce_text(output)
        self.trace.spans.append(span)

    def on_tool_error(self, error, *, run_id, **kwargs):
        span = self._open.pop(str(run_id), None)
        if span is None:
            return
        span.end_ms = _now_ms()
        span.status = "error"
        span.error = str(error)
        span.attributes["gen_ai.tool.call.result"] = f"ERROR: {error}"
        self.trace.spans.append(span)

    # --- finalisation --------------------------------------------------------
    def finalize(self, final_answer: str, error: Optional[str] = None) -> Trace:
        # Close any spans left open by an exception.
        for span in self._open.values():
            span.end_ms = _now_ms()
            if span.status == "ok":
                span.status = "error"
                span.error = span.error or "span not closed"
            self.trace.spans.append(span)
        self._open.clear()
        self.trace.final_answer = final_answer or ""
        self.trace.error = error
        self.trace.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        return self.trace
