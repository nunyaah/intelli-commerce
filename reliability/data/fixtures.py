"""Deterministic fixture database for reproducible offline evals.

Builds a self-contained commerce DB (orders / tickets / kpi_hourly /
anomaly_events) with fixed, hand-tuned data so that:
  * get_metrics / query_orders return stable values,
  * detect_anomaly('revenue') reports a *critical* spike (drives the HITL case),
  * search_tickets (keyword fallback) returns real ticket text.

Timestamps are anchored to "now" at build time, so every row falls inside the
today / last_hour / last_7_days windows regardless of when the suite runs —
making metric totals reproducible run-to-run.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

# (product_name, category, price, quantity, is_fraud, status)
_ORDERS = [
    ("Wireless Earbuds", "electronics", 79.99, 1, 0, "completed"),
    ("Yoga Mat", "fitness", 29.99, 2, 0, "completed"),
    ("Coffee Maker", "home", 119.50, 1, 0, "completed"),
    ("Running Shoes", "fitness", 89.00, 1, 0, "completed"),
    ("Desk Lamp", "home", 34.25, 3, 0, "completed"),
    ("Bluetooth Speaker", "electronics", 59.99, 1, 0, "refunded"),
    ("Water Bottle", "fitness", 19.99, 4, 0, "completed"),
    ("Mechanical Keyboard", "electronics", 109.00, 1, 0, "completed"),
    ("Standing Desk", "home", 399.00, 1, 1, "completed"),
    ("Phone Case", "electronics", 14.99, 2, 0, "completed"),
    ("Dumbbell Set", "fitness", 149.00, 1, 0, "completed"),
    ("Air Purifier", "home", 199.99, 1, 0, "refunded"),
    ("Smart Watch", "electronics", 249.00, 1, 1, "completed"),
    ("Resistance Bands", "fitness", 24.99, 3, 0, "completed"),
    ("Blender", "home", 79.00, 1, 0, "completed"),
    ("Wireless Mouse", "electronics", 39.99, 2, 0, "completed"),
    ("Foam Roller", "fitness", 27.50, 1, 0, "completed"),
    ("Table Fan", "home", 49.99, 2, 0, "completed"),
    ("USB-C Charger", "electronics", 22.99, 3, 0, "completed"),
    ("Kettlebell", "fitness", 64.00, 1, 0, "completed"),
]

# (category, urgency, subject, message, status, resolution_minutes)
_TICKETS = [
    ("delivery", "high", "Package not delivered", "My order is 5 days late and tracking hasn't updated. Delivery is very slow.", "open", None),
    ("delivery", "medium", "Wrong address", "The courier delivered to the wrong address, delivery problem.", "resolved", 120),
    ("refund", "high", "Refund not received", "I returned the item two weeks ago and still no refund processed.", "open", None),
    ("refund", "medium", "Partial refund", "I was only refunded part of my order total, refund issue.", "resolved", 240),
    ("product", "low", "Item defective", "The product arrived damaged and does not power on, defective product.", "open", None),
    ("product", "high", "Missing parts", "The standing desk is missing mounting screws, product incomplete.", "open", None),
    ("billing", "medium", "Double charged", "I was charged twice for the same order, billing error.", "resolved", 90),
    ("billing", "high", "Unexpected fee", "There is an extra fee on my invoice I did not authorise, billing dispute.", "open", None),
    ("technical", "low", "Cannot log in", "The website keeps logging me out, technical issue with login.", "resolved", 60),
    ("technical", "medium", "Checkout error", "Checkout fails at the payment step, technical error during checkout.", "open", None),
    ("delivery", "high", "Late delivery again", "Second time my delivery is delayed this month, slow delivery problem.", "open", None),
    ("refund", "low", "Refund status", "Just checking on the status of my refund request.", "resolved", 30),
]


def _conn(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, user_id TEXT, product_id TEXT, product_name TEXT,
    category TEXT, price REAL, quantity INTEGER, total REAL, region TEXT,
    payment_method TEXT, is_fraud INTEGER DEFAULT 0, risk_score REAL DEFAULT 0.0,
    status TEXT DEFAULT 'pending', created_at TEXT, processed_at TEXT
);
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY, order_id TEXT, user_id TEXT, category TEXT, urgency TEXT,
    subject TEXT, message TEXT, sentiment REAL DEFAULT 0.0, status TEXT DEFAULT 'open',
    resolution_time_minutes INTEGER, created_at TEXT, processed_at TEXT
);
CREATE TABLE IF NOT EXISTS kpi_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT, hour TEXT UNIQUE, revenue REAL DEFAULT 0.0,
    order_count INTEGER DEFAULT 0, avg_order_value REAL DEFAULT 0.0,
    ticket_count INTEGER DEFAULT 0, resolved_tickets INTEGER DEFAULT 0,
    fraud_count INTEGER DEFAULT 0, refund_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS anomaly_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, description TEXT, severity TEXT,
    metric_value REAL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS hitl_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT, anomaly_type TEXT,
    description TEXT, metric_value REAL, status TEXT DEFAULT 'pending', action TEXT,
    created_at TEXT, resolved_at TEXT
);
"""


