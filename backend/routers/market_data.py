from fastapi import APIRouter, HTTPException

from database import get_db_connection

router = APIRouter(prefix="/api/instruments", tags=["Market data"])


@router.get("")
@router.get("/", include_in_schema=False)
def list_instruments():
    with get_db_connection() as conn:
        return conn.execute(
            """
            SELECT i.instrument_id, i.symbol, i.name, i.instrument_type, i.sector, i.status,
                   i.multiplier, i.tick_size, i.lot_size, lp.last_price,
                   b.face_value, b.coupon_rate, b.coupon_frequency, b.issue_date, b.maturity_date,
                   approx_ytm(lp.last_price, b.coupon_rate, b.maturity_date, CURRENT_DATE) AS approx_ytm,
                   o.strike, o.expiry, o.option_type, u.symbol AS underlying_symbol
              FROM INSTRUMENT i
              JOIN last_price_view lp USING (instrument_id)
              LEFT JOIN BOND b   ON b.instrument_id = i.instrument_id
              LEFT JOIN OPTION o ON o.instrument_id = i.instrument_id
              LEFT JOIN INSTRUMENT u ON u.instrument_id = o.underlying_id
             ORDER BY i.instrument_id
            """
        ).fetchall()


@router.get("/{instrument_id}/bars")
def get_bars(instrument_id: int, limit: int = 120):
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT trade_date, open, high, low, close, volume
              FROM PRICE_BAR WHERE instrument_id = %s ORDER BY trade_date DESC LIMIT %s
            """,
            (instrument_id, limit),
        ).fetchall()
    return list(reversed(rows))


@router.get("/{instrument_id}/book")
def get_order_book(instrument_id: int):
    with get_db_connection() as conn:
        levels = conn.execute(
            """
            SELECT side, price, total_qty, num_orders, cumulative_qty
              FROM order_book_view WHERE instrument_id = %s
             ORDER BY CASE WHEN side = 'BUY' THEN -price ELSE price END
            """,
            (instrument_id,),
        ).fetchall()
        exists = conn.execute(
            "SELECT 1 FROM INSTRUMENT WHERE instrument_id = %s", (instrument_id,)
        ).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Instrument not found.")
    return {
        "bids": [l for l in levels if l["side"] == "BUY"],
        "asks": [l for l in levels if l["side"] == "SELL"],
    }


@router.get("/{instrument_id}/trades")
def get_recent_trades(instrument_id: int, limit: int = 20):
    with get_db_connection() as conn:
        return conn.execute(
            """
            SELECT t.trade_id, t.price, t.qty, t.executed_at
              FROM TRADE t JOIN "ORDER" o ON o.order_id = t.buy_order_id
             WHERE o.instrument_id = %s ORDER BY t.trade_id DESC LIMIT %s
            """,
            (instrument_id, limit),
        ).fetchall()