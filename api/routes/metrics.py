import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/app")

from fastapi import APIRouter

from shared.db import get_conn

router = APIRouter()


@router.get("/metrics/kpis")
def kpis():
    conn = get_conn()
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    o = conn.execute(
        "SELECT COALESCE(SUM(total),0) rev, COUNT(*) cnt, COALESCE(AVG(total),0) avg, "
        "COALESCE(SUM(is_fraud),0) fraud FROM orders WHERE created_at >= ?",
        (today,),
    ).fetchone()
    t = conn.execute(
        "SELECT COUNT(*) cnt, COALESCE(SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END),0) res, "
        "COALESCE(AVG(resolution_time_minutes),0) avg_res FROM tickets WHERE created_at >= ?",
        (today,),
    ).fetchone()
    conn.close()

    return {
        "revenue_today": round(o["rev"], 2),
        "orders_today": o["cnt"],
        "avg_order_value": round(o["avg"], 2),
        "fraud_flags": o["fraud"],
        "tickets_open": max(0, t["cnt"] - t["res"]),
        "avg_resolution_minutes": round(t["avg_res"], 0),
    }


@router.get("/metrics/revenue-chart")
def revenue_chart():
    conn = get_conn()
    rows = conn.execute(
        "SELECT hour, revenue, order_count FROM kpi_hourly ORDER BY hour DESC LIMIT 48"
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


@router.get("/metrics/tickets-by-category")
def tickets_by_category():
    conn = get_conn()
    rows = conn.execute(
        "SELECT category, COUNT(*) as count FROM tickets "
        "WHERE created_at >= datetime('now', '-24 hours') GROUP BY category"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/metrics/anomalies")
def anomalies():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM anomaly_events ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/metrics/order-heatmap")
def order_heatmap():
    conn = get_conn()
    rows = conn.execute(
        "SELECT strftime('%w', created_at) day, strftime('%H', created_at) hour, COUNT(*) count "
        "FROM orders WHERE created_at >= datetime('now', '-7 days') GROUP BY day, hour"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
