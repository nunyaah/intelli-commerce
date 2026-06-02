import threading
import sys

sys.path.insert(0, "/app")

from data_generator import order_generator, ticket_generator, anomaly_injector

if __name__ == "__main__":
    threads = [
        threading.Thread(target=order_generator.run, daemon=True),
        threading.Thread(target=ticket_generator.run, daemon=True),
        threading.Thread(target=anomaly_injector.run, daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
