import os
import tempfile

import pytest

# Force deterministic, free mock mode for the whole test session and isolate the
# reliability store in a temp DB so tests never touch a real one.
os.environ.setdefault("RELIABILITY_MOCK", "1")
_TMP = tempfile.mkdtemp(prefix="reliability-tests-")
os.environ["RELIABILITY_DB"] = os.path.join(_TMP, "test.db")

from reliability.store import init_store  # noqa: E402

init_store()


@pytest.fixture
def synthetic_trace():
    """Factory for a Trace with given tool calls + answer (no agent run needed)."""
    from reliability.tracing.schema import Span, SpanKind, Trace

    def _make(query="q", answer="", tools=None, llm_tokens=(100, 20), cost=1e-5):
        tools = tools or []
        spans = []
        t = 1000.0
        llm = Span(span_id="llm0", trace_id="t", name="chat", kind=SpanKind.LLM,
                   start_ms=t, end_ms=t + 50,
                   attributes={"gen_ai.request.model": "llama-3.1-8b-instant",
                               "gen_ai.usage.input_tokens": llm_tokens[0],
                               "gen_ai.usage.output_tokens": llm_tokens[1],
                               "gen_ai.cost.usd": cost})
        spans.append(llm)
        for i, (name, args, result) in enumerate(tools):
            spans.append(Span(span_id=f"tool{i}", trace_id="t", name=f"execute_tool {name}",
                              kind=SpanKind.TOOL, start_ms=t + 60 + i, end_ms=t + 70 + i,
                              attributes={"gen_ai.tool.name": name,
                                          "gen_ai.tool.call.arguments": args,
                                          "gen_ai.tool.call.result": result}))
        return Trace(trace_id="t", query=query, final_answer=answer, spans=spans)

    return _make
