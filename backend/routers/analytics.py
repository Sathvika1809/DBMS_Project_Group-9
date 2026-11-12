from fastapi import APIRouter

from database import get_db_connection

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/integrity")
def integrity():
    """Runs the integrity_report view: every violations count should be 0."""
    with get_db_connection() as conn:
        rows = conn.execute("SELECT check_name, violations FROM integrity_report").fetchall()
    return {"ok": all(r["violations"] == 0 for r in rows), "checks": rows}


@router.get("/audit")
def audit_log(limit: int = 30):
    with get_db_connection() as conn:
        return conn.execute(
            """
            SELECT log_id, table_name, row_id, action, old_values, new_values, changed_at
              FROM AUDIT_LOG ORDER BY log_id DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()


@router.get("/vwap")
def daily_vwap():
    with get_db_connection() as conn:
        return conn.execute(
            """
            SELECT i.symbol, t.executed_at::date AS day,
                   ROUND(SUM(t.price * t.qty) / SUM(t.qty), 2) AS vwap,
                   SUM(t.qty) AS volume, COUNT(*) AS trades
              FROM TRADE t
              JOIN "ORDER" o    ON o.order_id = t.buy_order_id
              JOIN INSTRUMENT i ON i.instrument_id = o.instrument_id
             GROUP BY i.symbol, t.executed_at::date ORDER BY i.symbol, day DESC
            """
        ).fetchall()


@router.get("/drawdown")
def drawdown():
    with get_db_connection() as conn:
        return conn.execute(
            """
            WITH bars AS (
                SELECT instrument_id, trade_date, close,
                       LAG(close, 30) OVER w AS close_30_ago,
                       MAX(close) OVER (PARTITION BY instrument_id ORDER BY trade_date
                                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_peak
                  FROM PRICE_BAR WINDOW w AS (PARTITION BY instrument_id ORDER BY trade_date)
            )
            SELECT i.symbol,
                   ROUND(MIN(b.close / b.running_peak - 1), 4) AS max_drawdown,
                   ROUND((ARRAY_AGG(b.close / b.close_30_ago - 1 ORDER BY b.trade_date DESC))[1], 4)
                       AS latest_30_bar_return
              FROM bars b JOIN INSTRUMENT i USING (instrument_id)
             GROUP BY i.symbol ORDER BY i.symbol
            """
        ).fetchall()