def build_fixture_db(path: str) -> str:
    """(Re)build the deterministic fixture DB at ``path``. Returns the path."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(path):
        os.remove(path)

    # Naive UTC to match the agent code (which uses datetime.utcnow()).
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    conn = _conn(path)
    conn.executescript(_SCHEMA)

    # Orders: spread across the last 50 minutes so all sit inside last_hour/today.
    for i, (name, cat, price, qty, fraud, status) in enumerate(_ORDERS):
        ts = (now - timedelta(minutes=2 * i + 1)).isoformat()
        conn.execute(
            """INSERT INTO orders (id,user_id,product_id,product_name,category,price,
               quantity,total,region,payment_method,is_fraud,risk_score,status,created_at,processed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"o{i:03d}", f"u{i % 7:03d}", f"p{i:03d}", name, cat, price, qty,
             round(price * qty, 2), ["NA", "EU", "APAC"][i % 3],
             ["card", "paypal", "applepay"][i % 3], fraud, 0.2 * (i % 5),
             status, ts, ts),
        )

    # Tickets: spread across the last hour.
    for i, (cat, urg, subj, msg, status, res) in enumerate(_TICKETS):
        ts = (now - timedelta(minutes=3 * i + 1)).isoformat()
        conn.execute(
            """INSERT INTO tickets (id,order_id,user_id,category,urgency,subject,message,
               sentiment,status,resolution_time_minutes,created_at,processed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"t{i:03d}", f"o{i:03d}", f"u{i % 7:03d}", cat, urg, subj, msg,
             -0.3 if urg == "high" else 0.1, status, res, ts, ts),
        )

    # kpi_hourly: 24 buckets. The most recent hour is a deliberate revenue spike
    # so detect_anomaly('revenue') returns status=critical (z-score >> 3).
    for h in range(24):
        hour_dt = (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        hour_str = hour_dt.strftime("%Y-%m-%dT%H:00:00")
        if h == 0:
            revenue, oc, tc, fc, rc = 9800.0, 140, 9, 6, 2
        else:
            revenue = 980.0 + (h % 4) * 35.0   # tight band ~ mean 1032, low stdev
            oc, tc, fc, rc = 14 + (h % 3), 2 + (h % 2), h % 2, h % 2
        conn.execute(
            """INSERT OR REPLACE INTO kpi_hourly
               (hour,revenue,order_count,avg_order_value,ticket_count,resolved_tickets,fraud_count,refund_count)
               VALUES (?,?,?,?,?,?,?,?)""",
            (hour_str, revenue, oc, round(revenue / max(oc, 1), 2), tc, max(0, tc - 1), fc, rc),
        )

    conn.execute(
        "INSERT INTO anomaly_events (type,description,severity,metric_value,created_at) VALUES (?,?,?,?,?)",
        ("revenue_spike", "Revenue spike detected — 9.5x hourly mean", "critical", 9.5, now.isoformat()),
    )

    conn.commit()
    conn.close()
    return path


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(".reliability", "fixture.db")
    build_fixture_db(out)
    print(f"Fixture DB written to {out}")
