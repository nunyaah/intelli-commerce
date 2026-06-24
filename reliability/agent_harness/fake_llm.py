"""A deterministic, scripted chat model.

This is what makes the suite runnable in CI for $0 and makes the "break it"
demo reproducible. It is a real ``BaseChatModel`` so the *actual* LangGraph
graph runs unchanged — only the model backend is swapped. Tool calls still
execute against the (fixture) database, so grounding/tool-selection graders see
genuine tool results.

Scenario format (see reliability/data/fake_scripts.yaml)::

    scenarios:
      - id: kpis_today
        match: ["today's kpis", "kpis today"]   # case-insensitive substring
        base:
          turns:
            - tool_calls: [{name: get_metrics, args: {period: today}}]
            - answer: "Today's revenue is ${get_metrics.revenue}, {get_metrics.order_count} orders."
        variants:
          degraded:
            turns:
              - answer: "Revenue today is about $4,200,000."   # ungrounded -> fails grounding

``${tool.field}`` placeholders are filled from the actual ToolMessage results in
the live conversation, so the grounded answer tracks the fixture data exactly.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _approx_tokens(text: str) -> int:
    # Deterministic, monotonic-in-length proxy (~4 chars/token).
    return max(1, len(text) // 4)


class FakeChatModel(BaseChatModel):
    """Scripted chat model driven by query-matched scenarios."""

    scenarios: list = []
    variant: str = "base"
    model_name: str = "llama-3.1-8b-instant"

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    # The graph calls ChatGroq(...).bind_tools(TOOLS); mirror that surface.
    def bind_tools(self, tools, **kwargs) -> "FakeChatModel":  # noqa: ANN001
        return self

    # --- scenario resolution -------------------------------------------------
    def _match_scenario(self, query: str) -> Optional[dict]:
        q = (query or "").lower().strip()
        best = None
        best_len = -1
        for sc in self.scenarios:
            for m in sc.get("match", []):
                m = m.lower()
                if m in q and len(m) > best_len:
                    best = sc
                    best_len = len(m)
        return best

    def _turns_for(self, scenario: dict) -> list[dict]:
        if self.variant != "base":
            variant = scenario.get("variants", {}).get(self.variant)
            if variant and variant.get("turns"):
                return variant["turns"]
        return scenario.get("base", {}).get("turns", [])

    def _latest_query(self, messages: list[BaseMessage]) -> str:
        for msg in messages:
            if isinstance(msg, HumanMessage):
                return msg.content if isinstance(msg.content, str) else str(msg.content)
        return ""

    def _turn_index(self, messages: list[BaseMessage]) -> int:
        # The agent_node has produced one AIMessage per prior turn.
        return sum(1 for m in messages if isinstance(m, AIMessage))

    def _tool_results(self, messages: list[BaseMessage]) -> dict[str, str]:
        out: dict[str, str] = {}
        for m in messages:
            if isinstance(m, ToolMessage):
                name = getattr(m, "name", None)
                if name:
                    out[name] = m.content if isinstance(m.content, str) else str(m.content)
        return out

    def _render(self, template: str, tool_results: dict[str, str]) -> str:
        def sub(match: re.Match) -> str:
            expr = match.group(1)
            tool, _, field = expr.partition(".")
            raw = tool_results.get(tool)
            if raw is None:
                return match.group(0)
            if not field:
                return raw
            try:
                data = json.loads(raw)
                if isinstance(data, list) and data:
                    data = data[0]
                val = data.get(field) if isinstance(data, dict) else None
                return str(val) if val is not None else match.group(0)
            except (json.JSONDecodeError, AttributeError):
                return match.group(0)

        return _PLACEHOLDER.sub(sub, template)

    # --- generation ----------------------------------------------------------
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        query = self._latest_query(messages)
        scenario = self._match_scenario(query)
        turn = self._turn_index(messages)
        tool_results = self._tool_results(messages)

        if scenario is None:
            # Unknown query: behave like a model with no idea -> safe, ungrounded.
            msg = self._make_message("I don't have enough information to answer that.", [], messages)
            return ChatResult(generations=[ChatGeneration(message=msg)])

        turns = self._turns_for(scenario)
        if turn >= len(turns):
            # Past the script: emit a terminal answer to avoid loops.
            msg = self._make_message("(no further action)", [], messages)
            return ChatResult(generations=[ChatGeneration(message=msg)])

        spec = turns[turn]
        tool_calls = spec.get("tool_calls")
        if tool_calls:
            calls = [
                {
                    "name": tc["name"],
                    "args": tc.get("args", {}),
                    "id": f"call_{turn}_{i}",
                    "type": "tool_call",
                }
                for i, tc in enumerate(tool_calls)
            ]
            msg = self._make_message("", calls, messages)
            return ChatResult(generations=[ChatGeneration(message=msg)])

        answer = self._render(spec.get("answer", ""), tool_results)
        msg = self._make_message(answer, [], messages)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _make_message(
        self, content: str, tool_calls: list, messages: list[BaseMessage]
    ) -> AIMessage:
        in_text = " ".join(
            m.content if isinstance(getattr(m, "content", ""), str) else "" for m in messages
        )
        out_text = content + json.dumps(tool_calls)
        usage = {
            "input_tokens": _approx_tokens(in_text),
            "output_tokens": _approx_tokens(out_text),
            "total_tokens": _approx_tokens(in_text) + _approx_tokens(out_text),
        }
        return AIMessage(
            content=content,
            tool_calls=tool_calls,
            usage_metadata=usage,
            response_metadata={"model_name": self.model_name},
        )
