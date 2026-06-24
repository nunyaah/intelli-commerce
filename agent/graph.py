import os
import sys

sys.path.insert(0, "/app")

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agent.state import AgentState
from agent.tools import TOOLS

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

SYSTEM_PROMPT = """You are IntelliCommerce AI, an intelligent real-time e-commerce analyst.

You have access to:
- query_orders: SQL queries on live order data
- search_tickets: Semantic search over support tickets
- get_metrics: Aggregated KPIs (today / last_hour / last_7_days)
- detect_anomaly: Z-score anomaly detection (revenue / tickets / refunds)
- web_search: External benchmarks and context

Rules:
- Always back conclusions with data from your tools.
- When detect_anomaly returns status=critical, prefix your response with [HITL_ALERT] and describe the anomaly clearly for human review.
- Be concise and analytical. Think like a data-driven operations manager."""


def build_graph(llm=None, system_prompt: str = SYSTEM_PROMPT):
    """Build the IntelliCommerce ReAct graph.

    ``llm`` and ``system_prompt`` are injectable so the reliability suite can run
    the *same* graph against a different model/prompt/variant (for A/B and the
    "break it" demo) or a deterministic FakeChatModel (for free CI runs). When
    omitted, behaviour is identical to production.
    """
    if llm is None:
        # Imported lazily so the graph can be built with an injected model
        # (FakeChatModel / a different provider) without requiring langchain_groq.
        from langchain_groq import ChatGroq

        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=GROQ_API_KEY,
            temperature=0,
        )
    llm = llm.bind_tools(TOOLS)

    def agent_node(state: AgentState):
        messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
        response = llm.invoke(messages)
        hitl_pending = "[HITL_ALERT]" in (response.content or "")
        return {
            "messages": [response],
            "hitl_pending": hitl_pending,
            "hitl_payload": (
                {"message": response.content, "thread_id": state.get("thread_id")}
                if hitl_pending
                else None
            ),
        }

    def route(state: AgentState):
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    checkpointer = MemorySaver()

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", route)
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=checkpointer)


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
