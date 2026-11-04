
"""
Concurrency stress test for the paper-trading exchange.

What it does:
  1. Snapshots total cash, total shares and the highest order_id.
  2. Sends 50 parallel LIMIT orders for one instrument:
       - HOUSE account (101) places SELL orders.
       - Accounts 102-106 rotate as BUYERS.
       - BUY prices are above SELL prices, so orders cross.
  3. Checks the database invariants after all requests finish.

Invariants:
  I1: Total cash across all accounts is unchanged.
  I2: Total shares of the instrument are unchanged.
  I3: No participating account has negative cash or shares.
  I4: No order created by this run is overfilled.
  I5: Shares bought == shares sold for orders created by this run.

Modes:
  Safe:
      python stress_test_concurrency.py

  Unsafe:
      python stress_test_concurrency.py --unsafe

Safe mode should preserve all invariants.
Unsafe mode should demonstrate a concurrency failure if the race
condition is reproduced.

Setup:
  pip install requests "psycopg[binary]"
  docker compose up

Environment variables:
  API_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, SPOT
"""

import argparse
import concurrent.futures
import csv
import os
import time

import psycopg
import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.getenv(
    "API_URL",
    "http://127.0.0.1:8000/api/orders/"
)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "papertrading"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgrespassword"),
    "connect_timeout": 10,
}

NUM_REQUESTS = 50
MAX_WORKERS = 10

QTY = 1.0

SELLER_ACCOUNT = 101
BUYER_ACCOUNTS = [102, 103, 104, 105, 106]

PARTICIPATING_ACCOUNTS = [
    SELLER_ACCOUNT,
    *BUYER_ACCOUNTS,
]

INSTRUMENT_ID = 1
TICK = 0.05

PRICE_BARS_CSV = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "data_pipeline",
        "seed_csvs",
        "price_bars.csv",
    )
)


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def get_connection():
    """Create a PostgreSQL connection using environment configuration."""
    return psycopg.connect(**DB_CONFIG)


# ---------------------------------------------------------------------------
# Price loading
# ---------------------------------------------------------------------------

def load_spot(instrument_id: int) -> float:
    """
    Get the latest closing price for an instrument.

    SPOT environment variable can override the CSV price.
    """

    if os.getenv("SPOT"):
        spot = float(os.environ["SPOT"])

        if spot <= 0:
            raise ValueError("SPOT must be greater than zero.")

        return spot

    if not os.path.exists(PRICE_BARS_CSV):
        raise FileNotFoundError(
            f"Price bars CSV not found: {PRICE_BARS_CSV}"
        )

    latest = None

    with open(
        PRICE_BARS_CSV,
        newline="",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            if int(row["Instrument_id"]) == instrument_id:

                trade_date = row["Trade_date"]
                close = float(row["Close"])

                if close <= 0:
                    continue

                if latest is None or trade_date > latest[0]:
                    latest = (trade_date, close)

    if latest is None:
        raise RuntimeError(
            f"No valid price bars found for instrument {instrument_id}"
        )

    return latest[1]


def tick_round(price: float) -> float:
    """Round a price to the nearest valid tick."""
    return round(round(price / TICK) * TICK, 2)


# ---------------------------------------------------------------------------
# Database snapshots
# ---------------------------------------------------------------------------

def snapshot():
    """
    Capture database state before or after the stress test.

    max_order is used to identify orders created during this run.
    """

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT COALESCE(SUM(cash_balance), 0)
                FROM ACCOUNT;
                """
            )

            total_cash = float(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM POSITION
                WHERE instrument_id = %s;
                """,
                (INSTRUMENT_ID,)
            )

            total_shares = float(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COALESCE(MAX(order_id), 0)
                FROM "ORDER";
                """
            )

            max_order = int(cur.fetchone()[0])

    return {
        "cash": total_cash,
        "shares": total_shares,
        "max_order": max_order,
    }


# ---------------------------------------------------------------------------
# Invariant checks
# ---------------------------------------------------------------------------

def check_invariants(before, after):
    """
    Check the five invariants.

    I3 checks the accounts participating in this test.
    I4 and I5 check only orders created during this run.
    """

    results = []

    def add(name, passed, detail):
        results.append((name, passed, detail))

    # I1: Total cash must remain unchanged.

    cash_diff = after["cash"] - before["cash"]

    add(
        "I1 Total cash unchanged",
        abs(cash_diff) < 0.01,
        (
            f"before={before['cash']:.2f}, "
            f"after={after['cash']:.2f}, "
            f"diff={cash_diff:.2f}"
        )
    )

    # I2: Total shares of the instrument must remain unchanged.

    shares_diff = after["shares"] - before["shares"]

    add(
        "I2 Total shares unchanged",
        abs(shares_diff) < 1e-6,
        (
            f"before={before['shares']}, "
            f"after={after['shares']}, "
            f"diff={shares_diff}"
        )
    )

    with get_connection() as conn:
        with conn.cursor() as cur:

            # I3: No participating account has negative cash
            # or negative quantity of the tested instrument.

            cur.execute(
                """
                SELECT COUNT(*)
                FROM ACCOUNT
                WHERE account_id = ANY(%s)
                  AND cash_balance < 0;
                """,
                (PARTICIPATING_ACCOUNTS,)
            )

            negative_cash = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM POSITION
                WHERE account_id = ANY(%s)
                  AND instrument_id = %s
                  AND quantity < 0;
                """,
                (PARTICIPATING_ACCOUNTS, INSTRUMENT_ID)
            )

            negative_positions = cur.fetchone()[0]

            add(
                "I3 No negative cash or shares",
                negative_cash == 0 and negative_positions == 0,
                (
                    f"negative cash accounts={negative_cash}, "
                    f"negative positions={negative_positions}"
                )
            )

            # I4: No order created during this run can be overfilled.

            cur.execute(
                """
                SELECT COUNT(*)
                FROM "ORDER"
                WHERE order_id > %s
                  AND filled_qty > qty;
                """,
                (before["max_order"],)
            )

            overfilled = cur.fetchone()[0]

            add(
                "I4 No overfilled orders",
                overfilled == 0,
                f"overfilled orders={overfilled}"
            )

            # I5: Total shares bought must equal total shares sold
            # for orders created during this run.

            cur.execute(
                """
                SELECT
                    COALESCE(
                        SUM(filled_qty)
                        FILTER (WHERE side = 'BUY'),
                        0
                    ),
                    COALESCE(
                        SUM(filled_qty)
                        FILTER (WHERE side = 'SELL'),
                        0
                    )
                FROM "ORDER"
                WHERE order_id > %s
                  AND instrument_id = %s;
                """,
                (before["max_order"], INSTRUMENT_ID)
            )

            bought, sold = cur.fetchone()

            bought = float(bought)
            sold = float(sold)

            add(
                "I5 Shares bought equal shares sold",
                abs(bought - sold) < 1e-6,
                f"bought={bought}, sold={sold}"
            )

    return results


