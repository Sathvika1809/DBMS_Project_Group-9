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
def place_and_match_order(order: OrderCreateRequest):
    """
    Submits a LIMIT order and triggers PostgreSQL match_and_settle stored procedure.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                insert_query = """
                    INSERT INTO "ORDER" (account_id, instrument_id, side, price, qty, filled_qty, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, 0.0, 'OPEN', NOW())
                    RETURNING order_id, status;
                """
                cur.execute(insert_query, (
                    order.account_id,
                    order.instrument_id,
                    order.side,
                    order.price,
                    order.qty
                ))
                new_order = cur.fetchone()
                order_id = int(new_order[0])

                # Explicit type cast %s::INT prevents smallint/int matching errors
                cur.execute("CALL match_and_settle(%s::INT);", (order_id,))
                
                cur.execute('SELECT status, filled_qty FROM "ORDER" WHERE order_id = %s;', (order_id,))
                updated_order = cur.fetchone()
                
                conn.commit()

                return {
                    "message": "Order placed and processed successfully.",
                    "order_id": order_id,
                    "status": updated_order[0],
                    "filled_qty": float(updated_order[1])
                }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order processing failed: {str(e)}"
        )