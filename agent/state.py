from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    thread_id: str
    hitl_pending: bool
    hitl_payload: Optional[dict]
