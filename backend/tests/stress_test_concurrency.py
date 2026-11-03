"""
Concurrency stress test for the paper-trading exchange.

What it does
  1. Snapshots total cash, total shares and the highest order_id.
  2. Fires many parallel LIMIT orders at one instrument:
       - the HOUSE account (101) places SELLs, accounts 102-106 rotate as BUYers,
         so nobody trades with themselves and every order crosses.
  3. Reads the database again and checks the invariants:
       I1  total cash across all accounts is unchanged
       I2  total shares of the instrument across all accounts is unchanged
       I3  no account has negative cash and no position is negative
       I4  no order is overfilled (filled_qty <= qty)
       I5  shares bought == shares sold, summed over the orders from this run

Modes
  python stress_test_concurrency.py            safe mode (match_and_settle, with FOR UPDATE)
  python stress_test_concurrency.py --unsafe   sends ?unsafe=true so the backend calls
                                               match_and_settle_unsafe (no row locks).
                                               The invariants should BREAK. That is the demo.

Setup
  pip install requests "psycopg[binary]"
  Stack must be running (docker compose up). DB is read via DB_* env vars,
  defaulting to localhost:5432 as exposed by docker-compose.
"""
import argparse
import concurrent.futures
import csv
import os
import time

import psycopg
import requests

BASE_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/orders/")

DB_CONN = (
    f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'postgrespassword')}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'papertrading')}"
)

NUM_REQUESTS = 50
QTY = 1.0
SELLER_ACCOUNT = 101                      # house account holds the inventory
BUYER_ACCOUNTS = [102, 103, 104, 105, 106]
INSTRUMENT_ID = 1                         # RELIANCE
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
BUY_PRICE = tick_round(SPOT * 1.005)    # bids above spot
SELL_PRICE = tick_round(SPOT * 0.995)   # asks below spot -> every pair crosses


# ----------------------------------------------------------------------------
# Database snapshots and invariant checks
# ----------------------------------------------------------------------------

def snapshot():
    with psycopg.connect(DB_CONN) as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(cash_balance), 0) FROM ACCOUNT;")
        total_cash = float(cur.fetchone()[0])
        cur.execute("SELECT COALESCE(SUM(quantity), 0) FROM POSITION WHERE instrument_id = %s;", (INSTRUMENT_ID,))
        total_shares = float(cur.fetchone()[0])
        cur.execute('SELECT COALESCE(MAX(order_id), 0) FROM "ORDER";')
        max_order = int(cur.fetchone()[0])
    return {"cash": total_cash, "shares": total_shares, "max_order": max_order}


def check_invariants(before, after):
    results = []

    def add(name, ok, detail):
        results.append((name, ok, detail))

    add("I1 total cash unchanged",
        abs(after["cash"] - before["cash"]) < 0.01,
        f"before={before['cash']:.2f} after={after['cash']:.2f} diff={after['cash'] - before['cash']:.2f}")
    add("I2 total shares unchanged",
        abs(after["shares"] - before["shares"]) < 1e-6,
        f"before={before['shares']} after={after['shares']} diff={after['shares'] - before['shares']}")

    with psycopg.connect(DB_CONN) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ACCOUNT WHERE cash_balance < 0;")
        neg_cash = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM POSITION WHERE quantity < 0;")
        neg_pos = cur.fetchone()[0]
        add("I3 no negative cash or shares", neg_cash == 0 and neg_pos == 0,
            f"accounts with negative cash={neg_cash}, negative positions={neg_pos}")

        cur.execute('SELECT COUNT(*) FROM "ORDER" WHERE filled_qty > qty;')
        overfilled = cur.fetchone()[0]
        add("I4 no overfilled order", overfilled == 0, f"overfilled orders={overfilled}")

        cur.execute(
            """
            SELECT COALESCE(SUM(filled_qty) FILTER (WHERE side = 'BUY'), 0),
                   COALESCE(SUM(filled_qty) FILTER (WHERE side = 'SELL'), 0)
            FROM "ORDER" WHERE order_id > %s AND instrument_id = %s;
            """,
            (before["max_order"], INSTRUMENT_ID),
        )
        bought, sold = (float(x) for x in cur.fetchone())
        add("I5 shares bought == shares sold", abs(bought - sold) < 1e-6, f"bought={bought} sold={sold}")

    return results


# ----------------------------------------------------------------------------
# Load generation
# ----------------------------------------------------------------------------

def send_order(order_index: int, unsafe: bool):
    """Even index = house SELL, odd index = BUY from a rotating buyer account."""
    if order_index % 2 == 0:
        side, account, price = "SELL", SELLER_ACCOUNT, SELL_PRICE
    else:
        side = "BUY"
        account = BUYER_ACCOUNTS[(order_index // 2) % len(BUYER_ACCOUNTS)]
        price = BUY_PRICE

    payload = {
        "account_id": account,
        "instrument_id": INSTRUMENT_ID,
        "side": side,
        "price": price,
        "qty": QTY,
    }
    params = {"unsafe": "true"} if unsafe else None

    start = time.time()
    try:
        r = requests.post(BASE_URL, json=payload, params=params, timeout=15)
        elapsed = round((time.time() - start) * 1000, 2)
        return {"status_code": r.status_code, "elapsed_ms": elapsed,
                "data": r.json() if r.status_code in (200, 201) else r.text}
    except Exception as e:
        return {"status_code": 500, "elapsed_ms": 0, "data": str(e)}


def run(unsafe: bool):
    mode = "UNSAFE (no row locks)" if unsafe else "SAFE (FOR UPDATE locking)"
    print(f"--- {NUM_REQUESTS} parallel orders -> {BASE_URL}  [{mode}] ---")
    print(f"Spot {SPOT} | BUY @ {BUY_PRICE} | SELL @ {SELL_PRICE} | qty {QTY} each")

    before = snapshot()
    start_total = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(send_order, i, unsafe) for i in range(NUM_REQUESTS)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    total_time = round(time.time() - start_total, 2)

    ok = sum(1 for r in results if r["status_code"] in (200, 201))
    avg = round(sum(r["elapsed_ms"] for r in results) / len(results), 2)
    after = snapshot()
    checks = check_invariants(before, after)

    print("\n================ CONCURRENCY TEST SUMMARY ================")
    print(f"Mode                : {mode}")
    print(f"Total time          : {total_time} s")
    print(f"Requests OK / failed: {ok} / {len(results) - ok}")
    print(f"Average latency     : {avg} ms")
    print("---------------- INVARIANTS ----------------")
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}  ({detail})")
    print("==========================================================")

    failures = [r for r in results if r["status_code"] not in (200, 201)]
    if failures:
        print(f"\nSample error: {failures[0]['data']}")

    all_ok = all(p for _, p, _ in checks)
    if unsafe:
        print("\nExpected in unsafe mode: at least one FAIL above."
              if not all_ok else
              "\nNo invariant broke this time. Re-run, raise NUM_REQUESTS, or check that the unsafe procedure really skips FOR UPDATE.")
    else:
        print("\nAll invariants hold." if all_ok else "\nBUG: an invariant broke in safe mode.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--unsafe", action="store_true", help="call the lock-free procedure to demonstrate failures")
    raise SystemExit(run(ap.parse_args().unsafe))