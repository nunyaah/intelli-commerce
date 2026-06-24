"""Trace tree data model, aligned with OpenTelemetry GenAI semantic conventions.

OTel GenAI conventions are still experimental (mid-2026), so we adopt the
attribute *names* (``gen_ai.*``) and span shapes but keep our own lightweight,
serialisable model as the source of truth. This is what the store persists and
what graders introspect.

Conventions used:
  * LLM inference span  -> name "chat <model>",  kind "llm"
      gen_ai.operation.name, gen_ai.request.model, gen_ai.request.temperature,
      gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, gen_ai.cost.usd
  * Tool execution span -> name "execute_tool <tool>", kind "tool"
      gen_ai.tool.name, gen_ai.tool.call.arguments, gen_ai.tool.call.result
  * Guardrail span      -> name "guardrail <name>",  kind "guardrail"
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


class SpanKind:
    LLM = "llm"
    TOOL = "tool"
    CHAIN = "chain"
    GUARDRAIL = "guardrail"


@dataclass
class Span:
    span_id: str
    trace_id: str
    name: str
    kind: str
    start_ms: float
    end_ms: Optional[float] = None
    parent_id: Optional[str] = None
    status: str = "ok"  # ok | error
    error: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.end_ms is None:
            return 0.0
        return round(self.end_ms - self.start_ms, 2)

    # --- typed accessors for the two span kinds graders care about ----------
    @property
    def model(self) -> Optional[str]:
        return self.attributes.get("gen_ai.request.model")

    @property
    def input_tokens(self) -> int:
        return int(self.attributes.get("gen_ai.usage.input_tokens", 0) or 0)

    @property
    def output_tokens(self) -> int:
        return int(self.attributes.get("gen_ai.usage.output_tokens", 0) or 0)

    @property
    def cost_usd(self) -> float:
        return float(self.attributes.get("gen_ai.cost.usd", 0.0) or 0.0)

    @property
    def tool_name(self) -> Optional[str]:
        return self.attributes.get("gen_ai.tool.name")

    @property
    def tool_args(self) -> Any:
        return self.attributes.get("gen_ai.tool.call.arguments")

    @property
    def tool_result(self) -> Any:
        return self.attributes.get("gen_ai.tool.call.result")

    def to_row(self) -> dict:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "kind": self.kind,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
            "attributes": json.dumps(self.attributes, default=str),
        }

    @classmethod
    def from_row(cls, row: dict) -> "Span":
        attrs = row.get("attributes")
        return cls(
            span_id=row["span_id"],
            trace_id=row["trace_id"],
            parent_id=row.get("parent_id"),
            name=row["name"],
            kind=row["kind"],
            start_ms=row["start_ms"],
            end_ms=row.get("end_ms"),
            status=row.get("status", "ok"),
            error=row.get("error"),
            attributes=json.loads(attrs) if isinstance(attrs, str) else (attrs or {}),
        )


@dataclass
class ToolCall:
    """Flattened tool invocation, in call order — the unit graders reason over."""

    name: str
    args: Any
    result: Any
    order: int
    duration_ms: float
    status: str
    error: Optional[str] = None


@dataclass
class Trace:
    trace_id: str
    query: str
    thread_id: Optional[str] = None
    final_answer: str = ""
    agent_version: dict = field(default_factory=dict)
    source: str = "eval"  # eval | live | online
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error: Optional[str] = None
    spans: list[Span] = field(default_factory=list)

    # --- derived aggregates --------------------------------------------------
    @property
    def llm_spans(self) -> list[Span]:
        return [s for s in self.spans if s.kind == SpanKind.LLM]

    @property
    def tool_spans(self) -> list[Span]:
        return [s for s in self.spans if s.kind == SpanKind.TOOL]

    @property
    def guardrail_spans(self) -> list[Span]:
        return [s for s in self.spans if s.kind == SpanKind.GUARDRAIL]

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.llm_spans)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.llm_spans)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(s.cost_usd for s in self.llm_spans), 8)

    @property
    def num_llm_calls(self) -> int:
        return len(self.llm_spans)

    @property
    def num_tool_calls(self) -> int:
        return len(self.tool_spans)

    @property
    def duration_ms(self) -> float:
        ends = [s.end_ms for s in self.spans if s.end_ms is not None]
        starts = [s.start_ms for s in self.spans]
        if not ends or not starts:
            return 0.0
        return round(max(ends) - min(starts), 2)

    def tool_calls(self) -> list[ToolCall]:
        ordered = sorted(self.tool_spans, key=lambda s: s.start_ms)
        out: list[ToolCall] = []
        for i, s in enumerate(ordered):
            out.append(
                ToolCall(
                    name=s.tool_name or s.name,
                    args=s.tool_args,
                    result=s.tool_result,
                    order=i,
                    duration_ms=s.duration_ms,
                    status=s.status,
                    error=s.error,
                )
            )
        return out

    def tool_names(self) -> list[str]:
        return [tc.name for tc in self.tool_calls()]

    def tool_outputs_text(self) -> str:
        """Concatenated tool results — the evidence the answer must be grounded in."""
        parts = []
        for tc in self.tool_calls():
            if tc.result is None:
                continue
            parts.append(str(tc.result))
        return "\n".join(parts)

    def header_row(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "thread_id": self.thread_id,
            "query": self.query,
            "final_answer": self.final_answer,
            "agent_version": json.dumps(self.agent_version, default=str),
            "source": self.source,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "cost_usd": self.total_cost_usd,
            "num_llm_calls": self.num_llm_calls,
            "num_tool_calls": self.num_tool_calls,
            "error": self.error,
        }

    def to_dict(self) -> dict:
        d = self.header_row()
        d["agent_version"] = self.agent_version
        d["spans"] = [s.to_row() | {"attributes": s.attributes} for s in self.spans]
        d["tool_calls"] = [
            {"name": tc.name, "args": tc.args, "result": tc.result, "order": tc.order,
             "duration_ms": tc.duration_ms, "status": tc.status}
            for tc in self.tool_calls()
        ]
        return d
