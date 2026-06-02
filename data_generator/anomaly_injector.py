import time
import random
from datetime import datetime
import sys

sys.path.insert(0, "/app")
from shared.db import get_conn, init_db

ANOMALIES = {
    "revenue_spike": {
        "description": "Unusual revenue spike detected — possible flash sale or bot activity",
        "severity": "warning",
    },
    "refund_surge": {
        "description": "Refund rate exceeded 15% — possible product defect or policy abuse",
        "severity": "critical",
    },
    "ticket_flood": {
        "description": "Support ticket volume is 3x normal — possible service outage",
        "severity": "critical",
    },
    "fraud_cluster": {
        "description": "Fraud rate spike detected — possible coordinated bot attack",
        "severity": "critical",
    },
}


def inject_anomaly():
    anomaly_type = random.choice(list(ANOMALIES.keys()))
    meta = ANOMALIES[anomaly_type]
    metric_value = round(random.uniform(2.5, 8.0), 2)

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO anomaly_events (type, description, severity, metric_value, created_at)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            anomaly_type,
            meta["description"],
            meta["severity"],
            metric_value,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    print(f"Anomaly injected: {anomaly_type} severity={meta['severity']}", flush=True)


def run():
    init_db()
    print("Anomaly injector started", flush=True)
    while True:
        time.sleep(random.uniform(180, 360))
        inject_anomaly()


if __name__ == "__main__":
    run()
