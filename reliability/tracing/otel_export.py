"""Optional OpenTelemetry export of captured traces.

We keep our own SQLite store as the always-on source of truth (so the suite is
self-contained and CI-friendly), and *additionally* emit standards-compliant
OTel GenAI spans to any OTLP/HTTP endpoint when one is configured — e.g.
Langfuse v3 at ``http://localhost:3001/api/public/otel``. This is the "stand on
open standards" bridge; it is a no-op when OpenTelemetry isn't installed or no
endpoint is set, so it never adds a hard dependency.
"""
from __future__ import annotations

import os
from functools import lru_cache

from reliability.config import otlp_endpoint
from reliability.tracing.schema import SpanKind, Trace


@lru_cache(maxsize=1)
def _tracer():
    endpoint = otlp_endpoint()
    if not endpoint:
        return None
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:
        return None

    # Opt in to the latest experimental GenAI conventions, per the OTel transition plan.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
    provider = TracerProvider(
        resource=Resource.create({"service.name": "intellicommerce-agent"})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    return provider.get_tracer("reliability")


def export_trace(trace: Trace) -> bool:
    tracer = _tracer()
    if tracer is None:
        return False
    from opentelemetry.trace import SpanKind as OTSpanKind

    kind_map = {
        SpanKind.LLM: OTSpanKind.CLIENT,
        SpanKind.TOOL: OTSpanKind.INTERNAL,
        SpanKind.GUARDRAIL: OTSpanKind.INTERNAL,
        SpanKind.CHAIN: OTSpanKind.INTERNAL,
    }
    with tracer.start_as_current_span(
        name=f"agent.run {trace.agent_version.get('model', '')}",
        kind=OTSpanKind.SERVER,
    ) as root:
        root.set_attribute("gen_ai.system", "intellicommerce")
        root.set_attribute("session.id", trace.thread_id or "")
        root.set_attribute("gen_ai.usage.input_tokens", trace.total_input_tokens)
        root.set_attribute("gen_ai.usage.output_tokens", trace.total_output_tokens)
        root.set_attribute("gen_ai.cost.usd", trace.total_cost_usd)
        for s in sorted(trace.spans, key=lambda x: x.start_ms):
            child = tracer.start_span(s.name, kind=kind_map.get(s.kind, OTSpanKind.INTERNAL))
            for k, v in s.attributes.items():
                try:
                    child.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
                except Exception:  # noqa: BLE001
                    pass
            if s.status == "error":
                child.set_attribute("error", True)
                if s.error:
                    child.set_attribute("error.message", s.error)
            child.end()
    return True
