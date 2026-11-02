import concurrent.futures
import csv
import os
import time

import requests  # pip install requests

BASE_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/orders/")

NUM_REQUESTS = 50
ACCOUNT_ID = 106
INSTRUMENT_ID = 1  # RELIANCE
TICK = 0.05

PRICE_BARS_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "data_pipeline", "seed_csvs", "price_bars.csv",
)


def load_spot(instrument_id: int) -> float:
    """Latest close for the instrument from the seeded data (override with SPOT env var)."""
    if os.getenv("SPOT"):
        return float(os.environ["SPOT"])
    latest = None
    with open(PRICE_BARS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["Instrument_id"]) == instrument_id:
                if latest is None or row["Trade_date"] > latest[0]:
                    latest = (row["Trade_date"], float(row["Close"]))
    if latest is None:
        raise RuntimeError(f"No price bars found for instrument {instrument_id}")
    return latest[1]


def tick_round(x: float) -> float:
    return round(round(x / TICK) * TICK, 2)


SPOT = load_spot(INSTRUMENT_ID)
BUY_PRICE = tick_round(SPOT * 1.005)   # bids above spot
SELL_PRICE = tick_round(SPOT * 0.995)  # asks below spot -> orders cross and match


def send_order(order_index: int):
    """Alternates BUY and SELL so the matching engine's locking is exercised."""
    side = "BUY" if order_index % 2 == 0 else "SELL"
    payload = {
        "account_id": ACCOUNT_ID,
        "instrument_id": INSTRUMENT_ID,
        "side": side,
        "price": BUY_PRICE if side == "BUY" else SELL_PRICE,
        "qty": 1.0,
    }

    start_time = time.time()
    try:
        response = requests.post(BASE_URL, json=payload, timeout=10)
        elapsed = round((time.time() - start_time) * 1000, 2)
        return {
            "order_index": order_index,
            "status_code": response.status_code,
            "elapsed_ms": elapsed,
            "data": response.json() if response.status_code in (200, 201) else response.text,
        }
    except Exception as e:
        return {"order_index": order_index, "status_code": 500, "elapsed_ms": 0, "data": str(e)}


def run_stress_test():
    print(f"--- Launching {NUM_REQUESTS} parallel orders to {BASE_URL} ---")
    print(f"Spot {SPOT}  |  BUY @ {BUY_PRICE}  |  SELL @ {SELL_PRICE}")
    start_total = time.time()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(send_order, i) for i in range(1, NUM_REQUESTS + 1)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    total_time = round(time.time() - start_total, 2)
    successes = sum(1 for r in results if r["status_code"] in (200, 201))
    failures = len(results) - successes
    avg_latency = round(sum(r["elapsed_ms"] for r in results) / len(results), 2)

    print("\n================ CONCURRENCY TEST SUMMARY ================")
    print(f"Total Time Taken    : {total_time} seconds")
    print(f"Successful Requests : {successes} / {NUM_REQUESTS}")
    print(f"Failed Requests     : {failures} / {NUM_REQUESTS}")
    print(f"Average Latency     : {avg_latency} ms")
    print("==========================================================")

    if failures > 0:
        print("\nSample Error Responses:")
        for r in results:
            if r["status_code"] not in (200, 201):
                print(f"Order #{r['order_index']} Failed: {r['data']}")
                break


if __name__ == "__main__":
    run_stress_test()