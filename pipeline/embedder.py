import os
import sys

sys.path.insert(0, "/app")
from shared.db import get_conn

import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

CHROMA_HOST = os.environ.get("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))

_collection = None
_ef = ONNXMiniLM_L6_V2()


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        _collection = client.get_or_create_collection("tickets", embedding_function=_ef)
    return _collection


def embed_new_tickets():
    conn = get_conn()
    tickets = conn.execute(
        """
        SELECT id, subject, message, category, urgency, sentiment
        FROM tickets
        WHERE processed_at IS NOT NULL
        ORDER BY processed_at DESC
        LIMIT 50
        """
    ).fetchall()
    conn.close()

    if not tickets:
        return

    col = _get_collection()
    try:
        existing = set(col.get(ids=[t["id"] for t in tickets])["ids"])
    except Exception:
        existing = set()

    new_tickets = [t for t in tickets if t["id"] not in existing]
    if not new_tickets:
        return

    texts = [f"{t['subject']}: {t['message']}" for t in new_tickets]

    col.add(
        ids=[t["id"] for t in new_tickets],
        documents=texts,
        metadatas=[
            {"category": t["category"], "urgency": t["urgency"], "sentiment": str(t["sentiment"])}
            for t in new_tickets
        ],
    )
    print(f"Embedded {len(new_tickets)} tickets into ChromaDB", flush=True)
