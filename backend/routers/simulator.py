import random
from decimal import Decimal, ROUND_HALF_UP

import psycopg
from fastapi import APIRouter, HTTPException

from database import db_error_message, get_db_connection

router = APIRouter(prefix="/api/simulate", tags=["Simulator"])


def _round_to_tick(price: Decimal, tick: Decimal) -> Decimal:
    steps = (price / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(tick, steps * tick)


@router.post("/tick")
def simulate_market_tick(instrument_id: int | None = None):
    try:
        with get_db_connection() as conn:
            # Prefer HOUSE / INSTITUTIONAL accounts (House Admin holds seeded inventory to sell)
            makers = conn.execute(
                """
                SELECT account_id FROM ACCOUNT
                 ORDER BY CASE
                            WHEN account_type = 'HOUSE' THEN 0
                            WHEN account_type IN ('INSTITUTIONAL', 'MARKET_MAKER') THEN 1
                            ELSE 2
                          END,
                          account_id ASC
                 LIMIT 2
                """
            ).fetchall()

            if len(makers) < 2:
                raise HTTPException(status_code=400, detail="Need at least 2 seeded accounts.")

            house_acct = makers[0]["account_id"]   # Holds inventory -> posts SELL asks
            second_acct = makers[1]["account_id"]  # Holds cash -> posts BUY bids
            maker_ids = [house_acct, second_acct]

            if instrument_id is not None:
                instruments = conn.execute(
                    """
                    SELECT i.instrument_id, i.symbol, i.tick_size,
                           COALESCE(
                               (SELECT price FROM TRADE WHERE instrument_id = i.instrument_id ORDER BY trade_id DESC LIMIT 1),
                               (SELECT close FROM PRICE_BAR WHERE instrument_id = i.instrument_id ORDER BY bar_date DESC LIMIT 1),
                               100.00
                           ) AS ref_price
                      FROM INSTRUMENT i
                     WHERE i.instrument_id = %s AND i.status = 'ACTIVE'
                    """,
                    (instrument_id,),
                ).fetchall()
            else:
                instruments = conn.execute(
                    """
                    SELECT i.instrument_id, i.symbol, i.tick_size,
                           COALESCE(
                               (SELECT price FROM TRADE WHERE instrument_id = i.instrument_id ORDER BY trade_id DESC LIMIT 1),
                               (SELECT close FROM PRICE_BAR WHERE instrument_id = i.instrument_id ORDER BY bar_date DESC LIMIT 1),
                               100.00
                           ) AS ref_price
                      FROM INSTRUMENT i
                     WHERE i.status = 'ACTIVE'
                    """
                ).fetchall()

            if not instruments:
                return {"quoted": 0, "trades_triggered": 0}

            target = random.choice(instruments)
            inst_id = target["instrument_id"]
            tick = Decimal(str(target["tick_size"]))
            mid = Decimal(str(target["ref_price"]))

            # Cancel old open bot orders so book stays fresh
            stale_orders = conn.execute(
                """
                SELECT order_id, account_id FROM "ORDER"
                 WHERE instrument_id = %s
                   AND account_id = ANY(%s)
                   AND status IN ('OPEN', 'PARTIAL')
                 ORDER BY order_id ASC
                 LIMIT 6
                """,
                (inst_id, maker_ids),
            ).fetchall()

            for stale in stale_orders:
                try:
                    with conn.transaction():
                        conn.execute(
                            "CALL cancel_order(%s::INT, %s::INT)",
                            (stale["order_id"], stale["account_id"]),
                        )
                except psycopg.Error:
                    pass

            drift_steps = random.choice([-1, 0, 0, 1])
            center = _round_to_tick(mid + tick * drift_steps, tick)

            placed = 0
            errors = []
            for level in (1, 2):
                bid_px = _round_to_tick(center - tick * level, tick)
                ask_px = _round_to_tick(center + tick * level, tick)
                qty = Decimal(str(random.choice([1, 2, 5])))

                # house_acct sells from inventory; second_acct buys with cash
                for acct, side, px in ((second_acct, "BUY", bid_px), (house_acct, "SELL", ask_px)):
                    try:
                        with conn.transaction():
                            row = conn.execute(
                                """
                                INSERT INTO "ORDER" (account_id, instrument_id, side, price, qty)
                                VALUES (%s, %s, %s, %s, %s) RETURNING order_id
                                """,
                                (acct, inst_id, side, px, qty),
                            ).fetchone()
                            conn.execute("CALL match_and_settle(%s::INT)", (row["order_id"],))
                            placed += 1
                    except psycopg.Error as exc:
                        errors.append(db_error_message(exc))

            # 70% chance to cross the spread so Time & Sales ticks live
            crossed = 0
            if random.random() < 0.7:
                cross_side = random.choice(["BUY", "SELL"])
                taker_acct = second_acct if cross_side == "BUY" else house_acct
                cross_px = _round_to_tick(
                    center + (tick if cross_side == "BUY" else -tick),
                    tick,
                )
                try:
                    with conn.transaction():
                        row = conn.execute(
                            """
                            INSERT INTO "ORDER" (account_id, instrument_id, side, price, qty)
                            VALUES (%s, %s, %s, %s, %s) RETURNING order_id
                            """,
                            (taker_acct, inst_id, cross_side, cross_px, Decimal("1")),
                        ).fetchone()
                        conn.execute("CALL match_and_settle(%s::INT)", (row["order_id"],))
                        crossed = 1
                except psycopg.Error as exc:
                    errors.append(db_error_message(exc))

            return {
                "symbol": target["symbol"],
                "center_price": str(center),
                "quotes_posted": placed,
                "trades_triggered": crossed,
                "errors": errors[:2],
            }
    except HTTPException:
        raise
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=db_error_message(e))