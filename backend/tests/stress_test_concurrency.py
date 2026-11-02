import concurrent.futures
import time
import requests

# API Endpoint URL
BASE_URL = "http://127.0.0.1:8000/api/orders/"

# Test Config: 50 concurrent requests targeting account 106 and instrument 1
NUM_REQUESTS = 50
ACCOUNT_ID = 106
INSTRUMENT_ID = 1

def send_order(order_index: int):
    """
    Sends an individual BUY or SELL order to the API.
    Alternates between BUY and SELL to force matching engine lock conditions.
    """
    side = "BUY" if order_index % 2 == 0 else "SELL"
    price = 2500.0 if side == "BUY" else 2480.0
    
    payload = {
        "account_id": ACCOUNT_ID,
        "instrument_id": INSTRUMENT_ID,
        "side": side,
        "price": price,
        "qty": 1.0
    }
    
    start_time = time.time()
    try:
        response = requests.post(BASE_URL, json=payload, timeout=10)
        elapsed = round((time.time() - start_time) * 1000, 2)
        return {
            "order_index": order_index,
            "status_code": response.status_code,
            "elapsed_ms": elapsed,
            "data": response.json() if response.status_code in (200, 201) else response.text
        }
    except Exception as e:
        return {
            "order_index": order_index,
            "status_code": 500,
            "elapsed_ms": 0,
            "data": str(e)
        }

def run_stress_test():
    print(f"--- Launching {NUM_REQUESTS} Parallel Orders to {BASE_URL} ---")
    start_total = time.time()
    
    results = []
    # Execute 50 requests in parallel threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(send_order, i) for i in range(1, NUM_REQUESTS + 1)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    total_time = round(time.time() - start_total, 2)
    
    # Calculate performance metrics
    successes = sum(1 for r in results if r["status_code"] in (200, 201))
    failures = sum(1 for r in results if r["status_code"] not in (200, 201))
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