def count_new_orders(max_order):
    """Count orders inserted after the initial snapshot."""

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT COUNT(*)
                FROM "ORDER"
                WHERE order_id > %s;
                """,
                (max_order,)
            )

            return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Parallel order submission
# ---------------------------------------------------------------------------

def send_order(
    order_index: int,
    unsafe: bool,
    buy_price: float,
    sell_price: float
):
    """
    Submit one order.

    Even index:
        HOUSE places SELL.

    Odd index:
        One of the five buyer accounts places BUY.
    """

    if order_index % 2 == 0:

        side = "SELL"
        account = SELLER_ACCOUNT
        price = sell_price

    else:

        side = "BUY"

        buyer_index = (
            order_index // 2
        ) % len(BUYER_ACCOUNTS)

        account = BUYER_ACCOUNTS[buyer_index]
        price = buy_price

    payload = {
        "account_id": account,
        "instrument_id": INSTRUMENT_ID,
        "side": side,
        "price": price,
        "qty": QTY,
    }

    params = {"unsafe": "true"} if unsafe else None

    start = time.perf_counter()

    try:

        response = requests.post(
            BASE_URL,
            json=payload,
            params=params,
            timeout=15
        )

        elapsed = round(
            (time.perf_counter() - start) * 1000,
            2
        )

        try:
            response_data = response.json()
        except ValueError:
            response_data = response.text

        return {
            "status_code": response.status_code,
            "elapsed_ms": elapsed,
            "data": response_data,
            "side": side,
            "account": account,
        }

    except requests.RequestException as error:

        elapsed = round(
            (time.perf_counter() - start) * 1000,
            2
        )

        return {
            "status_code": 0,
            "elapsed_ms": elapsed,
            "data": str(error),
            "side": side,
            "account": account,
        }


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

def run(unsafe: bool):

    mode = (
        "UNSAFE (without row locks)"
        if unsafe
        else "SAFE (with FOR UPDATE)"
    )

    # 50 requests means 25 SELL and 25 BUY orders.
    if NUM_REQUESTS % 2 != 0:
        raise ValueError("NUM_REQUESTS must be even.")

    spot = load_spot(INSTRUMENT_ID)

    buy_price = tick_round(spot * 1.005)
    sell_price = tick_round(spot * 0.995)

    if buy_price <= sell_price:
        raise ValueError("BUY price must be greater than SELL price.")

    print("\n======================================================")
    print("          CONCURRENCY STRESS TEST")
    print("======================================================")

    print(f"Mode          : {mode}")
    print(f"API           : {BASE_URL}")
    print(f"Instrument ID : {INSTRUMENT_ID}")
    print(f"Spot price    : {spot}")
    print(f"BUY price     : {buy_price}")
    print(f"SELL price    : {sell_price}")
    print(f"Quantity      : {QTY}")
    print(f"Requests      : {NUM_REQUESTS}")
    print(f"Workers       : {MAX_WORKERS}")

    # Take the initial snapshot.

    print("\nTaking initial database snapshot...")

    before = snapshot()

    print(f"Initial cash   : {before['cash']:.2f}")
    print(f"Initial shares : {before['shares']}")

    # Submit orders concurrently.

    print("\nSubmitting parallel orders...")

    start_total = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                send_order,
                i,
                unsafe,
                buy_price,
                sell_price
            )
            for i in range(NUM_REQUESTS)
        ]

        results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    total_time = round(
        time.perf_counter() - start_total,
        2
    )

    # Request statistics.

    successful_requests = sum(
        1
        for result in results
        if result["status_code"] in (200, 201)
    )

    failed_requests = NUM_REQUESTS - successful_requests

    average_latency = round(
        sum(r["elapsed_ms"] for r in results) / len(results),
        2
    )

    # Take the final snapshot only after all requests have completed.

    print("\nTaking final database snapshot...")

    after = snapshot()

    new_orders = count_new_orders(before["max_order"])

    # Check the invariants.

    checks = check_invariants(before, after)

    all_invariants_pass = all(
        passed
        for _, passed, _ in checks
    )

    all_requests_succeeded = (
        successful_requests == NUM_REQUESTS
    )

    all_orders_created = (
        new_orders == NUM_REQUESTS
    )

    # Display results.

    print("\n================ TEST SUMMARY =================")

    print(f"Mode                  : {mode}")
    print(f"Total execution time  : {total_time} seconds")
    print(f"Successful requests   : {successful_requests}")
    print(f"Failed requests       : {failed_requests}")
    print(f"New orders in DB      : {new_orders}")
    print(f"Average latency       : {average_latency} ms")

    print("\n---------------- INVARIANTS ----------------")

    for name, passed, detail in checks:

        status = "PASS" if passed else "FAIL"

        print(f"[{status}] {name}")
        print(f"       {detail}")

    print("\n---------------------------------------------")

    # Report request failures.

    if failed_requests > 0:

        print("\nSample request error:")

        for result in results:

            if result["status_code"] not in (200, 201):
                print(result["data"])
                break

    # Report test completeness separately from data invariants.

    print("\n---------------- TEST VALIDITY ----------------")

    print(
        "[PASS] All requests succeeded"
        if all_requests_succeeded
        else "[FAIL] Some requests failed"
    )

    print(
        "[PASS] All requests created database orders"
        if all_orders_created
        else "[FAIL] Expected order count does not match"
    )

    print("================================================")

    # Final verdict.

    # A run with failed requests or missing order records is inconclusive.
    # Do not mistake an HTTP error for a concurrency invariant failure.

    if not all_requests_succeeded or not all_orders_created:

        print("\nRESULT: INCONCLUSIVE")
        print(
            "Fix the API/database errors and run the test again."
        )

        return 1

    if unsafe:

        if not all_invariants_pass:

            print("\nRESULT: UNSAFE MODE DEMONSTRATED A FAILURE")
            print(
                "At least one invariant broke without row locking."
            )

            return 0

        else:

            print("\nRESULT: UNSAFE MODE DID NOT REPRODUCE THE BUG")
            print(
                "All invariants passed this time. "
                "Try running again or increasing NUM_REQUESTS."
            )

            return 1

    else:

        if all_invariants_pass:

            print("\nRESULT: SAFE MODE PASSED")
            print(
                "All invariants held with row-level locking."
            )

            return 0

        else:

            print("\nRESULT: SAFE MODE FAILED")
            print(
                "An invariant broke even with row-level locking."
            )

            return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Paper-trading exchange concurrency stress test"
    )

    parser.add_argument(
        "--unsafe",
        action="store_true",
        help="Use the unsafe matching procedure without row locks"
    )

    args = parser.parse_args()

    raise SystemExit(run(args.unsafe))
