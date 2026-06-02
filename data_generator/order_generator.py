import uuid
import random
import time
from datetime import datetime
import sys

sys.path.insert(0, "/app")
from shared.db import get_conn, init_db

from faker import Faker

fake = Faker()

PRODUCTS = [
    {"id": "P001", "name": "Wireless Headphones", "category": "Electronics", "base_price": 89.99},
    {"id": "P002", "name": "Running Shoes", "category": "Sports", "base_price": 129.99},
    {"id": "P003", "name": "Coffee Maker", "category": "Home", "base_price": 59.99},
    {"id": "P004", "name": "Yoga Mat", "category": "Sports", "base_price": 34.99},
    {"id": "P005", "name": "Laptop Stand", "category": "Electronics", "base_price": 49.99},
    {"id": "P006", "name": "Water Bottle", "category": "Sports", "base_price": 24.99},
    {"id": "P007", "name": "Desk Lamp", "category": "Home", "base_price": 39.99},
    {"id": "P008", "name": "Backpack", "category": "Accessories", "base_price": 79.99},
    {"id": "P009", "name": "Smart Watch", "category": "Electronics", "base_price": 249.99},
    {"id": "P010", "name": "Bluetooth Speaker", "category": "Electronics", "base_price": 69.99},
]

REGIONS = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East"]
PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "apple_pay", "bank_transfer"]


def generate_order():
    product = random.choice(PRODUCTS)
    quantity = random.randint(1, 5)
    price = product["base_price"] * random.uniform(0.9, 1.1)
    total = price * quantity
    is_fraud = random.random() < 0.02
    region = random.choice(REGIONS)

    risk_score = 0.0
    if total > 400:
        risk_score += 0.3
    if is_fraud:
        risk_score += 0.5
    if region in ["Middle East", "Latin America"] and total > 200:
        risk_score += 0.2
    risk_score = min(risk_score, 1.0)

    return {
        "id": str(uuid.uuid4()),
        "user_id": f"U{random.randint(1000, 9999)}",
        "product_id": product["id"],
        "product_name": product["name"],
        "category": product["category"],
        "price": round(price, 2),
        "quantity": quantity,
        "total": round(total, 2),
        "region": region,
        "payment_method": random.choice(PAYMENT_METHODS),
        "is_fraud": 1 if is_fraud else 0,
        "risk_score": round(risk_score, 3),
        "status": "completed",
        "created_at": datetime.utcnow().isoformat(),
        "processed_at": None,
    }


def run():
    init_db()
    print("Order generator started", flush=True)
    while True:
        order = generate_order()
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO orders (id, user_id, product_id, product_name, category, price,
                quantity, total, region, payment_method, is_fraud, risk_score, status, created_at)
            VALUES (:id, :user_id, :product_id, :product_name, :category, :price,
                :quantity, :total, :region, :payment_method, :is_fraud, :risk_score, :status, :created_at)
        """,
            order,
        )
        conn.commit()
        conn.close()

        hour = datetime.utcnow().hour
        delay = random.uniform(0.3, 1.5) if hour in range(18, 22) else random.uniform(0.5, 3.0)
        time.sleep(delay)


if __name__ == "__main__":
    run()
