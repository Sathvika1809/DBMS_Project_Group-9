from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from database import get_db_connection

router = APIRouter(prefix="/api/orders", tags=["Orders"])


class OrderCreateRequest(BaseModel):
    account_id: int = Field(..., description="ID of the trading account placing the order")
    instrument_id: int = Field(..., description="ID of the stock/bond/option instrument")
    side: str = Field(..., pattern="^(BUY|SELL)$", description="Order side: BUY or SELL")
    price: float = Field(..., gt=0, description="Limit price (must be positive)")
    qty: float = Field(..., gt=0, description="Order quantity (must be positive)")


@router.post("/", status_code=status.HTTP_201_CREATED)
def place_and_match_order(order: OrderCreateRequest, unsafe: bool = False):
    """
    Submits a LIMIT order and calls the match_and_settle stored procedure.
    ?unsafe=true calls match_and_settle_unsafe (no row locks) for the
    concurrency demo only.
    """
    # Fixed whitelist: never build the procedure name from user input.
    proc = "match_and_settle_unsafe" if unsafe else "match_and_settle"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO "ORDER" (account_id, instrument_id, side, price, qty, filled_qty, status)
                    VALUES (%s, %s, %s, %s, %s, 0, 'OPEN')
                    RETURNING order_id;
                    """,
                    (order.account_id, order.instrument_id, order.side, order.price, order.qty),
                )
                order_id = int(cur.fetchone()[0])

                cur.execute(f"CALL {proc}(%s::INT);", (order_id,))

                cur.execute('SELECT status, filled_qty FROM "ORDER" WHERE order_id = %s;', (order_id,))
                status_, filled = cur.fetchone()
            # leaving the connection context commits; any exception rolls back
            # the INSERT and the whole settlement together.

        return {
            "message": "Order placed and processed successfully.",
            "order_id": order_id,
            "status": status_,
            "filled_qty": float(filled),
            "mode": "unsafe" if unsafe else "safe",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order processing failed: {str(e)}",
        )