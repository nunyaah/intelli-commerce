from datetime import datetime, timedelta
import sys

sys.path.insert(0, "/app")
from shared.db import get_conn


def aggregate_kpis():
    conn = get_conn()
    now = datetime.utcnow()
    hour_str = now.strftime("%Y-%m-%dT%H:00:00")
    hour_start = now.replace(minute=0, second=0, microsecond=0).isoformat()
    hour_end = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).isoformat()

    o = conn.execute(
        """
        SELECT
            COALESCE(SUM(total), 0)       AS revenue,
            COUNT(*)                       AS order_count,
            COALESCE(AVG(total), 0)        AS avg_order_value,
            COALESCE(SUM(is_fraud), 0)     AS fraud_count,
            COALESCE(SUM(CASE WHEN status = 'refunded' THEN 1 ELSE 0 END), 0) AS refund_count
        FROM orders
        WHERE created_at >= ? AND created_at < ?
        """,
        (hour_start, hour_end),
    ).fetchone()

    t = conn.execute(
        """
        SELECT
            COUNT(*) AS ticket_count,
            COALESCE(SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END), 0) AS resolved_tickets
        FROM tickets
        WHERE created_at >= ? AND created_at < ?
        """,
        (hour_start, hour_end),
    ).fetchone()

    conn.execute(
        """
        INSERT INTO kpi_hourly
            (hour, revenue, order_count, avg_order_value, ticket_count, resolved_tickets, fraud_count, refund_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hour) DO UPDATE SET
            revenue          = excluded.revenue,
            order_count      = excluded.order_count,
            avg_order_value  = excluded.avg_order_value,
            ticket_count     = excluded.ticket_count,
            resolved_tickets = excluded.resolved_tickets,
            fraud_count      = excluded.fraud_count,
            refund_count     = excluded.refund_count
        """,
        (
            hour_str,
            o["revenue"],
            o["order_count"],
            o["avg_order_value"],
            t["ticket_count"],
            t["resolved_tickets"],
            o["fraud_count"],
            o["refund_count"],
        ),
    )
    conn.commit()
    conn.close()
