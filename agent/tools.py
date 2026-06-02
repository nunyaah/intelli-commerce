import json
import os
import statistics
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/app")
from shared.db import get_conn

import redis as redis_lib
import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from langchain_core.tools import tool

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
CHROMA_HOST = os.environ.get("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))

_redis = None
_collection = None
_ef = ONNXMiniLM_L6_V2()


def _redis_client():
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(REDIS_URL)
    return _redis


def _chroma_collection():
    global _collection
    if _collection is None:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        _collection = client.get_or_create_collection("tickets", embedding_function=_ef)
    return _collection


def _cached(key: str, fn, ttl: int = 60) -> str:
    r = _redis_client()
    hit = r.get(key)
    if hit:
        return hit.decode()
    result = fn()
    r.setex(key, ttl, result)
    return result


@tool
def query_orders(sql: str) -> str:
    """Run a read-only SQL SELECT against the orders table.
    Use for revenue analysis, order counts, product performance, fraud stats."""
    if not sql.strip().upper().startswith("SELECT"):
        return "Error: only SELECT statements are permitted."

    def run():
        conn = get_conn()
        try:
            cur = conn.execute(sql)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchmany(50)]
            return json.dumps(rows, default=str)
        except Exception as e:
            return f"Query error: {e}"
        finally:
            conn.close()

    return _cached(f"sql:{sql}", run)


@tool
def search_tickets(query: str, k: int = 4) -> str:
    """Semantic search over support tickets using embeddings.
    Use for questions about customer complaints, support patterns, or specific issues."""

    def run():
        try:
            results = _chroma_collection().query(query_texts=[query], n_results=min(k, 10))
            if not results["documents"][0]:
                return "No tickets found."
            out = []
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                out.append(f"[{meta['category'].upper()} / {meta['urgency']}] {doc}")
            return "\n\n".join(out)
        except Exception as e:
            return f"Search error: {e}"

    return _cached(f"tickets:{query}:{k}", run, ttl=30)


@tool
def get_metrics(period: str) -> str:
    """Get aggregated KPIs for a time window.
    period must be one of: 'today', 'last_hour', 'last_7_days'."""

    def run():
        conn = get_conn()
        now = datetime.utcnow()
        if period == "last_hour":
            since = (now - timedelta(hours=1)).isoformat()
        elif period == "today":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        else:
            since = (now - timedelta(days=7)).isoformat()

        o = conn.execute(
            "SELECT COALESCE(SUM(total),0) rev, COUNT(*) cnt, COALESCE(AVG(total),0) avg, "
            "COALESCE(SUM(is_fraud),0) fraud FROM orders WHERE created_at >= ?",
            (since,),
        ).fetchone()
        t = conn.execute(
            "SELECT COUNT(*) cnt, COALESCE(SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END),0) res "
            "FROM tickets WHERE created_at >= ?",
            (since,),
        ).fetchone()
        conn.close()

        res_rate = round((t["res"] / t["cnt"] * 100) if t["cnt"] else 0, 1)
        return json.dumps({
            "period": period,
            "revenue": round(o["rev"], 2),
            "order_count": o["cnt"],
            "avg_order_value": round(o["avg"], 2),
            "fraud_count": o["fraud"],
            "ticket_count": t["cnt"],
            "resolution_rate_pct": res_rate,
        })

    return _cached(f"metrics:{period}", run)


@tool
def detect_anomaly(metric: str) -> str:
    """Detect anomalies using z-score over the last 24 hourly buckets.
    metric: 'revenue' | 'tickets' | 'refunds'
    Returns current value, mean, z-score, and severity status."""

    def run():
        conn = get_conn()
        col_map = {"revenue": "revenue", "tickets": "ticket_count", "refunds": "refund_count"}
        col = col_map.get(metric)
        if not col:
            conn.close()
            return json.dumps({"error": "metric must be: revenue, tickets, refunds"})

        rows = conn.execute(
            f"SELECT {col} FROM kpi_hourly ORDER BY hour DESC LIMIT 24"
        ).fetchall()
        conn.close()

        values = [r[0] for r in rows if r[0] is not None]
        if len(values) < 3:
            return json.dumps({"metric": metric, "status": "insufficient_data"})

        mean = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 1.0
        current = values[0]
        z = round((current - mean) / std if std else 0, 2)
        status = "critical" if abs(z) > 3 else "warning" if abs(z) > 2 else "normal"

        return json.dumps({
            "metric": metric,
            "current_value": round(current, 2),
            "mean": round(mean, 2),
            "z_score": z,
            "status": status,
            "is_anomaly": abs(z) > 2,
        })

    return _cached(f"anomaly:{metric}", run, ttl=30)


@tool
def web_search(query: str) -> str:
    """Search the web for industry benchmarks or external context.
    Use when internal data alone is insufficient."""

    def run():
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            if not results:
                return "No results found."
            return "\n\n".join(f"{r['title']}: {r['body']}" for r in results)
        except Exception as e:
            return f"Web search failed: {e}"

    return _cached(f"web:{query}", run, ttl=300)


TOOLS = [query_orders, search_tickets, get_metrics, detect_anomaly, web_search]
