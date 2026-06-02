import time
import sys

sys.path.insert(0, "/app")

from pipeline.ingestion import process_new_orders, process_new_tickets
from pipeline.aggregator import aggregate_kpis
from pipeline.embedder import embed_new_tickets


def run():
    print("Pipeline service started", flush=True)
    while True:
        try:
            process_new_orders()
            process_new_tickets()
            aggregate_kpis()
            embed_new_tickets()
        except Exception as e:
            print(f"Pipeline error: {e}", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    run()
