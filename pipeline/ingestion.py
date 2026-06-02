from datetime import datetime
import sys

sys.path.insert(0, "/app")
from shared.db import get_conn


def process_new_orders():
    conn = get_conn()
    orders = conn.execute(
        "SELECT id FROM orders WHERE processed_at IS NULL LIMIT 100"
    ).fetchall()
    if orders:
        ids = [r[0] for r in orders]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE orders SET processed_at = ? WHERE id IN ({placeholders})",
            [datetime.utcnow().isoformat()] + ids,
        )
        conn.commit()
        print(f"Ingested {len(orders)} orders", flush=True)
    conn.close()


def process_new_tickets():
    conn = get_conn()
    tickets = conn.execute(
        "SELECT id FROM tickets WHERE processed_at IS NULL LIMIT 50"
    ).fetchall()
    if tickets:
        ids = [r[0] for r in tickets]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE tickets SET processed_at = ? WHERE id IN ({placeholders})",
            [datetime.utcnow().isoformat()] + ids,
        )
        conn.commit()
        print(f"Ingested {len(tickets)} tickets", flush=True)
    conn.close()
