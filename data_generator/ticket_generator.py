import uuid
import random
import time
from datetime import datetime
import sys

sys.path.insert(0, "/app")
from shared.db import get_conn, init_db

TICKET_TEMPLATES = {
    "delivery": [
        "My order hasn't arrived yet. It's been {days} days since it was supposed to arrive.",
        "Package was marked as delivered but I never received it.",
        "Wrong item was delivered to my address.",
        "Delivery arrived damaged.",
    ],
    "refund": [
        "I'd like to request a refund for my recent purchase.",
        "Product didn't match the description, need a full refund.",
        "I was charged twice for the same order.",
        "Item is defective and I need a refund.",
    ],
    "product": [
        "The product stopped working after {days} days of use.",
        "My order arrived with missing accessories.",
        "Product quality is much lower than advertised.",
        "The size/color doesn't match what I ordered.",
    ],
    "billing": [
        "I was overcharged for my recent order.",
        "My promo code didn't apply correctly at checkout.",
        "My subscription renewed even though I cancelled it.",
        "Payment was declined but money was still deducted.",
    ],
    "technical": [
        "The app keeps crashing when I try to complete checkout.",
        "I cannot log into my account.",
        "Getting a 500 error on the payment page.",
        "Search results are not showing the right products.",
    ],
}

URGENCY_MAP = {
    "low": {"weight": 0.3, "resolution_range": (1440, 4320), "sentiment_range": (0.0, 0.4)},
    "medium": {"weight": 0.45, "resolution_range": (120, 1440), "sentiment_range": (-0.2, 0.2)},
    "high": {"weight": 0.2, "resolution_range": (30, 120), "sentiment_range": (-0.6, -0.1)},
    "critical": {"weight": 0.05, "resolution_range": (5, 30), "sentiment_range": (-1.0, -0.5)},
}


def generate_ticket(order_ids):
    category = random.choice(list(TICKET_TEMPLATES.keys()))
    template = random.choice(TICKET_TEMPLATES[category])
    message = template.format(days=random.randint(1, 14))

    urgency = random.choices(
        list(URGENCY_MAP.keys()),
        weights=[v["weight"] for v in URGENCY_MAP.values()],
    )[0]

    meta = URGENCY_MAP[urgency]
    resolution_time = random.randint(*meta["resolution_range"])
    sentiment = round(random.uniform(*meta["sentiment_range"]), 3)

    return {
        "id": str(uuid.uuid4()),
        "order_id": random.choice(order_ids) if order_ids else None,
        "user_id": f"U{random.randint(1000, 9999)}",
        "category": category,
        "urgency": urgency,
        "subject": f"{category.title()} Issue",
        "message": message,
        "sentiment": sentiment,
        "status": random.choice(["open", "open", "in_progress", "resolved"]),
        "resolution_time_minutes": resolution_time,
        "created_at": datetime.utcnow().isoformat(),
        "processed_at": None,
    }


def run():
    init_db()
    print("Ticket generator started", flush=True)
    while True:
        conn = get_conn()
        order_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM orders ORDER BY RANDOM() LIMIT 20"
            ).fetchall()
        ]
        ticket = generate_ticket(order_ids)
        conn.execute(
            """
            INSERT INTO tickets (id, order_id, user_id, category, urgency, subject, message,
                sentiment, status, resolution_time_minutes, created_at)
            VALUES (:id, :order_id, :user_id, :category, :urgency, :subject, :message,
                :sentiment, :status, :resolution_time_minutes, :created_at)
        """,
            ticket,
        )
        conn.commit()
        conn.close()
        time.sleep(random.uniform(2, 8))


if __name__ == "__main__":
    run()
