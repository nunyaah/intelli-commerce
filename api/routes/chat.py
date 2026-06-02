import json
import sys
import uuid
from datetime import datetime

sys.path.insert(0, "/app")

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent.graph import get_graph
from shared.db import get_conn

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    thread_id: str = None


@router.post("/chat")
def chat(req: ChatRequest):
    thread_id = req.thread_id or str(uuid.uuid4())

    def generate():
        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state = {
            "messages": [HumanMessage(content=req.message)],
            "thread_id": thread_id,
            "hitl_pending": False,
            "hitl_payload": None,
        }
        try:
            for chunk in graph.stream(state, config=config, stream_mode="updates"):
                for node, update in chunk.items():
                    for msg in update.get("messages", []):
                        tool_calls = getattr(msg, "tool_calls", None) or []
                        content = getattr(msg, "content", "") or ""
                        if tool_calls:
                            for tc in tool_calls:
                                yield f"data: {json.dumps({'type': 'tool_call', 'tool': tc['name'], 'args': tc.get('args', {}), 'node': node})}\n\n"
                        elif content:
                            yield f"data: {json.dumps({'type': 'message', 'content': content, 'node': node})}\n\n"
                    if update.get("hitl_pending"):
                        payload = update.get("hitl_payload") or {}
                        conn = get_conn()
                        conn.execute(
                            "INSERT INTO hitl_queue (thread_id, anomaly_type, description, status, created_at) "
                            "VALUES (?,?,?,?,?)",
                            (
                                thread_id,
                                "anomaly",
                                payload.get("message", ""),
                                "pending",
                                datetime.utcnow().isoformat(),
                            ),
                        )
                        conn.commit()
                        conn.close()
                        yield f"data: {json.dumps({'type': 'hitl_alert', 'payload': payload, 'thread_id': thread_id})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
