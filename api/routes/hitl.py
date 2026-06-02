import sys
from datetime import datetime

sys.path.insert(0, "/app")

from fastapi import APIRouter
from pydantic import BaseModel

from shared.db import get_conn

router = APIRouter()


class ActionBody(BaseModel):
    action: str  # approve | dismiss | escalate


@router.get("/hitl/queue")
def queue():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM hitl_queue WHERE status = 'pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/hitl/{item_id}/resolve")
def resolve(item_id: int, body: ActionBody):
    conn = get_conn()
    conn.execute(
        "UPDATE hitl_queue SET status = 'resolved', action = ?, resolved_at = ? WHERE id = ?",
        (body.action, datetime.utcnow().isoformat(), item_id),
    )
    conn.commit()
    conn.close()
    return {"status": "resolved", "action": body.action}
